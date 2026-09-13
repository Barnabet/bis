"""Wire-contract tests use injected transport; no live provider result is simulated in the app."""
import copy
import json
import socket

import pytest

from foundry.errors import DomainError
from foundry.model_provider import OpenAIProvider, MAX_RESPONSE_BYTES, MAX_REQUEST_BYTES


SCHEMA = {'type': 'object', 'properties': {'message': {'type': 'string'}},
          'required': ['message'], 'additionalProperties': False}


@pytest.fixture(autouse=True)
def isolated_provider_environment_and_no_network(monkeypatch):
    """Host proxy credentials/configuration must never influence wire tests."""
    for name in ('OPENAI_API_KEY', 'FOUNDRY_OPENAI_MODEL', 'FOUNDRY_MODEL_PROVIDER',
                 'FOUNDRY_MODEL_BASE_URL', 'FOUNDRY_MODEL_NAME', 'FOUNDRY_MODEL_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    def forbidden_connection(*args, **kwargs):
        pytest.fail('Provider regression tests must not make real network connections.')
    monkeypatch.setattr(socket, 'create_connection', forbidden_connection)


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


PROXY_URL = 'http://127.0.0.1:8317/v1'
PROXY_MODEL = 'claude-opus-5'


def proxy_envelope():
    response = envelope()
    response['model'] = PROXY_MODEL
    return response


def proxy_provider(**kwargs):
    config = {'provider': 'cliproxyapi', 'base_url': PROXY_URL,
              'model': PROXY_MODEL, 'api_key': 'local-test-key'}
    config.update(kwargs)
    return OpenAIProvider(**config)


def test_proxy_environment_uses_separate_key_and_preserves_responses_contract(monkeypatch):
    monkeypatch.setenv('FOUNDRY_MODEL_PROVIDER', 'cliproxyapi')
    monkeypatch.setenv('FOUNDRY_MODEL_BASE_URL', PROXY_URL + '/')
    monkeypatch.setenv('FOUNDRY_MODEL_NAME', PROXY_MODEL)
    monkeypatch.setenv('FOUNDRY_MODEL_API_KEY', 'local-only-test-key')
    monkeypatch.setenv('OPENAI_API_KEY', 'must-not-forward-public-key')
    calls = []
    def transport(body, headers, **limits):
        calls.append((json.loads(body), headers, limits))
        return json.dumps(proxy_envelope()).encode()
    provider = OpenAIProvider(transport=transport)
    result = generate(provider)
    assert len(calls) == 1
    request, headers, limits = calls[0]
    assert headers['Authorization'] == 'Bearer local-only-test-key'
    assert 'must-not-forward-public-key' not in json.dumps(calls)
    assert request['model'] == PROXY_MODEL
    assert request['store'] is False and request['tools'] == [] and request['tool_choice'] == 'none'
    assert request['text']['format'] == {'type': 'json_schema', 'name': 'test_result', 'strict': True, 'schema': SCHEMA}
    assert json.loads(request['input'][0]['content'][0]['text']) == {'fact': 'approved'}
    assert request['max_output_tokens'] == 2048 and limits['timeout'] == 45
    status = provider.status()
    assert status['configured'] is True
    for field, value in {'provider':'cliproxyapi', 'base_url':PROXY_URL, 'protocol':'responses', 'model':PROXY_MODEL}.items():
        assert status[field] == result['receipt'][field] == value
    assert result['receipt']['requested_model'] == PROXY_MODEL
    assert result['receipt']['usage'] == {'input_tokens':32, 'output_tokens':12, 'total_tokens':44}
    serialized = json.dumps(status) + json.dumps(result)
    for secret in ['local-only-test-key', 'must-not-forward-public-key', 'Never store this reasoning']:
        assert secret not in serialized


def test_proxy_missing_local_key_does_not_fall_back_to_public_openai_key(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'public-account-test-key')
    called = []
    provider = proxy_provider(api_key=None, transport=lambda *a, **k: called.append(True))
    assert provider.status()['configured'] is False
    with pytest.raises(DomainError) as error:
        generate(provider)
    assert error.value.code == 'MODEL_NOT_CONFIGURED'
    assert called == [] and 'public-account-test-key' not in str(error.value)


def test_public_openai_does_not_use_local_proxy_credential(monkeypatch):
    monkeypatch.setenv('FOUNDRY_MODEL_API_KEY', 'local-account-test-key')
    called = []
    provider = OpenAIProvider(provider='openai', transport=lambda *a, **k: called.append(True))
    assert provider.status()['configured'] is False
    with pytest.raises(DomainError) as error:
        generate(provider)
    assert error.value.code == 'MODEL_NOT_CONFIGURED' and called == []


@pytest.mark.parametrize('base_url', [PROXY_URL, PROXY_URL + '/'])
def test_proxy_base_url_canonicalizes_trailing_slash(base_url):
    assert proxy_provider(base_url=base_url).status()['base_url'] == PROXY_URL


@pytest.mark.parametrize('base_url,canonical', [
    ('http://localhost:8317', PROXY_URL),
    ('http://LOCALHOST:8317/v1/', PROXY_URL),
    ('http://127.0.0.1:8317/', PROXY_URL),
    ('http://127.0.0.2:8321', 'http://127.0.0.2:8321/v1'),
    ('http://[::1]:8317/v1/', 'http://[::1]:8317/v1'),
    ('https://localhost:8317/v1', 'https://127.0.0.1:8317/v1'),
])
def test_proxy_canonicalizes_explicit_loopback_endpoints(base_url, canonical):
    assert proxy_provider(base_url=base_url).status()['base_url'] == canonical


@pytest.mark.parametrize('base_url', [
    'http://example.com:8317/v1', 'https://api.openai.com/v1',
    'http://192.168.1.10:8317/v1', 'http://0.0.0.0:8317/v1',
    'http://127.0.0.1.example.com:8317/v1', 'http://2130706433:8317/v1',
    'http://127.1:8317/v1', 'http://[::]:8317/v1',
    'http://127.0.0.1:0/v1', 'http://127.0.0.1:65536/v1',
    'http://user:private-url-password@127.0.0.1:8317/v1',
    PROXY_URL + '?api_key=private-url-password', PROXY_URL + '#private-url-password',
    PROXY_URL + '?', PROXY_URL + '#', PROXY_URL + '\n',
    'file:///tmp/proxy', 'ftp://127.0.0.1:8317/v1',
    'http://127.0.0.1:8317/v1/responses', 'http://127.0.0.1:8317/%76%31',
])
def test_proxy_rejects_unapproved_or_ambiguous_endpoints_without_network(base_url):
    with pytest.raises(DomainError) as error:
        proxy_provider(base_url=base_url)
    assert error.value.code == 'MODEL_CONFIGURATION_INVALID'
    assert 'private-url-password' not in str(error.value) + json.dumps(error.value.details)


def test_unknown_provider_and_public_endpoint_override_are_rejected():
    with pytest.raises(DomainError) as error:
        OpenAIProvider(provider='unconfigured-provider')
    assert error.value.code == 'MODEL_CONFIGURATION_INVALID'
    with pytest.raises(DomainError) as error:
        OpenAIProvider(provider='openai', base_url=PROXY_URL, api_key='public-test-key')
    assert error.value.code == 'MODEL_CONFIGURATION_INVALID'


def test_proxy_prompt_adds_json_only_instruction_and_complete_schema_without_mutation():
    calls = []
    def transport(body, headers, **limits):
        calls.append(json.loads(body))
        return json.dumps(proxy_envelope()).encode()
    schema = copy.deepcopy(SCHEMA)
    result = proxy_provider(transport=transport).generate('Compose within supplied data.', {'fact':'approved'}, schema, 'test_result')
    instructions = calls[0]['instructions']
    lower = instructions.lower()
    assert 'Compose within supplied data.' in instructions
    assert 'json' in lower and ('only' in lower or 'exactly one' in lower)
    assert ('markdown' in lower or 'fence' in lower) and ('no ' in lower or 'without' in lower or 'never' in lower or 'do not' in lower)
    # The schema is supplied in prompt text as well as text.format, because a
    # compatible proxy may accept the latter without enforcing its schema.
    decoder = json.JSONDecoder()
    embedded = []
    for index, char in enumerate(instructions):
        if char == '{':
            try:
                embedded.append(decoder.raw_decode(instructions[index:])[0])
            except ValueError:
                pass
    assert SCHEMA in embedded
    assert schema == SCHEMA
    assert result['output'] == {'message':'Draft commentary'}


@pytest.mark.parametrize('wrapped', [
    '```json\n{"message":"Draft commentary"}\n```',
    '```\n{"message":"Draft commentary"}\n```',
    'Here is the JSON: {"message":"Draft commentary"}',
])
def test_proxy_does_not_strip_fences_or_repair_non_json_output(wrapped):
    response = proxy_envelope()
    response['output'][1]['content'][0]['text'] = wrapped
    calls = []
    def transport(*args, **kwargs):
        calls.append(True)
        return json.dumps(response).encode()
    with pytest.raises(DomainError) as error:
        generate(proxy_provider(transport=transport))
    assert error.value.code == 'MODEL_OUTPUT_INVALID'
    assert len(calls) == 1


def test_proxy_rejects_model_substitution_but_public_alias_receipt_is_preserved():
    response = proxy_envelope()
    response['model'] = 'claude-opus-other'
    with pytest.raises(DomainError) as error:
        generate(proxy_provider(transport=lambda *a, **k: json.dumps(response).encode()))
    assert error.value.code == 'MODEL_IDENTITY_MISMATCH'
    response = envelope()
    response['model'] = 'gpt-6-astra-2026-09-01'
    result = generate(provider_for(response, provider='openai', model='gpt-6-astra'))
    assert result['receipt']['requested_model'] == 'gpt-6-astra'
    assert result['receipt']['model'] == 'gpt-6-astra-2026-09-01'


def test_proxy_endpoint_and_model_are_part_of_the_pinnable_configuration():
    original = proxy_provider().status()
    assert original != proxy_provider(base_url='http://127.0.0.1:8318/v1').status()
    assert original != proxy_provider(model='claude-opus-other').status()
    assert original == proxy_provider(base_url='http://localhost:8317/').status()


def test_proxy_request_limit_includes_explicit_schema_prompt_without_calling_transport():
    calls = []
    provider = proxy_provider(transport=lambda *a, **k: calls.append(True))
    schema = {**SCHEMA, 'description': 'x' * (MAX_REQUEST_BYTES // 2)}
    with pytest.raises(DomainError) as error:
        provider.generate('Scope', {}, schema, 'test_result')
    assert error.value.code == 'MODEL_REQUEST_LIMIT'
    assert calls == []


def _fake_http(monkeypatch, *, status=200, body=None, headers=None, fail_read=None):
    """Exercise the real HTTP adapter without opening a socket."""
    from foundry import model_provider
    events = []
    data = json.dumps(proxy_envelope()).encode() if body is None else body
    response_headers = {} if headers is None else headers
    class Response:
        def __init__(self):
            self.status, self.offset = status, 0
        def getheader(self, name, default=None):
            return response_headers.get(name, default)
        def read1(self, amount):
            events.append(('read', amount))
            if fail_read:
                raise fail_read
            result = data[self.offset:self.offset + amount]
            self.offset += len(result)
            return result
    class Connection:
        sock = None
        def __init__(self, host, port=None, **kwargs):
            events.append(('connect', host, port, kwargs))
        def request(self, method, path, **kwargs):
            events.append(('request', method, path, kwargs))
        def getresponse(self):
            return Response()
        def close(self):
            events.append(('closed',))
    monkeypatch.setattr(model_provider.http.client, 'HTTPConnection', Connection)
    return events


def test_proxy_http_posts_same_responses_wire_and_closes_connection(monkeypatch):
    events = _fake_http(monkeypatch)
    result = generate(proxy_provider())
    connection = next(event for event in events if event[0] == 'connect')
    assert connection[1:3] == ('127.0.0.1', 8317)
    request = next(event for event in events if event[0] == 'request')
    assert request[1:3] == ('POST', '/v1/responses')
    assert json.loads(request[3]['body'])['model'] == PROXY_MODEL
    assert request[3]['headers']['Authorization'] == 'Bearer local-test-key'
    assert request[3]['headers']['Accept-Encoding'] == 'identity'
    assert events[-1] == ('closed',)
    assert result['receipt']['base_url'] == PROXY_URL


@pytest.mark.parametrize('status', [302, 307, 401, 500])
def test_proxy_http_errors_are_not_read_redirected_or_retried(monkeypatch, status):
    events = _fake_http(monkeypatch, status=status, body=b'private provider error body')
    with pytest.raises(DomainError) as error:
        generate(proxy_provider())
    assert error.value.code == 'MODEL_HTTP_ERROR' and error.value.details == {'http_status':status}
    assert not any(event[0] == 'read' for event in events)
    assert sum(event[0] == 'connect' for event in events) == 1
    assert events[-1] == ('closed',)
    assert 'private provider' not in str(error.value)


@pytest.mark.parametrize('headers,code', [
    ({'Content-Length':str(MAX_RESPONSE_BYTES + 1)}, 'MODEL_RESPONSE_LIMIT'),
    ({'Content-Length':'not-a-number'}, 'MODEL_RESPONSE_INVALID'),
    ({'Content-Encoding':'gzip'}, 'MODEL_RESPONSE_INVALID'),
])
def test_proxy_response_metadata_limits_apply_before_body_read(monkeypatch, headers, code):
    events = _fake_http(monkeypatch, headers=headers)
    with pytest.raises(DomainError) as error:
        generate(proxy_provider())
    assert error.value.code == code
    assert not any(event[0] == 'read' for event in events)
    assert events[-1] == ('closed',)


def test_proxy_unknown_length_response_is_bounded_while_reading(monkeypatch):
    events = _fake_http(monkeypatch, body=b'x' * 129)
    with pytest.raises(DomainError) as error:
        generate(proxy_provider(max_response_bytes=128))
    assert error.value.code == 'MODEL_RESPONSE_LIMIT'
    assert events[-1] == ('closed',)


def test_proxy_read_timeout_is_redacted_without_retry(monkeypatch):
    events = _fake_http(monkeypatch, fail_read=socket.timeout('private proxy credential'))
    with pytest.raises(DomainError) as error:
        generate(proxy_provider())
    assert error.value.code == 'MODEL_TIMEOUT'
    assert 'private proxy credential' not in str(error.value)
    assert sum(event[0] == 'connect' for event in events) == 1
    assert events[-1] == ('closed',)
