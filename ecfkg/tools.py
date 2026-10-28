"""Finite, validated query API exposed to a model. No file or execution tools."""
from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field

from ecfkg.graph import KnowledgeGraph
from ecfkg.schema import ID, StrictModel


class Query(StrictModel):
    query: Annotated[str, Field(min_length=1, max_length=2000)]


class Candidates(StrictModel):
    symptom_ids: list[ID] = Field(max_length=3)
    component_ids: list[ID] = Field(max_length=8)


class Fault(StrictModel):
    fault_id: ID


class Dependency(StrictModel):
    component_id: ID
    max_depth: Annotated[int, Field(ge=1, le=4)] = 3


class Checks(StrictModel):
    candidate_fault_ids: list[ID] = Field(min_length=1, max_length=6)


class SourceQuery(StrictModel):
    source_id: ID


TOOL_MODELS = {
    "find_relevant_entities": (Query, "Find relevant symptom and component IDs from a report."),
    "get_candidate_faults": (Candidates, "Get conditional fault rules for known symptoms. Physical links alone do not imply causes."),
    "get_fault_evidence": (Fault, "Read a fault's conditional causal paths and designated development cases."),
    "get_dependency_paths": (Dependency, "Read bounded functional paths. These are not causal claims."),
    "get_diagnostic_checks": (Checks, "Read synthetic check definitions for retrieved candidate faults."),
    "get_source": (SourceQuery, "Read provenance, basis and review status for a known source ID."),
}


def tool_schemas():
    return [{"type": "function", "function": {"name": name, "description": desc,
             "parameters": model.model_json_schema()}} for name, (model, desc) in TOOL_MODELS.items()]


class ToolRouter:
    def __init__(self, graph: KnowledgeGraph, max_calls: int = 6):
        self.graph = graph
        self.max_calls = min(max_calls, 6)
        self.calls = 0
        self.trace: list[dict] = []

    def invoke(self, name: str, arguments: dict):
        if self.calls >= self.max_calls:
            raise ValueError("Tool call budget exceeded")
        self.calls += 1
        if name not in TOOL_MODELS:
            raise ValueError("Tool not allowlisted")
        validated = TOOL_MODELS[name][0].model_validate(arguments).model_dump()
        for key, value in validated.items():
            if key.endswith("_id") or key.endswith("_ids"):
                for identifier in value if isinstance(value, list) else [value]:
                    if identifier not in self.graph.graph:
                        raise ValueError("Unknown graph identifier")
        # name is validated against a fixed literal allowlist above.
        result = getattr(self.graph, name)(**validated)
        if len(json.dumps(result)) > 24000:
            raise ValueError("Tool result exceeds bounded evidence budget")
        self.trace.append({"tool": name, "arguments": validated, "result": result})
        return result

