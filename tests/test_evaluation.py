import json

from ecfkg.evaluate import evaluate, load_cases, save_report
from ecfkg.graph import KnowledgeGraph, ROOT


def test_metrics_include_ambiguous_misses_and_unknowns(tmp_path):
    result = evaluate(ROOT / "data/evaluation/cases.json")
    metrics = result["metrics"]
    assert metrics["case_count"] == 20 and metrics["applicable_count"] == 14
    assert metrics["scope_candidate_coverage"] == 12 / 14
    assert metrics["appropriate_abstention_rate"] == 1
    assert metrics["documentation_backed_evidence_coverage"] == 0
    assert metrics["average_candidate_list_size"] < 3
    assert metrics["mean_case_latency_ms"] > 0
    assert metrics["estimated_troubleshooting_time_reduction"] is None
    assert not result["config"]["mock"]
    save_report(result, tmp_path)
    saved = json.loads((tmp_path / "results.json").read_text())
    assert saved["metrics"] == metrics
    assert len((tmp_path / "results.csv").read_text().splitlines()) == 21


def test_case_ids_are_not_in_runtime_retrieval():
    graph = KnowledgeGraph()
    cases = load_cases(ROOT / "data/evaluation/cases.json", graph)
    assert not set(c.case_id for c in cases) & graph.graph.nodes
    assert not graph.find_relevant_entities("EVAL_001")

