"""Mock HTTP tests verify the API contract; no paid/live provider calls."""
import json

import httpx
import pytest

from ecfkg.agent import Agent, export_session
from ecfkg.api_llm import OpenAICompatibleAdapter, api_endpoint
from ecfkg.graph import KnowledgeGraph
from ecfkg.llm import ModelError
from ecfkg.schema import Observation

KEY = "test-key-not-a-real-credential"


def completion(content=None, calls=None, finish=None):
    return {"choices": [{"finish_reason": finish or ("tool_calls" if calls else "stop"),
                         "message": {"role": "assistant", "content": content, "tool_calls": calls}}]}


def tool_call(cid, name, args):
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def test_api_end_to_end_tool_ids_structured_output_and_secret_separation():
    requests = []
    responses = iter([
        completion(calls=[tool_call("call_find", "find_relevant_entities", {"query": "DMM near zero"})]),
        completion(calls=[tool_call("call_candidates", "get_candidate_faults", {"symptom_ids": ["S_ZERO"], "component_ids": ["C_DMM"]})]),
        completion(json.dumps({"symptom_ids": ["S_ZERO"], "component_ids": ["C_DMM"], "supported": True})),
        completion(json.dumps({"fault_ids": ["F_SUPPLY"], "evidence_ids": ["E_CAUSE_SUPPLY_1"], "next_check": None})),
    ])

    def handler(request):
        assert request.url == "https://provider.example/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer " + KEY
        body = json.loads(request.content)
        assert KEY not in request.content.decode()
        requests.append(body)
        return httpx.Response(200, json=next(responses))

    adapter = OpenAICompatibleAdapter("test-model", "https://provider.example/v1", KEY,
                                      transport=httpx.MockTransport(handler))
    adapter.is_mock = True
    turn = Agent(KnowledgeGraph(), adapter).run("DMM near zero", [Observation(check_id="CHECK_SUPPLY", outcome="output_disabled")])
    assert turn.assessment.status == "candidate_identified" and turn.mode == "api"
    assert turn.config["mock"] and turn.config["llm_inference_requests"] == 4
    assert turn.config["options"] == {"max_completion_tokens": 2048}
    assert KEY not in export_session([turn]) and KEY not in repr(adapter)
    tool_responses = [m for m in requests[2]["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_responses] == ["call_find", "call_candidates"]
    assert all("tool_name" not in m for m in tool_responses)
    assert isinstance(requests[1]["messages"][2]["tool_calls"][0]["function"]["arguments"], str)
    assert requests[-1]["response_format"]["json_schema"]["strict"] is True
    assert "tools" not in requests[-1]


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500, 302])
def test_api_http_errors_are_safe_and_do_not_follow_redirects(status):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(status, text="Provider echoes secret: " + KEY, headers={"Location": "https://unintended.example"})
    adapter = OpenAICompatibleAdapter("test", "https://provider.example/v1", KEY, transport=httpx.MockTransport(handler))
    with pytest.raises(ModelError) as exc:
        adapter.status()
    assert KEY not in str(exc.value)
    assert len(seen) == 1


@pytest.mark.parametrize("response", [
    {"choices": []}, completion("partial", finish="length"),
    completion(calls=[{"id": "c", "type": "function", "function": {"name": "x", "arguments": "broken"}}]),
    completion(calls=[tool_call("same", "x", {}), tool_call("same", "x", {})]),
    {"choices": [{"finish_reason": "stop", "message": None}]},
])
def test_api_malformed_output_abstains_without_baseline_fallback(response):
    adapter = OpenAICompatibleAdapter("test", "https://provider.example/v1", KEY,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=response)))
    turn = Agent(KnowledgeGraph(), adapter).run("DMM near zero", [])
    assert turn.assessment.status == "model_error" and not turn.assessment.candidates


def test_compatible_json_mode_and_model_inventory():
    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "test"}]})
        body = json.loads(request.content)
        assert body["max_tokens"] == 2048 and "max_completion_tokens" not in body
        assert body["response_format"] == {"type": "json_object"}
        assert "schema" in body["messages"][0]["content"]
        return httpx.Response(200, json=completion('{}'))
    adapter = OpenAICompatibleAdapter("test", "https://provider.example/v1", KEY, "json_object", "max_tokens",
                                      transport=httpx.MockTransport(handler))
    assert adapter.status()["listed"]
    assert adapter.chat([{"role": "user", "content": "Return JSON"}], schema={"type": "object"})["content"] == '{}'


@pytest.mark.parametrize("endpoint", ["http://provider.example/v1", "https://key@provider.example/v1", "https://provider.example/v1?key=secret", "https://provider.example/v1#key", "https://provider.example/v1/chat/completions", "https://provider.example:bad/v1"])
def test_api_rejects_unsafe_or_incorrect_base_urls(endpoint):
    with pytest.raises(ValueError): api_endpoint(endpoint)


@pytest.mark.parametrize("failure", ["timeout", "size", "json"])
def test_api_request_limits(failure):
    def handler(request):
        if failure == "timeout": raise httpx.ReadTimeout("contains " + KEY)
        return httpx.Response(200, content="x" * (262145 if failure == "size" else 10))
    adapter = OpenAICompatibleAdapter("test", "https://provider.example/v1", KEY, transport=httpx.MockTransport(handler))
    with pytest.raises(ModelError) as exc: adapter.status()
    assert KEY not in str(exc.value)


def test_missing_key_makes_no_network_request(monkeypatch):
    monkeypatch.delenv("ECFKG_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    def forbidden(request):
        pytest.fail("Missing configuration must fail before networking")
    adapter = OpenAICompatibleAdapter("test", "https://provider.example/v1", transport=httpx.MockTransport(forbidden))
    with pytest.raises(ModelError): adapter.status()

