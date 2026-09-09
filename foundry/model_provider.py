"""Bounded, stateless OpenAI Responses transport. Never logs credentials or bodies.

Official wire contract: https://developers.openai.com/api/docs/guides/structured-outputs
The injectable transport exists for deterministic tests, not an application mock mode.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import ssl
import time

from .errors import DomainError

DEFAULT_MODEL = 'gpt-6-astra'
MAX_REQUEST_BYTES = 131_072
MAX_RESPONSE_BYTES = 262_144
MAX_OUTPUT_TOKENS = 2_048
TIMEOUT_SECONDS = 45


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else _canonical(value)).hexdigest()


def _json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('Nonfinite JSON value')
    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


def _https_transport(body, headers, *, timeout, max_response_bytes):
    """Fixed HTTPS origin; no redirects, configurable URLs, cookies or tool calls."""
    connection = http.client.HTTPSConnection('api.openai.com', timeout=timeout, context=ssl.create_default_context())
    deadline = time.monotonic() + timeout
    try:
        connection.request('POST', '/v1/responses', body=body, headers=headers)
        if connection.sock:
            connection.sock.settimeout(max(.001, deadline - time.monotonic()))
        response = connection.getresponse()
        # Do not read or propagate a provider error body, which may contain inputs.
        if response.status != 200:
            raise DomainError('MODEL_HTTP_ERROR', 'The model provider rejected the request.', 502,
                              {'http_status': response.status})
        length = response.getheader('Content-Length')
        if length is not None:
            try:
                if int(length) < 0 or int(length) > max_response_bytes:
                    raise DomainError('MODEL_RESPONSE_LIMIT', 'The model response exceeded the byte limit.', 502)
            except ValueError:
                raise DomainError('MODEL_RESPONSE_INVALID', 'The model provider returned invalid response metadata.', 502) from None
        if response.getheader('Content-Encoding', 'identity') != 'identity':
            raise DomainError('MODEL_RESPONSE_INVALID', 'Compressed model responses are not accepted.', 502)
        chunks, total = [], 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            if connection.sock:
                connection.sock.settimeout(remaining)
            chunk = response.read1(min(16_384, max_response_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_response_bytes:
                raise DomainError('MODEL_RESPONSE_LIMIT', 'The model response exceeded the byte limit.', 502)
        return b''.join(chunks)
    finally:
        connection.close()


class OpenAIProvider:
    def __init__(self, *, api_key=None, model=None, transport=None, timeout=TIMEOUT_SECONDS,
                 max_output_tokens=MAX_OUTPUT_TOKENS, max_response_bytes=MAX_RESPONSE_BYTES):
        self._api_key = (os.environ.get('OPENAI_API_KEY', '') if api_key is None else api_key).strip()
        self.model = (os.environ.get('FOUNDRY_OPENAI_MODEL', DEFAULT_MODEL) if model is None else model).strip()
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', self.model):
            raise DomainError('MODEL_CONFIGURATION_INVALID', 'Configure a valid model identifier.')
        if self._api_key and (len(self._api_key) > 1024 or any(ord(c) < 33 or ord(c) > 126 for c in self._api_key)):
            raise DomainError('MODEL_CONFIGURATION_INVALID', 'The model credential has an invalid format.')
        if not 0 < timeout <= TIMEOUT_SECONDS or not 1 <= max_output_tokens <= MAX_OUTPUT_TOKENS or not 1 <= max_response_bytes <= MAX_RESPONSE_BYTES:
            raise DomainError('MODEL_CONFIGURATION_INVALID', 'Model request limits exceed the supported bounds.')
        self.timeout, self.max_output_tokens, self.max_response_bytes = timeout, max_output_tokens, max_response_bytes
        self._transport = transport or _https_transport

    def status(self):
        return {'configured': bool(self._api_key), 'provider': 'openai', 'model': self.model,
                'limits': {'timeout_seconds': self.timeout, 'max_output_tokens': self.max_output_tokens,
                           'max_request_bytes': MAX_REQUEST_BYTES, 'max_response_bytes': self.max_response_bytes}}

    def generate(self, instructions, payload, schema, name):
        if not self._api_key:
            raise DomainError('MODEL_NOT_CONFIGURED', 'Set OPENAI_API_KEY to enable model composition.', 409)
        if not isinstance(instructions, str) or not instructions.strip() or not isinstance(payload, dict) or not isinstance(schema, dict):
            raise DomainError('MODEL_REQUEST_INVALID', 'The model request requires instructions, a data object and a schema.')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', name):
            raise DomainError('MODEL_REQUEST_INVALID', 'The structured response schema name is invalid.')
        try:
            request = {'model': self.model, 'store': False, 'instructions': instructions,
                       'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': _canonical(payload).decode()}]}],
                       'text': {'format': {'type': 'json_schema', 'name': name, 'strict': True, 'schema': schema}},
                       'max_output_tokens': self.max_output_tokens, 'tools': [], 'tool_choice': 'none'}
            body = _canonical(request)
        except (ValueError, TypeError, UnicodeError):
            raise DomainError('MODEL_REQUEST_INVALID', 'The model request must contain finite JSON data.') from None
        if len(body) > MAX_REQUEST_BYTES:
            raise DomainError('MODEL_REQUEST_LIMIT', 'The scoped model request exceeds the byte limit.')
        try:
            raw = self._transport(body, {'Authorization': f'Bearer {self._api_key}', 'Content-Type': 'application/json',
                                         'Accept': 'application/json', 'Accept-Encoding': 'identity'},
                                  timeout=self.timeout, max_response_bytes=self.max_response_bytes)
        except DomainError:
            raise
        except TimeoutError:
            raise DomainError('MODEL_TIMEOUT', 'The model request exceeded its time limit.', 504) from None
        except Exception:
            raise DomainError('MODEL_UNAVAILABLE', 'The model provider could not be reached.', 502) from None
        if not isinstance(raw, bytes):
            raise DomainError('MODEL_RESPONSE_INVALID', 'The model transport returned an invalid response.', 502)
        if len(raw) > self.max_response_bytes:
            raise DomainError('MODEL_RESPONSE_LIMIT', 'The model response exceeded the byte limit.', 502)
        try:
            response = _json(raw)
        except (ValueError, UnicodeError, RecursionError):
            raise DomainError('MODEL_RESPONSE_INVALID', 'The model provider returned invalid JSON.', 502) from None
        if not isinstance(response, dict):
            raise DomainError('MODEL_RESPONSE_INVALID', 'The model provider returned an invalid response envelope.', 502)
        if response.get('status') != 'completed' or response.get('error'):
            raise DomainError('MODEL_INCOMPLETE', 'The model did not complete a usable response.', 502)
        texts = []
        output = response.get('output')
        if not isinstance(output, list):
            raise DomainError('MODEL_RESPONSE_INVALID', 'The model response has no output array.', 502)
        for item in output:
            if not isinstance(item, dict):
                raise DomainError('MODEL_RESPONSE_INVALID', 'The model returned an invalid output item.', 502)
            if item.get('type') == 'reasoning':
                continue  # Neither persist nor expose reasoning content.
            if item.get('type') != 'message' or item.get('role') != 'assistant' or item.get('status') != 'completed':
                raise DomainError('MODEL_RESPONSE_INVALID', 'The model returned an unexpected output item.', 502)
            content = item.get('content')
            if not isinstance(content, list):
                raise DomainError('MODEL_RESPONSE_INVALID', 'The model message content is invalid.', 502)
            for part in content:
                if isinstance(part, dict) and part.get('type') == 'refusal':
                    raise DomainError('MODEL_REFUSED', 'The model declined to compose this commentary.', 422)
                if not isinstance(part, dict) or part.get('type') != 'output_text' or not isinstance(part.get('text'), str):
                    raise DomainError('MODEL_RESPONSE_INVALID', 'The model returned unsupported message content.', 502)
                texts.append(part['text'])
        if len(texts) != 1:
            raise DomainError('MODEL_RESPONSE_INVALID', 'The model must return one structured text result.', 502)
        try:
            parsed = _json(texts[0])
            if not isinstance(parsed, dict):
                raise ValueError()
        except (ValueError, UnicodeError, RecursionError):
            raise DomainError('MODEL_OUTPUT_INVALID', 'The model output is not a valid JSON object.', 502) from None
        response_id = response.get('id')
        actual_model = response.get('model')
        if not isinstance(response_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', response_id) or not isinstance(actual_model, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', actual_model):
            raise DomainError('MODEL_RESPONSE_INVALID', 'The model response lacks a valid receipt identity.', 502)
        usage = response.get('usage')
        safe_usage = {}
        if isinstance(usage, dict):
            safe_usage = {k: usage[k] for k in ('input_tokens', 'output_tokens', 'total_tokens')
                          if isinstance(usage.get(k), int) and not isinstance(usage[k], bool) and usage[k] >= 0}
        return {'output': parsed, 'receipt': {'provider': 'openai', 'model': actual_model, 'requested_model': self.model,
                'response_id': response_id, 'usage': safe_usage, 'prompt_digest': _digest(body), 'response_digest': _digest(raw),
                'output_digest': _digest(parsed), 'schema_digest': _digest(schema), 'store': False,
                'limits': self.status()['limits']}}


def status():
    return OpenAIProvider().status()


def generate(instructions, payload, schema, name):
    return OpenAIProvider().generate(instructions, payload, schema, name)
