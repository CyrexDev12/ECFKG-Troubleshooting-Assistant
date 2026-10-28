"""Offline runner. This module alone handles diagnostic answer keys."""
from __future__ import annotations

import argparse
import csv
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
from statistics import mean
from datetime import datetime, timezone

from pydantic import Field, model_validator

from ecfkg.agent import Agent, EXPLAIN_PROMPT, INTERPRET_PROMPT
from ecfkg.graph import KnowledgeGraph, ROOT
from ecfkg.llm import ModelError
from ecfkg.api_llm import OpenAICompatibleAdapter
from ecfkg.schema import ID, Observation, StrictModel


class EvaluationCase(StrictModel):
    case_id: ID
    category: str
    initial_symptom: str = Field(max_length=2000)
    available_observations: list[Observation]
    expected_root_cause: ID | None
    expected_abstention: bool
    evidence_basis: str
    source_ids: list[ID]
    expected_useful_checks: list[ID]

    @model_validator(mode="after")
    def answer(self):
        if (self.expected_root_cause is None) != self.expected_abstention:
            raise ValueError("Specify a root cause or expected abstention, not both")
        return self


def load_cases(path: Path, graph: KnowledgeGraph):
    cases = [EvaluationCase.model_validate(c) for c in json.loads(path.read_text(encoding="utf-8"))]
    if len({c.case_id for c in cases}) != len(cases):
        raise ValueError("Duplicate evaluation case ID")
    for c in cases:
        if not set(c.source_ids) <= graph.sources.keys() or not set(c.expected_useful_checks) <= graph.checks.keys():
            raise ValueError("Unknown evaluation source or check")
        if c.expected_root_cause and c.expected_root_cause not in {r.fault_id for r in graph.rules.values()}:
            raise ValueError("Unknown evaluation answer")
        for o in c.available_observations:
            if o.check_id not in graph.checks or o.outcome not in graph.checks[o.check_id].outcomes:
                raise ValueError("Invalid evaluation observation")
    return cases


def code_hash():
    return hashlib.sha256(b"".join(p.name.encode() + p.read_bytes() for p in sorted((ROOT / "ecfkg").glob("*.py")))).hexdigest()


