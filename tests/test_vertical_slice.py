import json

import pytest

from ecfkg.diagnostics import assess, interpret_baseline
from ecfkg.graph import KnowledgeGraph
from ecfkg.schema import Observation
from ecfkg.simulator import Simulator


@pytest.fixture
def graph():
    return KnowledgeGraph()


def test_first_workflow_and_reversal(graph):
    sim = Simulator("SUPPLY")
    interp = interpret_baseline(sim.symptom(), graph)
    first = assess(graph, interp, [])
    assert first.status == "needs_observations"
    assert first.eligible_count == 5 and len(first.candidates) == 3
    assert first.next_check == "CHECK_SUPPLY"
    result = assess(graph, interp, [sim.check(first.next_check)])
    assert result.candidates[0].fault_id == "F_SUPPLY"
    assert result.status == "candidate_identified"
    route = Simulator("ROUTE")
    normal_supply = assess(graph, interp, [route.check("CHECK_SUPPLY")])
    assert normal_supply.next_check == "CHECK_ROUTE"
    assert assess(graph, interp, [route.check("CHECK_SUPPLY"), route.check("CHECK_ROUTE")]).candidates[0].fault_id == "F_ROUTE"


@pytest.mark.parametrize("preset", ["SUPPLY", "ROUTE", "LEAD", "DMM", "RESOURCE", "SEQUENCE"])
def test_all_faults_converge_without_hidden_input(graph, preset):
    sim = Simulator(preset)
    interp = interpret_baseline(sim.symptom(), graph)
    observations = []
    for _ in range(7):
        result = assess(graph, interp, observations)
        if result.status == "candidate_identified":
            break
        assert result.next_check
        observations.append(sim.check(result.next_check))
    assert result.candidates[0].fault_id == f"F_{preset}"


def test_shared_symptom_and_physical_edges_not_causal(graph):
    assert len({Simulator(p).symptom() for p in ["SUPPLY", "ROUTE", "LEAD", "DMM", "SEQUENCE"]}) == 1
    assert all(e["type"] != "CONNECTED_TO" for p in graph.get_dependency_paths("C_DMM") for e in p)
    assert not graph.get_candidate_faults([], ["C_DMM"])


def test_candidate_retrieval_requires_causal_graph_path(graph):
    import networkx as nx
    assert "F_SUPPLY" in {r["fault_id"] for r in graph.get_candidate_faults(["S_ZERO"], [])}
    graph.graph = nx.MultiDiGraph(graph.graph)
    graph.graph.remove_edge("F_SUPPLY", "COND_SUPPLY", "E_CAUSE_SUPPLY_1")
    assert "F_SUPPLY" not in {r["fault_id"] for r in graph.get_candidate_faults(["S_ZERO"], [])}


def test_duplicate_observations_and_incompatible_symptoms(graph):
    obs = Observation(check_id="CHECK_SUPPLY", outcome="normal")
    interp = interpret_baseline("DMM near zero", graph)
    assert assess(graph, interp, [obs]) == assess(graph, interp, [obs, obs])
    assert assess(graph, interpret_baseline("DMM near zero and a timeout", graph), []).status == "abstain"


def test_conflicts_unknown_and_out_of_scope(graph):
    interp = interpret_baseline(Simulator().symptom(), graph)
    assert assess(graph, interp, [Observation(check_id="CHECK_SUPPLY", outcome="normal"),
                                  Observation(check_id="CHECK_SUPPLY", outcome="output_disabled")]).status == "abstain"
    assert assess(graph, interp, [Observation(check_id="CHECK_SUPPLY", outcome="unknown")]).eligible_count == 5
    assert assess(graph, interpret_baseline("Diagnose ADCP II internals", graph), []).status == "abstain"
    with pytest.raises(ValueError):
        assess(graph, interp, [Observation(check_id="CHECK_SUPPLY", outcome="invented")])


def test_scenarios_do_not_change_ranking(graph):
    interp = interpret_baseline(Simulator().symptom(), graph)
    observation = [Observation(check_id="CHECK_SUPPLY", outcome="output_disabled")]
    theory = assess(KnowledgeGraph(include_scenarios=False), interp, observation)
    enriched = assess(graph, interp, observation)
    assert [c.fault_id for c in theory.candidates] == [c.fault_id for c in enriched.candidates]
    assert enriched.candidates[0].reference_case_ids == ["DEV_SUPPLY_REFERENCE"]
    assert not theory.candidates[0].reference_case_ids


@pytest.mark.parametrize("mutation", ["duplicate", "source", "endpoint", "path", "type", "url", "pending", "prediction"])
def test_graph_rejects_corruption(tmp_path, graph, mutation):
    knowledge = graph.knowledge.model_dump()
    sources = [s.model_dump() for s in graph.sources.values()]
    if mutation == "duplicate": knowledge["nodes"].append(knowledge["nodes"][0])
    if mutation == "source": knowledge["rules"][0]["source_ids"] = ["MISSING"]
    if mutation == "endpoint": knowledge["edges"][0]["target"] = "MISSING"
    if mutation == "path": knowledge["rules"][0]["path_edge_ids"] = [knowledge["edges"][0]["id"]]
    if mutation == "type": knowledge["edges"][0]["type"] = "MAGIC"
    if mutation == "url": sources[0]["reference"] = "file:///etc/passwd"
    if mutation == "pending": sources[0]["review_status"] = "pending"
    if mutation == "prediction": knowledge["rules"][0]["predictions"]["CHECK_SUPPLY"] = "made_up"
    (tmp_path / "graph.json").write_text(json.dumps(knowledge))
    (tmp_path / "sources.json").write_text(json.dumps(sources))
    with pytest.raises(ValueError): KnowledgeGraph(tmp_path)

