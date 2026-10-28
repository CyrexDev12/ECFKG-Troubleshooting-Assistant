"""Local engineer draft → validate → publish service, shared with diagnostics."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import getpass
import math
from pathlib import Path
import re
import uuid

import networkx as nx

from ecfkg.graph import KnowledgeGraph, ROOT
from ecfkg.schema import Check, Edge, Knowledge, Node, Rule, Source, compatible
from ecfkg.storage import atomic_json, digest, published, read_json, revision_path, store_lock, workspace

MODELS = {"nodes": Node, "edges": Edge, "checks": Check, "rules": Rule, "sources": Source}


def now():
    return datetime.now(timezone.utc).isoformat()


def data_part(draft):
    return {"knowledge": draft["knowledge"], "sources": draft["sources"]}


def records(document, collection):
    return document["sources"] if collection == "sources" else document["knowledge"][collection]


def change_diff(before, after):
    changes = []
    for collection in MODELS:
        old = {x["id"]: x for x in records(before, collection)}
        new = {x["id"]: x for x in records(after, collection)}
        for key in sorted(old.keys() | new.keys()):
            if old.get(key) != new.get(key):
                changes.append({"collection": collection, "id": key, "before": old.get(key), "after": new.get(key)})
    return changes


class GraphService:
    def __init__(self, root: Path | None = None, seed_dir: Path | None = None):
        self.root = root or workspace()
        self.seed_dir = seed_dir or ROOT / "data/runtime"
        with store_lock(self.root):
            if not (self.root / "current.json").exists():
                graph = KnowledgeGraph(self.seed_dir)
                content = {"knowledge": graph.knowledge.model_dump(), "sources": [s.model_dump() for s in graph.sources.values()]}
                self._snapshot(content, None, "Initial preserved prototype graph", "Initial import", [], None)

    def current(self):
        return published(self.root)

    def graph(self):
        current = self.current()
        return KnowledgeGraph.from_data(current["knowledge"], current["sources"])

    def _draft_path(self, draft_id):
        if not re.fullmatch(r"[a-f0-9]{32}", draft_id):
            raise ValueError("Invalid draft identifier")
        return self.root / "drafts" / (draft_id + ".json")

    def get_draft(self, draft_id):
        return read_json(self._draft_path(draft_id))

    def drafts(self):
        return sorted([read_json(p) for p in (self.root / "drafts").glob("*.json")], key=lambda d: d["updated_at"], reverse=True)

    def new_draft(self, label="Untitled graph revision", restore_version=None):
        with store_lock(self.root):
            current = self.current()
            source = current if restore_version is None else self.revision(restore_version)
            draft = {"id": uuid.uuid4().hex, "label": label[:160], "base_version": current["version"],
                     "seq": 0, "updated_at": now(), "editor": getpass.getuser(), "validation": None,
                     "restore_version": restore_version, **copy.deepcopy(data_part(source))}
            atomic_json(self._draft_path(draft["id"]), draft)
            return draft

    def _editable(self, draft_id, expected_seq):
        draft = self.get_draft(draft_id)
        if draft.get("published_version"):
            raise ValueError("This draft is already published. Create a new draft.")
        if draft["seq"] != expected_seq:
            raise ValueError("This draft changed in another session. Reload before editing.")
        return draft

    @staticmethod
    def _shape(draft):
        """Immediate structural checks; incomplete rule paths remain repairable drafts."""
        graph = Knowledge.model_validate(draft["knowledge"])
        sources = [Source.model_validate(s) for s in draft["sources"]]
        for items in [graph.nodes, graph.edges, graph.checks, graph.rules, sources]:
            if len({x.id for x in items}) != len(items):
                raise ValueError("Duplicate stable ID")
        if len(graph.nodes) > 1000 or len(graph.edges) > 4000:
            raise ValueError("Prototype limit: 1,000 nodes and 4,000 relationships")
        nodes = {n.id: n for n in graph.nodes}
        source_ids = {s.id for s in sources}
        for item in [*graph.nodes, *graph.edges, *graph.checks, *graph.rules]:
            if not set(item.source_ids) <= source_ids:
                raise ValueError(f"Unknown source reference on {item.id}")
        for edge in graph.edges:
            if edge.source not in nodes or edge.target not in nodes:
                raise ValueError("Relationship endpoint is missing")
            if edge.source == edge.target or not compatible(edge.type, nodes[edge.source].type, nodes[edge.target].type):
                raise ValueError(f"{edge.type} cannot connect these node types in this direction")
            if edge.type == "CAUSES" and (not edge.condition or not edge.condition.strip() or not edge.rule_id):
                raise ValueError("Causal relationships require explicit conditions and a rule ID")
        # Preserve full validated records, including unknown-to-the-canvas metadata.
        draft["knowledge"] = graph.model_dump()
        draft["sources"] = [s.model_dump() for s in sources]

    def _save(self, draft):
        self._shape(draft)
        draft.update(seq=draft["seq"] + 1, updated_at=now(), validation=None)
        atomic_json(self._draft_path(draft["id"]), draft)
        return draft

    def save_draft(self, draft_id, expected_seq):
        with store_lock(self.root):
            return self._save(self._editable(draft_id, expected_seq))

    def upsert(self, draft_id, collection, value, expected_seq, *, create=False):
        return self.upsert_many(draft_id, [(collection, value, create)], expected_seq)

    def upsert_many(self, draft_id, operations, expected_seq):
        with store_lock(self.root):
            draft = self._editable(draft_id, expected_seq)
            for collection, value, create in operations:
                if collection not in MODELS:
                    raise ValueError("Unknown record category")
                value = MODELS[collection].model_validate(value).model_dump()
                items = records(draft, collection)
                existing = next((i for i, x in enumerate(items) if x["id"] == value["id"]), None)
                if create and existing is not None:
                    raise ValueError("ID already exists; choose a new stable ID")
                if not create and existing is None:
                    raise ValueError("Record no longer exists; reload the draft")
                if existing is None:
                    items.append(value)
                else:
                    items[existing] = value
            return self._save(draft)

    def deletion_plan(self, draft_id, collection, identifier):
        draft = self.get_draft(draft_id)
        if collection not in MODELS or not any(x["id"] == identifier for x in records(draft, collection)):
            raise ValueError("Record does not exist")
        if collection == "sources":
            refs = [x["id"] for group in ["nodes", "edges", "rules", "checks"] for x in records(draft, group)
                    if identifier in x["source_ids"] and x["id"] != identifier]
            if refs:
                raise ValueError("Reassign this source before deletion; referenced by: " + ", ".join(refs[:12]))
        removed = {group: set() for group in MODELS}
        removed[collection].add(identifier)
        if collection == "sources":
            removed["nodes"].add(identifier)
        if collection == "checks":
            removed["nodes"].add(identifier)
        for node_id in removed["nodes"].copy():
            removed["checks"].update(c["id"] for c in records(draft, "checks") if c["id"] == node_id)
            removed["sources"].update(s["id"] for s in draft["sources"] if s["id"] == node_id)
            if node_id in removed["sources"] and collection != "sources":
                raise ValueError("Delete source metadata through the Sources form after reassigning references")
        for edge in records(draft, "edges"):
            if edge["source"] in removed["nodes"] or edge["target"] in removed["nodes"]:
                removed["edges"].add(edge["id"])
        for rule in records(draft, "rules"):
            if ({rule["fault_id"], rule["component_id"], *rule["symptom_ids"]} & removed["nodes"]
                    or set(rule["path_edge_ids"]) & removed["edges"]):
                removed["rules"].add(rule["id"])
        for edge in records(draft, "edges"):
            if edge.get("rule_id") in removed["rules"]:
                removed["edges"].add(edge["id"])
        changed_rules = [r["id"] for r in records(draft, "rules")
                         if set(r["predictions"]) & removed["checks"] and r["id"] not in removed["rules"]]
        return {"remove": {k: sorted(v) for k, v in removed.items() if v}, "clear_check_predictions": changed_rules,
                "notice": "Removing a causal edge also removes its diagnostic rule and the remaining edges in that rule's path."}

    def delete(self, draft_id, collection, identifier, expected_seq, *, confirmed=False):
        if not confirmed:
            raise ValueError("Deletion requires explicit confirmation of the affected records")
        with store_lock(self.root):
            draft = self._editable(draft_id, expected_seq)
            plan = self.deletion_plan(draft_id, collection, identifier)
            for group, ids in plan["remove"].items():
                records(draft, group)[:] = [x for x in records(draft, group) if x["id"] not in ids]
            deleted_checks = plan["remove"].get("checks", [])
            for rule in records(draft, "rules"):
                rule["predictions"] = {k: v for k, v in rule["predictions"].items() if k not in deleted_checks}
            return self._save(draft)

    def diff(self, draft_id):
        draft = self.get_draft(draft_id)
        return change_diff(self.revision(draft["base_version"]), draft)

    @staticmethod
    def _regression(before, after):
        from ecfkg.diagnostics import assess, interpret_baseline
        from ecfkg.schema import Observation
        rows = []
        for case in read_json(ROOT / "data/evaluation/cases.json"):
            outcomes = []
            for graph in [before, after]:
                try:
                    observations = [Observation.model_validate(o) for o in case["available_observations"]]
                    interpretation = interpret_baseline(case["initial_symptom"], graph)
                    steps = []
                    for count in range(len(observations) + 1):
                        result = assess(graph, interpretation, observations[:count])
                        steps.append({"status": result.status, "faults": [c.fault_id for c in result.candidates],
                                      "scores": [c.score for c in result.candidates], "next_check": result.next_check})
                    faults = [c.fault_id for c in result.candidates]
                    ok = result.status == "abstain" if case["expected_abstention"] else case["expected_root_cause"] in faults
                    outcomes.append({"status": result.status, "faults": faults, "expected_result_met": ok,
                                     "next_check": result.next_check, "steps": steps,
                                     "initial_useful_check": steps[0]["next_check"] in case["expected_useful_checks"]})
                except ValueError:
                    outcomes.append({"status": "invalid_case_references", "faults": [], "expected_result_met": False, "next_check": None})
            rows.append({"case_id": case["case_id"], "before": outcomes[0], "after": outcomes[1],
                         "changed": outcomes[0] != outcomes[1],
                         "regression": outcomes[0]["expected_result_met"] and not outcomes[1]["expected_result_met"]})
        return rows

    def validate(self, draft_id, expected_seq):
        with store_lock(self.root):
            draft = self._editable(draft_id, expected_seq)
            current = self.current()
            errors, warnings, cases = [], [], []
            if draft["base_version"] != current["version"]:
                errors.append("Published version changed. Start a draft from the latest version; review/reapply your changes.")
            try:
                graph = KnowledgeGraph.from_data(draft["knowledge"], draft["sources"])
                cases = self._regression(self.graph(), graph)
                if any(c["regression"] for c in cases):
                    errors.append("Existing diagnostic cases regressed. Repair the draft before publication.")
                fault_rules = {r.fault_id for r in graph.rules.values()}
                orphaned = [n.id for n in graph.nodes.values() if n.type == "fault" and n.id not in fault_rules]
                if orphaned:
                    warnings.append("Faults without complete causal rules cannot be retrieved: " + ", ".join(orphaned))
                for rule in graph.rules.values():
                    if not rule.predictions:
                        warnings.append(f"{rule.id} has no diagnostic check predictions")
                signatures = {}
                for rule in graph.rules.values():
                    key = digest([rule.component_id, sorted(rule.symptom_ids), rule.predictions])
                    if key in signatures:
                        warnings.append(f"Potentially indistinguishable fault rules: {signatures[key]} and {rule.id}; review competing explanations")
                    signatures[key] = rule.id
                parallel = {}
                for edge in graph.edges.values():
                    key = (edge.source, edge.target, edge.type)
                    if key in parallel and edge.condition != parallel[key].condition:
                        warnings.append(f"Parallel conditional relationships {parallel[key].id} and {edge.id}: review conditions for conflict")
                    parallel[key] = edge
                dependency = nx.DiGraph((e.source, e.target) for e in graph.edges.values() if e.type == "DEPENDS_ON")
                if not nx.is_directed_acyclic_graph(dependency):
                    warnings.append("Dependency cycle detected; verify that mutual dependency is intentional")
                if any(c["changed"] for c in cases):
                    warnings.append("Some existing diagnostic outputs changed; inspect the case comparison")
                if any(s.basis != "verified_public" for s in graph.sources.values()):
                    warnings.append("Synthetic/assumption evidence remains labeled; publication is not engineering validation")
            except ValueError as exc:
                errors.append(str(exc))
            report = {"valid": not errors, "errors": errors, "warnings": warnings, "cases": cases,
                      "validated_at": now(), "content_sha256": digest(data_part(draft)),
                      "base_version": current["version"], "seq": draft["seq"]}
            draft["validation"] = report
            atomic_json(self._draft_path(draft_id), draft)
            return report

    def publish(self, draft_id, expected_seq, description, reviewer, *, approved=False):
        if not approved or not reviewer.strip() or not description.strip():
            raise ValueError("Publication requires a named local reviewer, change description and explicit approval")
        with store_lock(self.root):
            draft = self._editable(draft_id, expected_seq)
            current = self.current()
            report = draft.get("validation") or {}
            if (not report.get("valid") or report.get("content_sha256") != digest(data_part(draft))
                    or report.get("base_version") != current["version"] or draft["base_version"] != current["version"]):
                raise ValueError("Validate this exact draft against the current published graph before publication")
            KnowledgeGraph.from_data(draft["knowledge"], draft["sources"])
            changes = change_diff(current, draft)
            if not changes:
                raise ValueError("No engineering changes to publish; layouts are stored separately")
            revision = self._snapshot(data_part(draft), current["version"], description[:2000], reviewer[:160], changes, report)
            draft["published_version"] = revision["version"]
            atomic_json(self._draft_path(draft_id), draft)
            return revision

    def _snapshot(self, content, parent, description, reviewer, changes, validation):
        paths = list((self.root / "revisions").glob("v*.json"))
        sequence = max((int(p.name[1:7]) for p in paths), default=-1) + 1
        version = f"v{sequence:06d}-{digest(content)[:12]}"
        content = copy.deepcopy(content)
        content["knowledge"]["version"] = version
        record = {"version": version, "parent": parent, "timestamp": now(), "editor": getpass.getuser(),
                  "reviewer": reviewer, "description": description, "changes": changes,
                  "validation": validation, **content}
        # Single immutable snapshot holds graph and provenance; pointer changes last.
        atomic_json(revision_path(self.root, version), record, backup=False)
        atomic_json(self.root / "current.json", {"version": version, "sha256": digest(record)})
        return record

    def revision(self, version):
        # Only committed history is eligible for restore (exclude interrupted unpublished snapshots).
        for item in self.history():
            if item["version"] == version:
                return read_json(revision_path(self.root, version))
        raise ValueError("Revision is not in published history")

    def history(self):
        entry, result, seen = self.current(), [], set()
        while entry:
            if entry["version"] in seen:
                raise ValueError("Invalid history cycle")
            seen.add(entry["version"])
            result.append({k: entry[k] for k in ["version", "parent", "timestamp", "editor", "reviewer", "description"]})
            entry = read_json(revision_path(self.root, entry["parent"])) if entry["parent"] else None
        return result

    def layout(self, view):
        path = self.root / "layouts.json"
        return read_json(path).get(view, {}) if path.exists() else {}

    def save_layout(self, view, positions, viewport=None):
        if view not in {"architecture", "dependencies", "causal"} or len(positions) > 1000:
            raise ValueError("Invalid layout view or size")
        for identifier, point in positions.items():
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,79}", identifier) or set(point) != {"x", "y"}:
                raise ValueError("Invalid layout position")
            if any(type(v) not in {float, int} or not math.isfinite(v) or abs(v) > 1e6 for v in point.values()):
                raise ValueError("Invalid layout coordinate")
        if viewport is not None:
            if set(viewport) != {"x", "y", "zoom"} or any(type(v) not in {float, int} or not math.isfinite(v) for v in viewport.values()):
                raise ValueError("Invalid viewport")
            if not .05 <= viewport["zoom"] <= 4 or abs(viewport["x"]) > 1e6 or abs(viewport["y"]) > 1e6:
                raise ValueError("Viewport outside bounds")
        with store_lock(self.root):
            path = self.root / "layouts.json"
            layouts = read_json(path) if path.exists() else {}
            layouts[view] = {"positions": positions, "viewport": viewport, "saved_at": now()}
            atomic_json(path, layouts)
        return layouts[view]