def evaluate(cases_path: Path, mode: str = "baseline", include_scenarios: bool = True, adapter=None):
    graph = KnowledgeGraph(include_scenarios=include_scenarios)
    cases = load_cases(cases_path, graph)
    config = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "mode": mode,
              "include_scenarios": include_scenarios, "graph_version": graph.knowledge.version,
              "data_sha256": graph.data_hash, "cases_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
              "code_sha256": code_hash(), "python": platform.python_version(),
              "dependencies": {p: version(p) for p in ["streamlit", "networkx", "pydantic", "httpx", "pytest"]},
              "prompts": {"interpret": INTERPRET_PROMPT, "explain": EXPLAIN_PROMPT},
              "mock": bool(adapter and adapter.is_mock), "candidate_cap": 3,
              "evaluation_design": "Developer-created synthetic cases; not independent validation"}
    if mode not in {"baseline", "api", "llm"}:
        raise ValueError("Evaluation mode must be baseline or api")
    if mode in {"api", "llm"}:
        try:
            adapter = adapter or OpenAICompatibleAdapter()
            config.update(model=adapter.model, endpoint=adapter.endpoint)
            if isinstance(adapter, OpenAICompatibleAdapter):
                adapter.ensure_configured()
            config["model_metadata"] = getattr(adapter, "metadata", {})
        except (ModelError, ValueError) as exc:
            return {"status": "not_run", "reason": str(exc), "config": config,
                    "cases": [c.model_dump() for c in cases], "results": [], "metrics": None}
    agent = Agent(graph, adapter if mode in {"api", "llm"} else None)
    results = []
    for case in cases:
        # The only inputs crossing into the agent: symptom and observations. No IDs or answers.
        turns = [agent.run(case.initial_symptom, [])]
        for i in range(1, len(case.available_observations) + 1):
            turns.append(agent.run(case.initial_symptom, case.available_observations[:i]))
        final = turns[-1].assessment
        faults = [c.fault_id for c in final.candidates]
        references = [(eid, eid in graph.edges or eid in graph.sources) for eid in final.evidence_ids]
        results.append({"case_id": case.case_id, "category": case.category, "status": final.status,
                        "expected_root_cause": case.expected_root_cause, "expected_abstention": case.expected_abstention,
                        "returned_faults": faults, "candidate_count": len(faults),
                        "top1": bool(case.expected_root_cause and faults and faults[0] == case.expected_root_cause),
                        "top3": bool(case.expected_root_cause and case.expected_root_cause in faults[:3]),
                        "appropriate_abstention": case.expected_abstention and final.status == "abstain",
                        "initial_useful_check": turns[0].assessment.next_check in case.expected_useful_checks,
                        "reference_count": len(references), "valid_references": sum(ok for _, ok in references),
                        "documented_candidates": sum(c.basis == "verified_public" for c in final.candidates),
                        "synthetic_candidates": sum(c.basis == "synthetic_demo" for c in final.candidates),
                        "latency_ms": sum(t.elapsed_ms for t in turns), "turn_count": len(turns),
                        "turns": [t.model_dump() for t in turns]})
    applicable = [r for r in results if r["expected_root_cause"]]
    unknown = [r for r in results if r["expected_abstention"]]
    candidate_count = sum(r["candidate_count"] for r in results)
    refs = sum(r["reference_count"] for r in results)
    ratio = lambda numerator, denominator: numerator / denominator if denominator else None
    metrics = {
        "case_count": len(results), "applicable_count": len(applicable), "abstention_case_count": len(unknown),
        "scope_candidate_coverage": ratio(sum(r["top3"] for r in applicable), len(applicable)),
        "top1_accuracy": ratio(sum(r["top1"] for r in applicable), len(applicable)),
        "top3_coverage": ratio(sum(r["top3"] for r in applicable), len(applicable)),
        "average_candidate_list_size": mean(r["candidate_count"] for r in results),
        "average_candidate_list_size_applicable": mean(r["candidate_count"] for r in applicable) if applicable else None,
        "appropriate_abstention_rate": ratio(sum(r["appropriate_abstention"] for r in unknown), len(unknown)),
        "citation_reference_validity": ratio(sum(r["valid_references"] for r in results), refs),
        "documentation_backed_evidence_coverage": ratio(sum(r["documented_candidates"] for r in results), candidate_count),
        "synthetic_evidence_coverage": ratio(sum(r["synthetic_candidates"] for r in results), candidate_count),
        "mean_case_latency_ms": mean(r["latency_ms"] for r in results),
        "mean_turn_latency_ms": sum(r["latency_ms"] for r in results) / sum(r["turn_count"] for r in results),
        "model_error_count": sum(r["status"] == "model_error" for r in results),
        "estimated_troubleshooting_time_reduction": None, "measured_troubleshooting_time_reduction": None,
    }
    metrics["scope_80_percent_threshold_met_on_this_suite"] = metrics["scope_candidate_coverage"] >= 0.8 if applicable else None
    return {"status": "completed", "config": config, "cases": [c.model_dump() for c in cases], "results": results, "metrics": metrics}


def save_report(report, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    columns = ["case_id", "category", "status", "expected_root_cause", "expected_abstention", "returned_faults",
               "candidate_count", "top1", "top3", "appropriate_abstention", "initial_useful_check", "reference_count", "valid_references", "latency_ms"]
    with (out / "results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({**r, "returned_faults": ", ".join(r["returned_faults"])} for r in report["results"])
    (out / "cases.json").write_text(json.dumps(report["cases"], indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=ROOT / "data/evaluation/cases.json")
    parser.add_argument("--out", type=Path, default=ROOT / "outputs/baseline")
    parser.add_argument("--mode", choices=["baseline", "api", "llm"], default="baseline", help="llm is a compatibility alias for api; local hosting is deferred")
    parser.add_argument("--theory-only", action="store_true")
    args = parser.parse_args()
    report = evaluate(args.cases, args.mode, not args.theory_only)
    save_report(report, args.out)
    print(json.dumps({"status": report["status"], "reason": report.get("reason"), "metrics": report["metrics"]}, indent=2))


if __name__ == "__main__":
    main()

