"""Bounded Responses / Chat Completions transport. Credentials stay private."""
from __future__ import annotations

import copy
import json
import os
import time
from urllib.parse import urlparse

import httpx

from ecfkg.llm import ModelError

DEFAULT_API_BASE = "https://api.openai.com/v1"


class APIError(ModelError):
    """Only application-authored messages may cross into the UI or exports."""
    MESSAGES = {
        "missing_model": "Enter an API model identifier before running.",
        "missing_key": "Enter an API key or set ECFKG_API_KEY / OPENAI_API_KEY.",
        "authentication": "API authentication failed. Check that the key is active and belongs to this provider/project.",
        "access": "API access denied. Check the key's project and model permissions.",
        "not_found": "API model or route was not found. Check the model ID, account access and API base URL.",
        "quota": "API quota is exhausted. Check the API project's billing balance and spending limit.",
        "rate_limit": "API rate limit or quota reached. Check API billing and retry after the provider's limit resets.",
        "request": "The API rejected the request. Check the API protocol and provider compatibility settings.",
        "tools": "The API rejected tool calling. Use Responses for GPT-6.1 Sol; verify tool support for other providers.",
        "format": "The API rejected the output format. Check structured-output support or select JSON object mode.",
        "token_parameter": "The API rejected the token limit parameter. Check Provider compatibility settings.",
        "redirect": "The API redirected the request. Enter the provider's direct HTTPS base URL.",
        "server": "The API service failed to complete the request. Retry later.",
        "timeout": "The API request timed out. Retry later; no automatic retry ran.",
        "connection": "Could not connect securely to the API. Check the base URL, network and certificate configuration.",
        "bounds": "The API response exceeded the configured size or time limit.",
        "malformed": "The API returned an invalid response for the selected protocol.",
        "inventory": "The API returned an invalid model inventory. This provider may not support the connection check.",
        "incomplete": "The model reached its output limit before finishing. The response was not used.",
        "refusal": "The model declined the request. The response was not used.",
    }

    def __init__(self, code: str, http_status: int | None = None):
        self.code = code if code in self.MESSAGES else "malformed"
        self.http_status = http_status if type(http_status) is int and 100 <= http_status <= 599 else None
        super().__init__(self.MESSAGES[self.code] + (f" (HTTP {self.http_status})" if self.http_status else ""))


def resolve_protocol(endpoint: str, protocol: str = "auto") -> str:
    if protocol not in {"auto", "responses", "chat_completions"}:
        raise ValueError("API protocol must be auto, responses or chat_completions")
    if protocol == "auto":
        try:
            host = urlparse(endpoint).hostname
        except ValueError:
            host = None  # The adapter validates the URL before making any request.
        return "responses" if host == "api.openai.com" else "chat_completions"
    return protocol


def api_endpoint(value: str) -> str:
    """A base URL, never a credential-bearing URL or redirect target."""
    value = value.strip().rstrip("/")
    url = urlparse(value)
    try:
        _ = url.port
    except ValueError:
        raise ValueError("API base URL has an invalid port") from None
    if (url.scheme != "https" or not url.hostname or url.username or url.password
        or url.query or url.fragment or any(c.isspace() for c in value)
        or "\\" in value or "%" in value or ".." in url.path
        or url.path.endswith(("/chat/completions", "/responses", "/models"))):
        raise ValueError("Enter an HTTPS API base URL, such as https://api.openai.com/v1, without credentials or a method path")
    return value


