"""Mocks exercise protocol/failure handling, never live model performance."""
import copy
import json

import httpx
import pytest
from pydantic import ValidationError

from ecfkg.agent import Agent, export_session
from ecfkg.graph import KnowledgeGraph, ROOT
from ecfkg.llm import ModelError, OllamaAdapter, local_endpoint
from ecfkg.schema import Observation
from ecfkg.tools import ToolRouter


class ScriptedModel:
    model = "software-test-mock"
    endpoint = "mock://no-network"
    is_mock = True

    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def chat(self, messages, **kwargs):
        self.requests.append(copy.deepcopy(messages))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def call(name, args):
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}


def content(value):
    return {"role": "assistant", "content": json.dumps(value)}


def good_responses():
    return [call("find_relevant_entities", {"query": "DMM near zero"}),
            call("get_candidate_faults", {"symptom_ids": ["S_ZERO"], "component_ids": ["C_DMM"]}),
            content({"symptom_ids": ["S_ZERO"], "component_ids": ["C_DMM"], "supported": True}),
            content({"fault_ids": ["F_SUPPLY"], "evidence_ids": ["E_CAUSE_SUPPLY_1"], "next_check": None})]


def test_mock_tool_workflow_grounded_selection():
    model = ScriptedModel(good_responses())
    turn = Agent(KnowledgeGraph(), model).run("DMM near zero", [Observation(check_id="CHECK_SUPPLY", outcome="output_disabled")])
    assert turn.assessment.status == "candidate_identified"
    assert turn.model_selection.fault_ids == ["F_SUPPLY"]
    assert turn.config["mock"] is True
    assert len(turn.trace) == 2
    assert "station.json" not in json.dumps(model.requests)
    assert "expected_root" not in export_session([turn])


@pytest.mark.parametrize("responses", [
    [{"role": "assistant", "content": "broken json"}],
    [ModelError("unavailable")],
    [call("execute_python", {"code": "print('unsafe')"})],
    [content({"symptom_ids": ["S_FAKE"], "component_ids": [], "supported": True})],
    good_responses()[:-1] + [content({"fault_ids": ["F_SUPPLY"], "evidence_ids": ["INVENTED_SOURCE"], "next_check": None})],
    good_responses()[:-1] + [content({"fault_ids": ["F_SUPPLY"], "evidence_ids": ["SRC_MODEL"], "next_check": None, "confidence": 99})],
    [call("find_relevant_entities", {"query": "DMM near zero"})] * 7,
])
def test_model_errors_do_not_fallback(responses):
    model = ScriptedModel(responses)
    result = Agent(KnowledgeGraph(), model).run("DMM near zero", [Observation(check_id="CHECK_SUPPLY", outcome="output_disabled")])
    assert result.assessment.status == "model_error"
    assert not result.assessment.candidates
    assert result.mode == "llm"


def test_tool_bounds_and_source_immutability():
    graph = KnowledgeGraph()
    router = ToolRouter(graph)
    with pytest.raises(ValidationError): router.invoke("get_dependency_paths", {"component_id": "C_DMM", "max_depth": 999})
    with pytest.raises(ValueError): router.invoke("get_source", {"source_id": "MISSING"})
    source = router.invoke("get_source", {"source_id": "SRC_MODEL"})
    source["title"] = "Mutated return"
    assert graph.sources["SRC_MODEL"].title != source["title"]
    with pytest.raises(ValidationError): router.invoke("find_relevant_entities", {"query": "x", "path": "private/file"})
    router.invoke("find_relevant_entities", {"query": "near zero"})
    router.invoke("find_relevant_entities", {"query": "near zero"})
    with pytest.raises(ValueError): router.invoke("find_relevant_entities", {"query": "near zero"})


@pytest.mark.parametrize("url", ["https://example.com", "http://127.0.0.1.evil.com", "http://user:pass@localhost:11434", "http://localhost:11434/api", "file:///tmp/model", "http://10.0.0.1:11434"])
def test_remote_endpoints_rejected(url):
    with pytest.raises(ValueError): local_endpoint(url)


@pytest.mark.parametrize("failure", ["timeout", "malformed", "redirect", "oversized", "cloud"])
def test_http_failures(failure):
    def handler(request):
        if failure == "timeout": raise httpx.ReadTimeout("test timeout")
        if failure == "malformed": return httpx.Response(200, content="not json")
        if failure == "redirect": return httpx.Response(302, headers={"Location": "https://example.com"})
        if failure == "oversized": return httpx.Response(200, content="x" * 262145)
        if request.url.path == "/api/tags": return httpx.Response(200, json={"models": [{"name": "local-test"}]})
        return httpx.Response(200, json={"remote_host": "example.com", "remote_model": "remote"})
    adapter = OllamaAdapter("local-test", transport=httpx.MockTransport(handler))
    with pytest.raises(ModelError): adapter.ensure_local_model()


def test_hidden_answer_boundary_and_export():
    graph = KnowledgeGraph()
    assert not any(n.id.startswith("EVAL_") for n in graph.nodes.values())
    for module in ["agent.py", "graph.py", "tools.py", "diagnostics.py", "llm.py"]:
        text = (ROOT / "ecfkg" / module).read_text()
        assert "data/evaluation" not in text and "Simulator" not in text.replace("Simulator object", "")
    a = Agent(graph).run("DMM near zero", [])
    b = Agent(graph).run("DMM near zero", [])
    assert a.assessment == b.assessment
    exported = json.loads(export_session([a]))
    assert "preset" not in exported and "hidden_fault" not in json.dumps(exported)

