"""Regression for GPT-6.1 Sol tool calling: Responses, not Chat Completions."""
import json

import httpx
import pytest

from ecfkg.agent import Agent, export_session
from ecfkg.api_llm import APIError, OpenAICompatibleAdapter, resolve_protocol
from ecfkg.graph import KnowledgeGraph
from ecfkg.schema import Observation

KEY = "test-only-key"


def function(cid, name, args):
    return {"type": "function_call", "id": "fc_" + cid, "call_id": cid,
            "name": name, "arguments": json.dumps(args), "status": "completed"}


def message(value, phase="final_answer"):
    return {"type": "message", "id": "msg_" + phase, "role": "assistant", "phase": phase,
            "status": "completed", "content": [{"type": "output_text", "text": value, "annotations": []}]}


def test_sol_complete_tool_exchange_preserves_context_without_exporting_it():
    reasoning = {"id": "rs_1", "type": "reasoning", "summary": [], "encrypted_content": "opaque-test-context"}
    outputs = iter([
        [reasoning, function("call_find", "find_relevant_entities", {"query": "DMM near zero"})],
        [function("call_candidates", "get_candidate_faults", {"symptom_ids": ["S_ZERO"], "component_ids": ["C_DMM"]})],
        [message("I have retrieved the evidence.", "commentary"),
         message(json.dumps({"symptom_ids": ["S_ZERO"], "component_ids": ["C_DMM"], "supported": True}))],
        [message(json.dumps({"fault_ids": ["F_SUPPLY"], "evidence_ids": ["E_CAUSE_SUPPLY_1"], "next_check": None}))],
    ])
    requests = []

    def handler(request):
        assert str(request.url) == "https://api.openai.com/v1/responses"
        assert request.headers["Authorization"] == "Bearer " + KEY
        body = json.loads(request.content)
        assert body["model"] == "gpt-6.1-sol"
        assert body["store"] is False and body["stream"] is False
        assert body["reasoning"] == {"effort": "low"}
        assert body["max_output_tokens"] == 4096
        assert KEY not in request.content.decode()
        assert "messages" not in body and "response_format" not in body
        if len(requests) == 1:
            assert body["input"][2] == reasoning
            assert body["input"][3]["type"] == "function_call"
            assert body["input"][4]["call_id"] == "call_find"
            assert body["input"][4]["type"] == "function_call_output"
        if len(requests) == 2:
            assert [i["call_id"] for i in body["input"] if i.get("type") == "function_call_output"] == ["call_find", "call_candidates"]
        if len(requests) < 3:
            assert len(body["tools"]) == 6
            assert all(t["type"] == "function" and "function" not in t and t["strict"] is False for t in body["tools"])
        else:
            assert "tools" not in body
            assert body["text"]["format"]["strict"] is True
            assert len(body["input"]) == 2  # Explanation uses its own assessment context.
        requests.append(body)
        return httpx.Response(200, json={"status": "completed", "output": next(outputs)})

    adapter = OpenAICompatibleAdapter("gpt-6.1-sol", "https://api.openai.com/v1", KEY,
                                      transport=httpx.MockTransport(handler))
    adapter.is_mock = True
    agent = Agent(KnowledgeGraph(), adapter)
    turn = agent.run("DMM near zero", [Observation(check_id="CHECK_SUPPLY", outcome="output_disabled")])
    assert turn.assessment.status == "candidate_identified"
    assert len(requests) == 4 and turn.config["llm_inference_requests"] == 4
    assert turn.config["model_metadata"]["provider_protocol"] == "responses"
    exported = export_session([turn])
    assert KEY not in exported and "opaque-test-context" not in exported and "_responses_output" not in exported


@pytest.mark.parametrize("status,code,param,expected", [
    (400, "unsupported_parameter", "tools", "Responses"),
    (400, "unsupported_value", "response_format", "output format"),
    (401, "invalid_api_key", None, "authentication failed"),
    (403, None, None, "access denied"),
    (404, "model_not_found", None, "model or route"),
    (429, "insufficient_quota", None, "quota is exhausted"),
    (429, "rate_limit_exceeded", None, "rate limit"),
    (500, None, None, "service failed"),
])
def test_actionable_errors_reach_agent_without_provider_text(status, code, param, expected):
    adapter = OpenAICompatibleAdapter("gpt-6.1-sol", "https://api.openai.com/v1", KEY,
        transport=httpx.MockTransport(lambda r: httpx.Response(status, json={"error": {
            "code": code, "param": param, "message": "Do not expose " + KEY}})))
    turn = Agent(KnowledgeGraph(), adapter).run("DMM near zero", [])
    assert turn.assessment.status == "model_error"
    assert expected in turn.assessment.reason and str(status) in turn.assessment.reason
    assert not turn.assessment.candidates and KEY not in export_session([turn])


@pytest.mark.parametrize("response,code", [
    ({"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}}, "incomplete"),
    ({"status": "failed", "error": {"message": KEY}}, "server"),
    ({"status": "completed", "output": []}, "malformed"),
    ({"status": "completed", "output": [{"type": "shell_call"}]}, "malformed"),
    ({"status": "completed", "output": [function("x", "find_relevant_entities", {})] * 2}, "malformed"),
    ({"status": "completed", "output": [{"type": "message", "role": "assistant", "content": [{"type": "refusal", "refusal": KEY}]}]}, "refusal"),
])
def test_bad_responses_remain_bounded_and_safe(response, code):
    adapter = OpenAICompatibleAdapter("gpt-6.1-sol", "https://api.openai.com/v1", KEY,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=response)))
    with pytest.raises(APIError) as error:
        adapter.chat([{"role": "user", "content": "Synthetic observation"}])
    assert error.value.code == code and KEY not in str(error.value)


def test_protocol_selection_and_responses_json_mode():
    assert resolve_protocol("https://api.openai.com/v1") == "responses"
    assert resolve_protocol("https://provider.example/v1") == "chat_completions"
    assert resolve_protocol("https://api.openai.com/v1", "chat_completions") == "chat_completions"
    assert resolve_protocol("https://[broken") == "chat_completions"
    def handler(request):
        assert request.url.path == "/v1/responses"
        body = json.loads(request.content)
        assert body["text"]["format"] == {"type": "json_object"}
        assert "schema" in body["input"][0]["content"]
        return httpx.Response(200, json={"status": "completed", "output": [message("{}") ]})
    adapter = OpenAICompatibleAdapter("test", "https://provider.example/v1", KEY, "json_object",
                                      transport=httpx.MockTransport(handler), protocol="responses")
    assert adapter.chat([{"role": "user", "content": "Return JSON"}], schema={"type": "object"})["content"] == "{}"
