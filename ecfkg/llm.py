"""Model protocol and deferred Ollama implementation.

The active UI/CLI uses api_llm.OpenAICompatibleAdapter. Ollama is retained for future work.
"""
from __future__ import annotations

import json
import os
import time
from typing import Protocol
from urllib.parse import urlparse

import httpx


class ModelError(RuntimeError):
    pass


class ModelAdapter(Protocol):
    model: str
    endpoint: str
    is_mock: bool

    def chat(self, messages: list[dict], *, tools=None, schema=None, timeout=25.0) -> dict: ...


OPTIONS = {"temperature": 0, "seed": 42, "num_predict": 1024, "num_ctx": 8192}


def local_endpoint(endpoint: str) -> str:
    url = urlparse(endpoint)
    if (url.scheme not in {"http", "https"} or url.hostname not in {"localhost", "127.0.0.1", "::1"}
        or url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}):
        raise ValueError("Model endpoint must be a loopback HTTP(S) origin")
    port = url.port or (443 if url.scheme == "https" else 80)
    host = "[::1]" if url.hostname == "::1" else "127.0.0.1"
    return f"{url.scheme}://{host}:{port}"


class OllamaAdapter:
    is_mock = False

    def __init__(self, model: str | None = None, endpoint: str | None = None, transport=None):
        self.model = model if model is not None else os.environ.get("ECFKG_MODEL", "")
        self.endpoint = local_endpoint(endpoint or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))
        if "cloud" in self.model.casefold() or len(self.model) > 200:
            raise ValueError("Cloud-tagged or invalid model name is not allowed")
        self.transport = transport
        self.metadata: dict = {}

    def _request(self, method: str, path: str, payload=None, timeout=25.0):
        started = time.monotonic()
        try:
            with httpx.Client(trust_env=False, follow_redirects=False, transport=self.transport,
                              timeout=httpx.Timeout(timeout, connect=min(3.0, timeout))) as client:
                with client.stream(method, self.endpoint + path, json=payload) as response:
                    response.raise_for_status()
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > 262144 or time.monotonic() - started > timeout:
                            raise ModelError("Local model response exceeded size or time bound")
            result = json.loads(data)
            if not isinstance(result, dict):
                raise ModelError("Local model returned a non-object response")
            return result
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise ModelError(f"Local model request failed ({type(exc).__name__})") from exc

    def status(self):
        tags = self._request("GET", "/api/tags", timeout=3.0)
        models = tags.get("models")
        if not isinstance(models, list):
            raise ModelError("Malformed local model inventory")
        local = [m for m in models if isinstance(m, dict) and not m.get("remote_host") and not m.get("remote_model")
                 and "cloud" not in str(m.get("name", "")).casefold()]
        return {"reachable": True, "model": self.model, "available": self.model in {m.get("name") for m in local},
                "models": [{"name": m.get("name"), "digest": m.get("digest")} for m in local]}

    def ensure_local_model(self):
        if not self.model:
            raise ModelError("Set ECFKG_MODEL to an already installed local model")
        status = self.status()
        if not status["available"]:
            raise ModelError("Configured local model is not installed; no download attempted")
        details = self._request("POST", "/api/show", {"model": self.model}, timeout=3.0)
        if details.get("remote_host") or details.get("remote_model"):
            raise ModelError("Remote-backed models are disabled")
        self.metadata = next(m for m in status["models"] if m["name"] == self.model)

    def chat(self, messages, *, tools=None, schema=None, timeout=25.0):
        if not self.metadata:
            self.ensure_local_model()
        payload = {"model": self.model, "messages": messages, "stream": False, "options": OPTIONS}
        if tools:
            payload["tools"] = tools
        if schema:
            payload["format"] = schema
        result = self._request("POST", "/api/chat", payload, timeout=timeout)
        message = result.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            raise ModelError("Malformed local model message")
        return message

