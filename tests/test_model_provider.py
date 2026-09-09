"""Wire-contract tests use injected transport; no live provider result is simulated in the app."""
import copy
import json
import socket

import pytest

from foundry.errors import DomainError
from foundry.model_provider import OpenAIProvider, MAX_RESPONSE_BYTES, MAX_REQUEST_BYTES


SCHEMA = {'type': 'object', 'properties': {'message': {'type': 'string'}},
          'required': ['message'], 'additionalProperties': False}


def envelope(output=None):
    return {'id': 'resp_test_123', 'model': 'gpt-6-astra', 'status': 'completed', 'error': None,
            'usage': {'input_tokens': 32, 'output_tokens': 12, 'total_tokens': 44, 'secret': 'discard this'},
            'output': [{'type': 'reasoning', 'summary': [{'text': 'Never store this reasoning'}]},
                       {'type': 'message', 'role': 'assistant', 'status': 'completed',
                        'content': [{'type': 'output_text', 'text': json.dumps(output or {'message': 'Draft commentary'})}]}]}


def provider_for(value, **kwargs):
    return OpenAIProvider(api_key='test-key', transport=lambda *a, **k: value if isinstance(value, bytes) else json.dumps(value).encode(), **kwargs)


def generate(provider):
    return provider.generate('Compose within supplied data.', {'fact': 'approved'}, SCHEMA, 'test_result')


def test_request_is_stateless_strict_and_toolless_and_receipt_is_sanitized():
    calls = []
    def transport(body, headers, **limits):
        calls.append((json.loads(body), headers, limits))
        return json.dumps(envelope()).encode()
    provider = OpenAIProvider(api_key='sensitive-test-key', transport=transport)
    result = generate(provider)
    request, headers, limits = calls[0]
    assert request['store'] is False and request['tools'] == [] and request['tool_choice'] == 'none'
    assert request['text']['format'] == {'type': 'json_schema', 'name': 'test_result', 'strict': True, 'schema': SCHEMA}
    assert request['max_output_tokens'] == 2048 and limits['timeout'] == 45
    assert headers['Authorization'] == 'Bearer sensitive-test-key'
    assert json.loads(request['input'][0]['content'][0]['text']) == {'fact': 'approved'}
    receipt = result['receipt']
    assert result['output'] == {'message': 'Draft commentary'}
    assert receipt['usage'] == {'input_tokens': 32, 'output_tokens': 12, 'total_tokens': 44}
    assert len(receipt['prompt_digest']) == len(receipt['response_digest']) == 64
    assert 'sensitive-test-key' not in json.dumps(result) + json.dumps(provider.status())
    assert 'Never store this reasoning' not in json.dumps(result)
    assert 'discard this' not in json.dumps(result)