class OpenAICompatibleAdapter:
    is_mock = False
    execution_mode = "api"

    def __init__(self, model: str | None = None, endpoint: str | None = None,
                 api_key: str | None = None, response_format: str | None = None,
                 token_parameter: str | None = None, transport=None, *, protocol: str | None = None):
        self.model = (model if model is not None else os.environ.get("ECFKG_MODEL", "")).strip()
        self.endpoint = api_endpoint(endpoint or os.environ.get("ECFKG_API_BASE_URL", DEFAULT_API_BASE))
        self.protocol = resolve_protocol(self.endpoint, protocol or os.environ.get("ECFKG_API_PROTOCOL", "auto"))
        self.__api_key = (api_key if api_key is not None else
                          os.environ.get("ECFKG_API_KEY") or os.environ.get("OPENAI_API_KEY", "")).strip()
        self.response_format = response_format or os.environ.get("ECFKG_API_RESPONSE_FORMAT", "json_schema")
        token_parameter = token_parameter or os.environ.get("ECFKG_API_TOKEN_PARAMETER", "max_completion_tokens")
        if self.response_format not in {"json_schema", "json_object"}:
            raise ValueError("Unsupported API response format")
        if token_parameter not in {"max_completion_tokens", "max_tokens"}:
            raise ValueError("Unsupported API token parameter")
        if len(self.model) > 200 or any(c in self.model for c in "\r\n"):
            raise ValueError("Invalid API model identifier")
        self.options = {"max_output_tokens": 4096} if self.protocol == "responses" else {token_parameter: 2048}
        # Sol supports low effort; keep this small retrieval task within its bounded turn.
        if self.protocol == "responses" and self.model == "gpt-6.1-sol":
            self.options["reasoning"] = {"effort": "low"}
        self.request_timeout_seconds = 60 if self.protocol == "responses" else 25
        self.transport = transport
        self.metadata = {"provider_protocol": self.protocol,
                         "response_format": self.response_format,
                         "sampling": "provider defaults; no temperature or seed override"}

    def ensure_configured(self):
        if not self.model:
            raise APIError("missing_model")
        if not self.__api_key or any(c.isspace() for c in self.__api_key):
            raise APIError("missing_key")

    @staticmethod
    def _http_error(status: int, data: bytes) -> APIError:
        category = {400: "request", 401: "authentication", 403: "access", 404: "not_found",
                    422: "request", 429: "rate_limit"}.get(status, "server" if status >= 500 else "request")
        if 300 <= status < 400:
            category = "redirect"
        try:
            error = json.loads(data).get("error", {})
            code, param = error.get("code"), error.get("param")
            # Never display the raw body, message, code, parameter or echoed credentials.
            if status in {400, 401, 403, 404, 429} and isinstance(code, str):
                category = {"invalid_api_key": "authentication", "model_not_found": "not_found",
                            "insufficient_quota": "quota", "rate_limit_exceeded": "rate_limit"}.get(code, category)
            if status in {400, 422} and isinstance(param, str):
                category = {"tools": "tools", "response_format": "format", "text.format": "format",
                            "max_tokens": "token_parameter", "max_completion_tokens": "token_parameter"}.get(param, category)
        except (ValueError, AttributeError, TypeError):
            pass
        return APIError(category, status)

    def _request(self, method: str, path: str, payload=None, timeout=25.0):
        self.ensure_configured()
        started = time.perf_counter()
        try:
            with httpx.Client(trust_env=False, follow_redirects=False, transport=self.transport,
                              timeout=httpx.Timeout(timeout, connect=min(5.0, timeout))) as client:
                with client.stream(method, self.endpoint + path, json=payload,
                                   headers={"Authorization": "Bearer " + self.__api_key}) as response:
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > 262144 or time.perf_counter() - started > timeout:
                            raise APIError("bounds")
                    if response.status_code >= 300:
                        raise self._http_error(response.status_code, data)
            result = json.loads(data)
            if not isinstance(result, dict):
                raise APIError("malformed")
            return result
        except httpx.TimeoutException:
            raise APIError("timeout") from None
        except httpx.HTTPError:
            raise APIError("connection") from None
        except (ValueError, TypeError):
            # Never expose provider bodies, request headers, or exceptions carrying credentials.
            raise APIError("malformed") from None

    def status(self):
        result = self._request("GET", "/models", timeout=10.0)
        models = result.get("data")
        if not isinstance(models, list):
            raise APIError("inventory")
        available = any(isinstance(m, dict) and m.get("id") == self.model for m in models)
        return {"reachable": True, "model": self.model, "listed": available, "endpoint": self.endpoint}

    @staticmethod
    def _wire_messages(messages):
        outgoing = []
        for message in messages:
            role = message["role"]
            item = {"role": role, "content": message.get("content", "")}
            if role == "tool":
                if not message.get("tool_call_id"):
                    raise ModelError("API tool response is missing its call ID")
                item["tool_call_id"] = message["tool_call_id"]
            if role == "assistant" and message.get("tool_calls"):
                calls = copy.deepcopy(message["tool_calls"])
                for call in calls:
                    call["function"]["arguments"] = json.dumps(call["function"]["arguments"])
                item["tool_calls"] = calls
            outgoing.append(item)
        return outgoing

    def chat(self, messages, *, tools=None, schema=None, timeout=25.0):
        if self.protocol == "responses":
            return self._responses_chat(messages, tools=tools, schema=schema, timeout=timeout)
        payload = {"model": self.model, "messages": self._wire_messages(messages),
                   "stream": False, **self.options}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if schema:
            payload["response_format"] = (
                {"type": "json_schema", "json_schema": {"name": "grounded_selection", "strict": True, "schema": schema}}
                if self.response_format == "json_schema" else {"type": "json_object"})
            # JSON-mode providers still receive the contract and undergo local validation.
            if self.response_format == "json_object":
                payload["messages"] = [{"role": "system", "content": "Return JSON matching this schema: " + json.dumps(schema)}, *payload["messages"]]
        result = self._request("POST", "/chat/completions", payload, timeout=timeout)
        return self._parse_chat_output(result)

    @staticmethod
    def _parse_chat_output(result):
        try:
            choices = result["choices"]
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError("Expected one completion")
            choice = choices[0]
            if choice.get("finish_reason") == "length":
                raise APIError("incomplete")
            if choice.get("finish_reason") == "content_filter":
                raise APIError("refusal")
            if choice.get("finish_reason") not in {"stop", "tool_calls"}:
                raise ValueError("Truncated or refused output")
            message = choice["message"]
            if message.get("refusal"):
                raise APIError("refusal")
            if message.get("role") != "assistant":
                raise ValueError("Invalid role")
            content = message.get("content") or ""
            if not isinstance(content, str):
                raise ValueError("Invalid content")
            calls = message.get("tool_calls") or []
            if not isinstance(calls, list) or len(calls) > 6:
                raise ValueError("Too many or invalid tool calls")
            normalized, seen = [], set()
            for call in calls:
                cid = call["id"]
                if not isinstance(cid, str) or not cid or len(cid) > 200 or cid in seen or call.get("type") != "function":
                    raise ValueError("Invalid tool call")
                function = call["function"]
                args = json.loads(function["arguments"])
                if not isinstance(args, dict) or not isinstance(function["name"], str):
                    raise ValueError("Invalid tool arguments")
                seen.add(cid)
                normalized.append({"id": cid, "type": "function", "function": {"name": function["name"], "arguments": args}})
            return {"role": "assistant", "content": content, "tool_calls": normalized}
        except (KeyError, TypeError, ValueError, AttributeError):
            raise APIError("malformed") from None

    def _responses_chat(self, messages, *, tools=None, schema=None, timeout=25.0):
        inputs = []
        for message in messages:
            if message["role"] == "tool":
                if not message.get("tool_call_id"):
                    raise APIError("malformed")
                inputs.append({"type": "function_call_output", "call_id": message["tool_call_id"],
                               "output": message["content"]})
            elif message["role"] == "assistant" and "_responses_output" in message:
                # Replay all output items, including encrypted reasoning and function calls.
                # These stay within this turn and are never rendered or exported.
                inputs.extend(copy.deepcopy(message["_responses_output"]))
            else:
                inputs.append({"role": message["role"], "content": message.get("content", "")})
        payload = {"model": self.model, "input": inputs, "store": False, "stream": False, **self.options}
        if tools:
            # Preserve optional arguments/defaults; the existing router validates every call.
            payload["tools"] = [{"type": "function", **tool["function"], "strict": False} for tool in tools]
            payload["tool_choice"] = "auto"
        if schema:
            payload["text"] = {"format": ({"type": "json_schema", "name": "grounded_selection",
                                           "schema": schema, "strict": True}
                                          if self.response_format == "json_schema" else {"type": "json_object"})}
            if self.response_format == "json_object":
                inputs.insert(0, {"role": "system", "content": "Return JSON matching this schema: " + json.dumps(schema)})
        result = self._request("POST", "/responses", payload, timeout=timeout)
        try:
            if result.get("status") == "incomplete":
                detail = result.get("incomplete_details") or {}
                raise APIError("incomplete" if detail.get("reason") == "max_output_tokens" else "refusal")
            if result.get("status") == "failed":
                raise APIError("server")
            if result.get("status") != "completed" or result.get("error"):
                raise ValueError("Unfinished response")
            output = result["output"]
            if not isinstance(output, list) or not output:
                raise ValueError("Missing output")
            calls, texts = [], []
            for item in output:
                kind = item["type"]
                if kind == "function_call":
                    calls.append({"id": item["call_id"], "type": "function",
                                  "function": {"name": item["name"], "arguments": item["arguments"]}})
                elif kind == "message":
                    if item.get("role") != "assistant":
                        raise ValueError("Invalid role")
                    for part in item["content"]:
                        if part["type"] == "refusal":
                            raise APIError("refusal")
                        if part["type"] != "output_text" or not isinstance(part["text"], str):
                            raise ValueError("Invalid text")
                        if item.get("phase") != "commentary":
                            texts.append(part["text"])
                elif kind != "reasoning":
                    raise ValueError("Unexpected output item")
            if not calls and not texts:
                raise ValueError("No usable output")
            normalized = self._parse_chat_output({"choices": [{"finish_reason": "tool_calls" if calls else "stop",
                "message": {"role": "assistant", "content": "".join(texts), "tool_calls": calls}}]})
            normalized["_responses_output"] = output
            return normalized
        except (KeyError, TypeError, ValueError, AttributeError):
            raise APIError("malformed") from None

