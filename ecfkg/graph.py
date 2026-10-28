"""Validated JSON storage and bounded read-only graph retrieval."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import networkx as nx

from ecfkg.schema import Knowledge, Source

ROOT = Path(__file__).resolve().parents[1]


class KnowledgeGraph:
    def __init__(self, data_dir: Path | None = None, include_scenarios: bool = True):
        data_dir = data_dir or ROOT / "data" / "runtime"
        graph_bytes = (data_dir / "graph.json").read_bytes()
        source_bytes = (data_dir / "sources.json").read_bytes()
        self.data_hash = hashlib.sha256(graph_bytes + source_bytes).hexdigest()
        self.knowledge = Knowledge.model_validate_json(graph_bytes)
        sources = [Source.model_validate(s) for s in json.loads(source_bytes)]
        self.sources = self._unique(sources)
        self.nodes = self._unique(self.knowledge.nodes)
        self.edges = self._unique(self.knowledge.edges)
        self.checks = self._unique(self.knowledge.checks)
        self.rules = self._unique(self.knowledge.rules)
        self._validate()
        self.include_scenarios = include_scenarios
        self.graph = nx.MultiDiGraph()
        for n in self.nodes.values():
            if include_scenarios or n.knowledge != "scenario":
                self.graph.add_node(n.id, **n.model_dump())
        for e in self.edges.values():
            if e.source in self.graph and e.target in self.graph:
                self.graph.add_edge(e.source, e.target, key=e.id, **e.model_dump())
        nx.freeze(self.graph)

    @staticmethod
    def _unique(items):
        result = {item.id: item for item in items}
        if len(result) != len(items):
            raise ValueError("Duplicate ID")
        return result

    def _validate(self):
        layers = {"component": "physical", "interface": "physical", "software": "physical",
                  "configuration": "physical", "function": "functional", "measurement": "functional",
                  "condition": "causal", "fault": "causal", "symptom": "causal", "check": "diagnostic",
                  "case": "scenario", "source": "evidence"}
        for node in self.nodes.values():
            if node.layer != layers[node.type] or (node.type == "case") != (node.knowledge == "scenario"):
                raise ValueError("Node layer or theory/scenario mismatch")
        for source in self.sources.values():
            if source.review_status == "pending":
                raise ValueError("Pending source cannot enter runtime graph")
            if source.reference.startswith("docs/") and not (ROOT / source.reference).is_file():
                raise ValueError(f"Missing local source: {source.reference}")
        for item in [*self.nodes.values(), *self.edges.values(), *self.checks.values(), *self.rules.values()]:
            if not set(item.source_ids) <= self.sources.keys():
                raise ValueError(f"Missing source on {item.id}")
            if hasattr(item, "basis") and any(self.sources[s].basis != item.basis for s in item.source_ids):
                raise ValueError(f"Evidence basis mismatch on {item.id}")
        for edge in self.edges.values():
            if edge.source not in self.nodes or edge.target not in self.nodes:
                raise ValueError(f"Missing edge endpoint: {edge.id}")
            if edge.type == "CAUSES" and (
                not edge.condition or edge.rule_id not in self.rules
            ):
                raise ValueError("Causal edge requires condition and rule")
            if edge.type == "CAUSES" and edge.id not in self.rules[edge.rule_id].path_edge_ids:
                raise ValueError("Orphaned causal edge")
            if edge.type == "SUPPORTED_BY" and (edge.target not in self.sources or self.nodes[edge.target].type != "source"):
                raise ValueError("Invalid provenance edge")
            if edge.type == "CHECKS" and (edge.source not in self.checks or self.nodes[edge.target].type != "fault"):
                raise ValueError("Invalid diagnostic edge")
            if edge.type == "EXEMPLIFIES" and (
                self.nodes[edge.source].type != "case" or self.nodes[edge.source].knowledge != "scenario"
                or self.nodes[edge.target].type != "fault"
            ):
                raise ValueError("Only designated reference cases may exemplify faults")
        for check in self.checks.values():
            if check.id not in self.nodes or self.nodes[check.id].type != "check":
                raise ValueError("Check node missing")
            if len(check.outcomes) < 2 or "unknown" not in check.outcomes:
                raise ValueError("Check needs modeled outcomes and unknown")
        for rule in self.rules.values():
            if rule.fault_id not in self.nodes or self.nodes[rule.fault_id].type != "fault":
                raise ValueError("Rule fault missing")
            if rule.component_id not in self.nodes:
                raise ValueError("Rule component missing")
            if any(s not in self.nodes or self.nodes[s].type != "symptom" for s in rule.symptom_ids):
                raise ValueError("Rule symptom missing")
            for check_id, outcome in rule.predictions.items():
                if check_id not in self.checks or outcome not in self.checks[check_id].outcomes or outcome == "unknown":
                    raise ValueError("Invalid rule prediction")
            previous = rule.fault_id
            for edge_id in rule.path_edge_ids:
                edge = self.edges.get(edge_id)
                if not edge or edge.type != "CAUSES" or edge.rule_id != rule.id or edge.source != previous:
                    raise ValueError("Invalid or disconnected causal path")
                if edge.basis != rule.basis or set(edge.source_ids) != set(rule.source_ids):
                    raise ValueError("Path provenance mismatch")
                previous = edge.target
            if previous not in rule.symptom_ids:
                raise ValueError("Causal path does not terminate at a rule symptom")

    def find_relevant_entities(self, query: str):
        q = query.casefold()
        hits = []
        for n in self.nodes.values():
            if n.id in self.graph and n.type in {"symptom", "component", "software", "interface"}:
                score = sum(a.casefold() in q for a in [n.label, *n.aliases])
                if score:
                    hits.append((score, n))
        return [n.model_dump() for _, n in sorted(hits, key=lambda x: (-x[0], x[1].id))[:12]]

    def get_candidate_faults(self, symptom_ids: list[str], component_ids: list[str]):
        # Component relevance cannot manufacture a symptom or causal mechanism.
        reachable_faults = set()
        frontier = {s for s in symptom_ids if s in self.graph and self.nodes[s].type == "symptom"}
        visited = set(frontier)
        for _ in range(4):
            parents = {source for node in frontier for source, _, edge in self.graph.in_edges(node, data=True)
                       if edge["type"] == "CAUSES"}
            reachable_faults.update(n for n in parents if self.nodes[n].type == "fault")
            frontier = parents - visited
            visited |= parents
            if not frontier:
                break
        return [r.model_dump() for r in self.rules.values()
                if r.fault_id in reachable_faults and set(r.symptom_ids) & set(symptom_ids)][:12]

    def get_fault_evidence(self, fault_id: str):
        rules = [r for r in self.rules.values() if r.fault_id == fault_id]
        return {"rules": [r.model_dump() for r in rules],
                "paths": [self.edges[e].model_dump() for r in rules for e in r.path_edge_ids],
                "reference_cases": self.reference_cases(fault_id)}

    def reference_cases(self, fault_id: str):
        return [self.nodes[u].model_dump() for u, _, e in self.graph.in_edges(fault_id, data=True)
                if e["type"] == "EXEMPLIFIES"][:3]

    def get_dependency_paths(self, component_id: str, max_depth: int = 3):
        if component_id not in self.graph:
            return []
        paths, queue = [], [(component_id, [], {component_id})]
        while queue and len(paths) < 24:
            node, path, visited = queue.pop(0)
            if len(path) >= min(max_depth, 4):
                continue
            for _, target, edge in self.graph.out_edges(node, data=True):
                if edge["type"] not in {"DEPENDS_ON", "PERFORMS", "MEASURES"} or target in visited:
                    continue
                new_path = path + [edge["id"]]
                paths.append(new_path)
                if len(paths) == 24:
                    break
                queue.append((target, new_path, visited | {target}))
        return [[self.edges[e].model_dump() for e in p] for p in paths]

    def get_diagnostic_checks(self, candidate_fault_ids: list[str]):
        ids = {c for r in self.rules.values() if r.fault_id in candidate_fault_ids for c in r.predictions}
        return [c.model_dump() for c in self.checks.values() if c.id in ids][:8]

    def get_source(self, source_id: str):
        return self.sources[source_id].model_dump()