def test_configuration_uses_environment_and_missing_key_does_not_call_transport(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setenv('FOUNDRY_OPENAI_MODEL', 'configured-model')
    called = []
    provider = OpenAIProvider(transport=lambda *a, **k: called.append(True))
    assert provider.status()['configured'] is False
    assert provider.status()['model'] == 'configured-model'
    with pytest.raises(DomainError) as error:
        generate(provider)
    assert error.value.code == 'MODEL_NOT_CONFIGURED' and called == []


@pytest.mark.parametrize('status', ['incomplete', 'failed', 'in_progress', 'cancelled', None])
def test_noncompleted_response_is_never_used(status):
    response = envelope(); response['status'] = status
    with pytest.raises(DomainError) as error:
        generate(provider_for(response))
    assert error.value.code == 'MODEL_INCOMPLETE'


def test_refusal_is_explicit_and_provider_text_is_not_exposed():
    response = envelope()
    response['output'][1]['content'] = [{'type': 'refusal', 'refusal': 'secret source text in rejection'}]
    with pytest.raises(DomainError) as error:
        generate(provider_for(response))
    assert error.value.code == 'MODEL_REFUSED'
    assert 'secret source' not in str(error.value)


@pytest.mark.parametrize('raw', [b'not JSON', b'[]', b'{"status":"completed","status":"failed"}', b'{"number":NaN}', b'\xff'])
def test_malformed_wire_json_fails_closed(raw):
    with pytest.raises(DomainError) as error:
        generate(provider_for(raw))
    assert error.value.code == 'MODEL_RESPONSE_INVALID'


@pytest.mark.parametrize('value', ['["wrong root"]', '{"a":1,"a":2}', '{"a":NaN}', 'not JSON'])
def test_output_json_must_be_one_strict_object(value):
    response = envelope(); response['output'][1]['content'][0]['text'] = value
    with pytest.raises(DomainError) as error:
        generate(provider_for(response))
    assert error.value.code == 'MODEL_OUTPUT_INVALID'


@pytest.mark.parametrize('mutate', [
    lambda r: r['output'].append({'type': 'function_call', 'name': 'publish'}),
    lambda r: r['output'][1].update(status='incomplete'),
    lambda r: r['output'][1].update(role='user'),
    lambda r: r['output'][1]['content'].append(copy.deepcopy(r['output'][1]['content'][0])),
    lambda r: r.update(id='id\ninvalid'),
])
def test_unexpected_output_items_or_receipts_are_not_accepted(mutate):
    response = envelope(); mutate(response)
    with pytest.raises(DomainError) as error:
        generate(provider_for(response))
    assert error.value.code == 'MODEL_RESPONSE_INVALID'


@pytest.mark.parametrize('exception,code', [(socket.timeout('secret key'), 'MODEL_TIMEOUT'),
                                          (OSError('secret provider body'), 'MODEL_UNAVAILABLE')])
def test_transport_failures_are_bounded_and_redacted(exception, code):
    def fail(*a, **k):
        raise exception
    with pytest.raises(DomainError) as error:
        generate(OpenAIProvider(api_key='test-key', transport=fail))
    assert error.value.code == code
    assert 'secret' not in str(error.value)


def test_request_and_response_limits_apply_to_injected_transport_too():
    with pytest.raises(DomainError) as error:
        generate(provider_for(b' ' * (MAX_RESPONSE_BYTES + 1)))
    assert error.value.code == 'MODEL_RESPONSE_LIMIT'
    called = []
    provider = OpenAIProvider(api_key='test-key', transport=lambda *a, **k: called.append(True))
    with pytest.raises(DomainError) as error:
        provider.generate('Scope', {'large': 'x' * MAX_REQUEST_BYTES}, SCHEMA, 'result')
    assert error.value.code == 'MODEL_REQUEST_LIMIT' and called == []


def test_prompt_identity_changes_when_scoped_inputs_or_schema_change():
    provider = provider_for(envelope())
    first = generate(provider)['receipt']
    second = provider.generate('Different instructions', {'fact': 'approved'}, SCHEMA, 'test_result')['receipt']
    assert first['prompt_digest'] != second['prompt_digest']
    assert first['response_digest'] == second['response_digest']


def test_https_transport_does_not_read_error_body_or_follow_redirect(monkeypatch):
    from foundry import model_provider
    calls = []
    class Response:
        status = 302
        def read(self, *args):
            raise AssertionError('Error body must not be read')
    class Connection:
        sock = None
        def __init__(self, host, **kwargs):
            calls.append(host)
        def request(self, method, path, **kwargs):
            calls.append((method, path))
        def getresponse(self):
            return Response()
        def close(self):
            calls.append('closed')
    monkeypatch.setattr(model_provider.http.client, 'HTTPSConnection', Connection)
    with pytest.raises(DomainError) as error:
        generate(OpenAIProvider(api_key='test-key'))
    assert error.value.code == 'MODEL_HTTP_ERROR'
    assert error.value.details == {'http_status': 302}
    assert calls == ['api.openai.com', ('POST', '/v1/responses'), 'closed']
