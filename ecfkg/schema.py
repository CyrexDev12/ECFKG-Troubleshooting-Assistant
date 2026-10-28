"""Closed schemas shared by loading, diagnostic inputs and tool boundaries."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

ID = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{1,79}$")]
Basis = Literal["synthetic_demo", "engineering_assumption", "verified_public"]
KnowledgeStatus = Literal["draft", "synthetic", "reviewed"]
NODE_LAYERS = {"component": "physical", "interface": "physical", "software": "physical",
               "configuration": "physical", "function": "functional", "measurement": "functional",
               "condition": "causal", "fault": "causal", "symptom": "causal", "check": "diagnostic",
               "case": "scenario", "source": "evidence"}
PHYSICAL = {"component", "interface", "software", "configuration"}
FUNCTIONAL = PHYSICAL | {"function", "measurement"}
EDGE_TYPES = ["CONNECTED_TO", "HAS_COMPONENT", "CONTROLS", "DEPENDS_ON", "PERFORMS", "MEASURES",
              "PRODUCES", "CONSUMES", "FLOWS_TO", "AFFECTS", "CAUSES", "CHECKS", "EXEMPLIFIES", "SUPPORTED_BY"]


def compatible(edge_type: str, source_type: str, target_type: str) -> bool:
    pairs = {
        "CONNECTED_TO": (PHYSICAL, PHYSICAL), "HAS_COMPONENT": (PHYSICAL, PHYSICAL),
        "CONTROLS": (PHYSICAL, FUNCTIONAL), "DEPENDS_ON": (FUNCTIONAL, FUNCTIONAL),
        "PERFORMS": (PHYSICAL, {"function"}), "MEASURES": (PHYSICAL, {"measurement"}),
        "PRODUCES": (FUNCTIONAL, {"measurement", "function"}),
        "CONSUMES": (FUNCTIONAL, {"measurement", "function"}), "FLOWS_TO": (FUNCTIONAL, FUNCTIONAL),
        "AFFECTS": ({"fault"}, PHYSICAL), "CHECKS": ({"check"}, {"fault"}),
        "EXEMPLIFIES": ({"case"}, {"fault"}), "SUPPORTED_BY": (set(NODE_LAYERS), {"source"}),
    }
    if edge_type == "CAUSES":
        return (source_type in {"fault", "condition"} and target_type in {"condition", "symptom"})
    allowed = pairs.get(edge_type)
    return bool(allowed and source_type in allowed[0] and target_type in allowed[1])


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Source(StrictModel):
    id: ID
    title: str
    publisher: str
    reference: str
    section: str
    paraphrase: str
    access_date: str
    basis: Basis
    review_status: Literal["pending", "approved", "synthetic_unreviewed"]
    permitted_use: str
    approval_record: str | None = None

    @model_validator(mode="after")
    def valid_metadata(self):
        date.fromisoformat(self.access_date)
        if self.reference.startswith("https://"):
            url = urlparse(self.reference)
            _ = url.port  # Reject malformed ports as well as malformed hostnames.
            if not url.hostname or url.username or url.password or any(c.isspace() for c in self.reference):
                raise ValueError("Invalid source URL")
        elif not self.reference.startswith("docs/") or ".." in self.reference:
            raise ValueError("Source requires HTTPS URL or approved docs/ reference")
        if self.basis == "verified_public" and (
            self.review_status != "approved" or not self.approval_record
        ):
            raise ValueError("Public evidence needs explicit approval record")
        if not all([self.section.strip(), self.paraphrase.strip(), self.permitted_use.strip()]):
            raise ValueError("Incomplete source provenance")
        return self


class Node(StrictModel):
    id: ID
    type: Literal["component", "interface", "software", "configuration", "function",
                  "measurement", "condition", "fault", "symptom", "check", "case", "source"]
    layer: Literal["physical", "functional", "causal", "diagnostic", "scenario", "evidence"]
    knowledge: Literal["theory", "scenario"] = "theory"
    label: str
    description: str
    aliases: list[str] = Field(default_factory=list)
    source_ids: list[ID] = Field(min_length=1)
    properties: dict[str, str] = Field(default_factory=dict)
    status: KnowledgeStatus = "synthetic"


class Edge(StrictModel):
    id: ID
    source: ID
    target: ID
    type: Literal["CONNECTED_TO", "DEPENDS_ON", "PERFORMS", "MEASURES", "AFFECTS",
                  "CAUSES", "CHECKS", "EXEMPLIFIES", "SUPPORTED_BY", "HAS_COMPONENT", "CONTROLS",
                  "PRODUCES", "CONSUMES", "FLOWS_TO"]
    basis: Basis
    source_ids: list[ID] = Field(min_length=1)
    condition: str | None = None
    rule_id: ID | None = None
    description: str = ""
    status: KnowledgeStatus = "synthetic"


class Check(StrictModel):
    id: ID
    label: str
    instructions: str
    outcomes: dict[str, str]
    source_ids: list[ID] = Field(min_length=1)


class Rule(StrictModel):
    id: ID
    fault_id: ID
    component_id: ID
    symptom_ids: list[ID] = Field(min_length=1)
    conditions: list[str] = Field(min_length=1)
    predictions: dict[str, str]
    path_edge_ids: list[ID] = Field(min_length=1)
    basis: Basis
    source_ids: list[ID] = Field(min_length=1)


class Knowledge(StrictModel):
    version: str
    nodes: list[Node]
    edges: list[Edge]
    checks: list[Check]
    rules: list[Rule]


class Observation(StrictModel):
    check_id: ID
    outcome: Annotated[str, Field(min_length=1, max_length=80)]
    origin: Literal["user", "simulator"] = "user"


class Interpretation(StrictModel):
    symptom_ids: list[ID] = Field(default_factory=list, max_length=3)
    component_ids: list[ID] = Field(default_factory=list, max_length=8)
    supported: bool


class Candidate(StrictModel):
    fault_id: ID
    description: str
    score: int
    supporting: list[str]
    contradicting: list[str]
    path_edge_ids: list[ID]
    source_ids: list[ID]
    basis: Basis
    uncertainty: str
    suggested_check: str | None
    reference_case_ids: list[ID] = Field(default_factory=list)


class Assessment(StrictModel):
    status: Literal["needs_observations", "candidate_identified", "abstain", "model_error"]
    reason: str
    candidates: list[Candidate]
    next_check: str | None
    eligible_count: int
    truncated: bool
    evidence_ids: list[ID]

