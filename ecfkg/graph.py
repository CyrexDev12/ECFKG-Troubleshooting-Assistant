"""Validated JSON storage and bounded read-only graph retrieval."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import networkx as nx

from ecfkg.schema import Knowledge, Source, NODE_LAYERS, PHYSICAL, compatible

ROOT = Path(__file__).resolve().parents[1]


class KnowledgeGraph:
    def __init__(self, data_dir: Path | None = None, include_scenarios: bool = True):
        if data_dir is None:
            from ecfkg.storage import published
            revision = published()
            if revision:
                self._load(revision["knowledge"], revision["sources"], include_scenarios)
                return
        data_dir = data_dir or ROOT / "data" / "runtime"
        graph_bytes = (data_dir / "graph.json").read_bytes()
        source_bytes = (data_dir / "sources.json").read_bytes()
        self.data_hash = hashlib.sha256(graph_bytes + source_bytes).hexdigest()
        self._load(json.loads(graph_bytes), json.loads(source_bytes), include_scenarios)
        self.data_hash = hashlib.sha256(graph_bytes + source_bytes).hexdigest()

    @classmethod
    def from_data(cls, knowledge: dict, sources: list[dict], include_scenarios=True):
        graph = cls.__new__(cls)
        graph._load(knowledge, sources, include_scenarios)
        return graph

    def _load(self, knowledge, source_data, include_scenarios):
        from ecfkg.storage import digest
        self.data_hash = digest({"knowledge": knowledge, "sources": source_data})
        self.knowledge = Knowledge.model_validate(knowledge)
        sources = [Source.model_validate(s) for s in source_data]
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
        for node in self.nodes.values():
            if node.layer != NODE_LAYERS[node.type] or (node.type == "case") != (node.knowledge == "scenario"):
                raise ValueError("Node layer or theory/scenario mismatch")
            if not node.label.strip() or not node.description.strip() or node.status == "draft":
                raise ValueError(f"Node {node.id} needs a label, description and publishable knowledge status")
            if node.type == "check" and node.id not in self.checks:
                raise ValueError(f"Diagnostic check definition missing: {node.id}")
            if node.type == "source" and node.id not in self.sources:
                raise ValueError(f"Source metadata missing: {node.id}")
        if (self.nodes.keys() & self.edges.keys() or self.nodes.keys() & self.rules.keys()
                or self.edges.keys() & self.rules.keys()):
            raise ValueError("Node, relationship and rule IDs must be globally distinct")
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
            if edge.source == edge.target or not compatible(edge.type, self.nodes[edge.source].type, self.nodes[edge.target].type):
                raise ValueError(f"Incompatible relationship types/direction: {edge.id}")
            if edge.status == "draft":
                raise ValueError(f"Relationship {edge.id} is still draft knowledge")
            if edge.type == "CAUSES" and (
                not edge.condition or not edge.condition.strip() or edge.rule_id not in self.rules
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
            if not check.instructions.strip() or not check.label.strip() or any(not k.strip() or not v.strip() for k, v in check.outcomes.items()):
                raise ValueError("Diagnostic check needs instructions and named outcomes")
            if check.id not in self.nodes or self.nodes[check.id].type != "check":
                raise ValueError("Check node missing")
            if len(check.outcomes) < 2 or "unknown" not in check.outcomes:
                raise ValueError("Check needs modeled outcomes and unknown")
        for rule in self.rules.values():
            if rule.fault_id not in self.nodes or self.nodes[rule.fault_id].type != "fault":
                raise ValueError("Rule fault missing")
            if rule.component_id not in self.nodes or self.nodes[rule.component_id].type not in PHYSICAL:
                raise ValueError("Rule component missing")
            if not all(c.strip() for c in rule.conditions) or len(rule.path_edge_ids) > 4:
                raise ValueError("Rule needs explicit conditions and at most four causal edges")
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
        if len({r.fault_id for r in self.rules.values()}) != len(self.rules):
            raise ValueError("This scorer supports one diagnostic rule per fault; use distinct fault modes")
        for kind in ["CAUSES", "HAS_COMPONENT"]:
            structure = nx.DiGraph((e.source, e.target) for e in self.edges.values() if e.type == kind)
            if not nx.is_directed_acyclic_graph(structure):
                raise ValueError(f"{kind} relationships must not contain a directed cycle")
            if kind == "HAS_COMPONENT" and any(d > 1 for _, d in structure.in_degree()):
                raise ValueError("A component can have only one containment parent")
        signatures = [(e.source, e.target, e.type, e.condition, e.rule_id) for e in self.edges.values()]
        if len(signatures) != len(set(signatures)):
            raise ValueError("Duplicate relationship meaning; parallel types/conditions are allowed")

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
                if edge["type"] not in {"DEPENDS_ON", "PERFORMS", "MEASURES", "CONTROLS", "PRODUCES", "CONSUMES", "FLOWS_TO"} or target in visited:
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

