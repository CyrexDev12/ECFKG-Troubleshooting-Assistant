"""Streamlit engineer workspace and bidirectional React Flow canvas."""
from __future__ import annotations

from datetime import date
import json

import streamlit as st

from ecfkg.fault_authoring import DEMO_FIELDS, fault_operations
from ecfkg.graph import ROOT
from ecfkg.graph_service import GraphService, records
from ecfkg.schema import EDGE_TYPES, NODE_LAYERS, PHYSICAL, FUNCTIONAL, Node, Source

ASSETS = ROOT / "ecfkg/editor_assets"
CANVAS = st.components.v2.component("station_knowledge_canvas", html="",
    js=(ASSETS / "editor.js").read_text(encoding="utf-8"),
    css=(ASSETS / "editor.css").read_text(encoding="utf-8"))
VIEWS = {"System Architecture": "architecture", "Dependencies": "dependencies", "Causal Faults": "causal"}
VIEW_EDGES = {
    "architecture": ["CONNECTED_TO", "HAS_COMPONENT", "CONTROLS"],
    "dependencies": ["DEPENDS_ON", "PERFORMS", "MEASURES", "CONTROLS", "PRODUCES", "CONSUMES", "FLOWS_TO"],
    "causal": ["CAUSES", "AFFECTS", "CHECKS"],
}


def _change(service, draft, operation, *args, **kwargs):
    try:
        result = operation(*args, **kwargs)
        st.session_state.editor_notice = "Draft saved. Validate before publishing."
        st.rerun()
        return result
    except ValueError as exc:
        st.error(str(exc))


def _sources(draft, current=None, label="Evidence sources"):
    ids = [s["id"] for s in draft["sources"]]
    return st.multiselect(label, ids, default=[x for x in (current or ids[:1]) if x in ids])


def _pairs(label, mapping, key, first="Property", second="Value"):
    values = st.data_editor([{first: k, second: v} for k, v in mapping.items()] or [{first: "", second: ""}],
                            num_rows="dynamic", key=key, width="stretch",
                            column_config={first: st.column_config.TextColumn(first, required=True),
                                           second: st.column_config.TextColumn(second, required=True)})
    entries = [(str(row.get(first) or "").strip(), str(row.get(second) or "").strip()) for row in values]
    entries = [(a, b) for a, b in entries if a or b]
    if any(not a or not b for a, b in entries) or len({a for a, _ in entries}) != len(entries):
        raise ValueError(f"{label}: names must be unique and both columns filled")
    return dict(entries)


def _delete(service, draft, collection, identifier):
    with st.expander("Delete this record"):
        try:
            plan = service.deletion_plan(draft["id"], collection, identifier)
            st.caption(plan["notice"])
            st.json(plan, expanded=True)
            confirmed = st.checkbox("I confirm removal of every listed record and prediction", key=f"delete_ok_{collection}_{identifier}_{draft['seq']}")
            if st.button("Confirm deletion", disabled=not confirmed, key=f"delete_{collection}_{identifier}"):
                st.session_state.editor_selection = None
                _change(service, draft, service.delete, draft["id"], collection, identifier, draft["seq"], confirmed=confirmed)
        except ValueError as exc:
            st.warning(str(exc))


def _node_form(service, draft, selected, editable):
    new = selected is None
    node = selected or {"id": "", "type": "component", "label": "", "description": "", "aliases": [], "source_ids": [], "properties": {}, "status": "synthetic"}
    st.subheader("Add node" if new else node["label"])
    category = st.selectbox("Node category", list(NODE_LAYERS), index=list(NODE_LAYERS).index(node["type"]), disabled=not editable)
    with st.form(f"node_{draft['id']}_{draft['seq']}_{node['id']}"):
        identifier = st.text_input("Stable node ID", node["id"], disabled=not new or not editable, help="Uppercase letters, digits and underscores. IDs cannot be renamed.")
        label = st.text_input("Display name", node["label"], disabled=not editable)
        description = st.text_area("Description", node["description"], disabled=not editable)
        aliases = st.text_area("Search aliases (one per line)", "\n".join(node["aliases"]), disabled=not editable)
        source_ids = _sources(draft, node["source_ids"])
        status = st.selectbox("Knowledge status", ["synthetic", "reviewed", "draft"], index=["synthetic", "reviewed", "draft"].index(node["status"]))
        st.caption("Configuration / functional properties")
        properties = _pairs("Properties", node["properties"], f"props_{draft['id']}_{node['id']}_{draft['seq']}")
        if st.form_submit_button("Save node to draft", disabled=not editable):
            value = {**node, "id": identifier, "type": category, "layer": NODE_LAYERS[category],
                     "knowledge": "scenario" if category == "case" else "theory", "label": label,
                     "description": description, "aliases": [x.strip() for x in aliases.splitlines() if x.strip()],
                     "source_ids": source_ids, "status": status, "properties": properties}
            _change(service, draft, service.upsert, draft["id"], "nodes", value, draft["seq"], create=new)
    if not new:
        related = [e for e in records(draft, "edges") if node["id"] in {e["source"], e["target"]}]
        st.caption(f"{len(related)} connected relationships")
        for e in related:
            if st.button(f"{e['type']}: {e['source']} → {e['target']}", key="rel_" + e["id"]):
                st.session_state.editor_selection = {"collection": "edges", "id": e["id"]}
                st.session_state.editor_panel = "selection"
                st.rerun()
        if node["type"] in PHYSICAL and st.button("Add Fault Mode", disabled=not editable):
            st.session_state.fault_component = node["id"]
            st.session_state.editor_panel = "fault"
            st.rerun()
        if node["type"] == "check":
            if st.button("Edit diagnostic procedure", disabled=not editable):
                st.session_state.editor_selection = {"collection": "checks", "id": node["id"]}
                st.session_state.editor_panel = "checks"
                st.session_state.editor_check_node = node
                st.rerun()
        if node["type"] == "fault":
            for rule in records(draft, "rules"):
                if rule["fault_id"] == node["id"] and st.button("Edit causal rule " + rule["id"]):
                    st.session_state.editor_selection = {"collection": "rules", "id": rule["id"]}
                    st.rerun()
        with st.expander("Evidence details"):
            for source in draft["sources"]:
                if source["id"] in node["source_ids"]:
                    st.json(source)
        if editable:
            _delete(service, draft, "nodes", node["id"])


def _edge_form(service, draft, selected, editable):
    proposed = st.session_state.get("editor_connection", {})
    new = selected is None
    edge = selected or {"id": "", "source": proposed.get("source"), "target": proposed.get("target"),
                        "type": "CONNECTED_TO", "description": "", "condition": "", "rule_id": "",
                        "basis": "synthetic_demo", "source_ids": [], "status": "synthetic"}
    st.subheader("Add relationship" if new else "Relationship properties")
    ids = [n["id"] for n in records(draft, "nodes")]
    with st.form(f"edge_{draft['id']}_{draft['seq']}_{edge['id']}"):
        identifier = st.text_input("Stable relationship ID", edge["id"], disabled=not new or not editable)
        source = st.selectbox("From node (source)", ids, index=ids.index(edge["source"]) if edge["source"] in ids else 0)
        target = st.selectbox("To node (target)", ids, index=ids.index(edge["target"]) if edge["target"] in ids else min(1, len(ids)-1))
        kind = st.selectbox("Relationship type", EDGE_TYPES, index=EDGE_TYPES.index(edge["type"]))
        description = st.text_area("Relationship description", edge["description"])
        condition = st.text_area("Conditions (required for CAUSES)", edge["condition"] or "")
        rule_id = st.text_input("Causal rule ID (CAUSES only)", edge["rule_id"] or "")
        basis = st.selectbox("Evidence basis", ["synthetic_demo", "engineering_assumption", "verified_public"],
                             index=["synthetic_demo", "engineering_assumption", "verified_public"].index(edge["basis"]))
        source_ids = _sources(draft, edge["source_ids"])
        status = st.selectbox("Knowledge status", ["synthetic", "reviewed", "draft"], index=["synthetic", "reviewed", "draft"].index(edge["status"]))
        st.caption("Arrows are directed from source to target. Physical/dependency links never create causal knowledge.")
        if st.form_submit_button("Save relationship to draft", disabled=not editable):
            value = {"id": identifier, "source": source, "target": target, "type": kind, "description": description,
                     "condition": condition.strip() or None, "rule_id": rule_id.strip() or None,
                     "basis": basis, "source_ids": source_ids, "status": status}
            _change(service, draft, service.upsert, draft["id"], "edges", value, draft["seq"], create=new)
    if not new and editable:
        _delete(service, draft, "edges", edge["id"])


def _check_form(service, draft, selected, editable):
    new = selected is None
    paired = st.session_state.get("editor_check_node", {}) if new else {}
    check = selected or {"id": paired.get("id", ""), "label": paired.get("label", ""),
                         "instructions": paired.get("description", ""), "outcomes": {"normal": "Expected state", "unknown": "Not checked"},
                         "source_ids": paired.get("source_ids", [])}
    st.subheader("Diagnostic check")
    with st.form(f"check_{draft['id']}_{draft['seq']}_{check['id']}"):
        identifier = st.text_input("Stable check ID", check["id"], disabled=not new or bool(paired))
        label = st.text_input("Check name", check["label"])
        instructions = st.text_area("Observation instructions", check["instructions"])
        st.caption("Outcome codes must include unknown. Rules reference these exact codes.")
        outcomes = _pairs("Outcomes", check["outcomes"], f"check_outcomes_{draft['id']}_{draft['seq']}_{check['id']}", "Outcome code", "Meaning")
        source_ids = _sources(draft, check["source_ids"])
        if st.form_submit_button("Save check to draft", disabled=not editable):
            value = {"id": identifier, "label": label, "instructions": instructions, "outcomes": outcomes, "source_ids": source_ids}
            node = next((n for n in records(draft, "nodes") if n["id"] == identifier), None)
            node_value = {**(node or {}), "id": identifier, "type": "check", "layer": "diagnostic", "label": label,
                          "description": instructions, "source_ids": source_ids}
            _change(service, draft, service.upsert_many, draft["id"], [("nodes", node_value, node is None), ("checks", value, new)], draft["seq"])
    if not new and editable:
        _delete(service, draft, "checks", check["id"])


def _rule_form(service, draft, selected, editable):
    new = selected is None
    rule = selected or {"id": "", "fault_id": "", "component_id": "", "symptom_ids": [], "conditions": [],
                        "predictions": {}, "path_edge_ids": [], "basis": "synthetic_demo", "source_ids": []}
    st.subheader("Causal diagnostic rule")
    nodes = records(draft, "nodes")
    faults = [n["id"] for n in nodes if n["type"] == "fault"]
    components = [n["id"] for n in nodes if n["type"] in PHYSICAL]
    if not faults or not components:
        st.info("Create a fault and component first.")
        return
    with st.form(f"rule_{draft['id']}_{draft['seq']}_{rule['id']}"):
        identifier = st.text_input("Stable rule ID", rule["id"], disabled=not new)
        fault = st.selectbox("Fault", faults, index=faults.index(rule["fault_id"]) if rule["fault_id"] in faults else 0)
        component = st.selectbox("Associated component", components, index=components.index(rule["component_id"]) if rule["component_id"] in components else 0)
        symptoms = st.multiselect("Supported symptoms", [n["id"] for n in nodes if n["type"] == "symptom"], default=rule["symptom_ids"])
        conditions = st.text_area("Causal conditions (one per line)", "\n".join(rule["conditions"]))
        paths = st.multiselect("Ordered CAUSES edges: fault → condition → symptom", [e["id"] for e in records(draft, "edges") if e["type"] == "CAUSES"], default=rule["path_edge_ids"])
        st.caption("Select edges in traversal order. Each edge must reference this rule ID.")
        predictions = _pairs("Predictions", rule["predictions"], f"rule_predictions_{draft['id']}_{draft['seq']}_{rule['id']}", "Check ID", "Expected outcome")
        basis = st.selectbox("Evidence basis", ["synthetic_demo", "engineering_assumption", "verified_public"], index=["synthetic_demo", "engineering_assumption", "verified_public"].index(rule["basis"]))
        source_ids = _sources(draft, rule["source_ids"])
        if st.form_submit_button("Save rule to draft", disabled=not editable):
            value = {"id": identifier, "fault_id": fault, "component_id": component, "symptom_ids": symptoms,
                     "conditions": [x.strip() for x in conditions.splitlines() if x.strip()], "path_edge_ids": paths,
                     "predictions": predictions, "basis": basis, "source_ids": source_ids}
            _change(service, draft, service.upsert, draft["id"], "rules", value, draft["seq"], create=new)
    if not new and editable:
        _delete(service, draft, "rules", rule["id"])


def _source_form(service, draft, selected, editable):
    new = selected is None
    source = selected or {"id": "", "title": "", "publisher": "Local prototype editor", "reference": "docs/editor-guide.md",
                          "section": "Locally authored synthetic mechanisms", "paraphrase": "", "access_date": date.today().isoformat(),
                          "basis": "synthetic_demo", "review_status": "synthetic_unreviewed", "permitted_use": "Original synthetic project demonstration",
                          "approval_record": None}
    st.subheader("Source and provenance")
    with st.form(f"source_{draft['id']}_{draft['seq']}_{source['id']}"):
        value = dict(source)
        for key, label in [("id", "Stable source ID"), ("title", "Source title"), ("publisher", "Author / publisher"),
                           ("reference", "HTTPS or docs/ reference"), ("section", "Section"), ("access_date", "Access date (YYYY-MM-DD)")]:
            value[key] = st.text_input(label, source[key], disabled=key == "id" and not new)
        value["paraphrase"] = st.text_area("Permitted paraphrase / explicit assumption", source["paraphrase"])
        value["basis"] = st.selectbox("Evidence basis", ["synthetic_demo", "engineering_assumption", "verified_public"], index=["synthetic_demo", "engineering_assumption", "verified_public"].index(source["basis"]))
        statuses = ["synthetic_unreviewed", "approved", "pending"]
        value["review_status"] = st.selectbox("Source review status", statuses, index=statuses.index(source["review_status"]))
        value["permitted_use"] = st.text_area("Permitted use", source["permitted_use"])
        value["approval_record"] = st.text_input("Approval record (required for verified public)", source["approval_record"] or "") or None
        st.caption("A local approval record is an assertion by the reviewer, not verified authorization. Pending sources cannot be published.")
        if st.form_submit_button("Save source to draft", disabled=not editable):
            node = next((n for n in records(draft, "nodes") if n["id"] == value["id"]), None)
            node_value = {**(node or {}), "id": value["id"], "type": "source", "layer": "evidence", "label": value["title"],
                          "description": value["paraphrase"], "source_ids": [value["id"]]}
            _change(service, draft, service.upsert_many, draft["id"], [("sources", value, new), ("nodes", node_value, node is None)], draft["seq"])
    if not new and editable:
        _delete(service, draft, "sources", source["id"])


def _fault_form(service, draft, editable):
    st.subheader("Add a complete fault mode")
    st.caption("Creates a fault → condition → symptom path, component association, check and rule together in this draft.")
    example = st.checkbox("Use the synthetic aperture demonstration", key="fault_example")
    defaults = DEMO_FIELDS if example else {}
    components = [n["id"] for n in records(draft, "nodes") if n["type"] in PHYSICAL]
    if not components:
        st.info("Create a physical component first.")
        return
    with st.form(f"fault_bundle_{draft['id']}_{example}"):
        values = {}
        values["stem"] = st.text_input("Unique ID suffix", defaults.get("stem", ""), help="Example: APERTURE_018. Stable IDs are generated from this suffix.")
        component = st.session_state.get("fault_component", defaults.get("component_id", "C_DMM"))
        values["component_id"] = st.selectbox("Component", components, index=components.index(component) if component in components else 0)
        for key, label in [("fault_label", "Fault mode name"), ("description", "Fault description"),
                           ("condition_label", "Intermediate condition"), ("symptom_label", "Observable symptom"),
                           ("alias", "Distinctive symptom phrase"), ("conditions", "Explicit causal conditions"),
                           ("check_label", "Diagnostic check name"), ("instructions", "Check instructions")]:
            values[key] = st.text_area(label, defaults.get(key, ""), height=70) if key in {"description", "conditions", "instructions"} else st.text_input(label, defaults.get(key, ""))
        use_synthetic = st.checkbox("Create a source record labeling this as a synthetic assumption", value=True)
        source_id = st.selectbox("Existing source (used when unchecked)", [s["id"] for s in draft["sources"]])
        if st.form_submit_button("Add fault path to draft", disabled=not editable):
            try:
                if any(not v.strip() for v in values.values()):
                    raise ValueError("Complete every fault field before adding the path")
                operations = []
                if use_synthetic:
                    source_id = "SRC_" + values["stem"]
                    source = Source(id=source_id, title=values["fault_label"], publisher="Local prototype editor",
                        reference="docs/editor-guide.md", section="Locally authored synthetic mechanisms",
                        paraphrase=values["conditions"], access_date=date.today().isoformat(), basis="synthetic_demo",
                        review_status="synthetic_unreviewed", permitted_use="Original synthetic assumption for the generic capstone prototype")
                    source_node = Node(id=source_id, type="source", layer="evidence", label=source.title,
                                       description=source.paraphrase, source_ids=[source_id])
                    operations += [("sources", source.model_dump(), True), ("nodes", source_node.model_dump(), True)]
                    basis = "synthetic_demo"
                else:
                    basis = next(s["basis"] for s in draft["sources"] if s["id"] == source_id)
                operations += fault_operations(**values, source_id=source_id, basis=basis)
                _change(service, draft, service.upsert_many, draft["id"], operations, draft["seq"])
            except ValueError as exc:
                st.error(str(exc))


def _publication(service, draft):
    st.subheader("Review and publish")
    report = draft.get("validation")
    if not report:
        st.info("Validate this draft first. Every edit invalidates the previous validation.")
    else:
        (st.success if report["valid"] else st.error)("Validation passed" if report["valid"] else "Publication blocked")
        for error in report["errors"]:
            st.error(error)
        for warning in report["warnings"]:
            st.warning(warning)
        with st.expander("Existing case comparison", expanded=False):
            st.json(report["cases"])
    changes = service.diff(draft["id"])
    st.write(f"{len(changes)} changed records")
    for change in changes:
        with st.expander(f"{change['collection']} · {change['id']}"):
            st.json({"previous": change["before"], "updated": change["after"]})
    with st.form("publish_review_" + draft["id"]):
        description = st.text_area("Change description", draft["label"])
        reviewer = st.text_input("Local reviewer identity", draft["editor"])
        approval = st.checkbox("I reviewed the diff, assumptions and case results and approve publication")
        st.caption("Local prototype review only. This is not production authorization or technical certification.")
        if st.form_submit_button("Publish reviewed changes", disabled=not report or not report["valid"]):
            try:
                revision = service.publish(draft["id"], draft["seq"], description, reviewer, approved=approval)
                st.session_state.editor_notice = "Published " + revision["version"] + ". New troubleshooting sessions now use this graph."
                st.session_state.pop("editor_draft_id", None)
                st.session_state.editor_panel = "selection"
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def _event(service, draft, event, edit):
    if not isinstance(event, dict) or event.get("event_id") == st.session_state.get("editor_last_event"):
        return
    st.session_state.editor_last_event = event.get("event_id")
    if event.get("draft_id") != draft["id"] or event.get("seq") != draft["seq"]:
        st.warning("The canvas changed; retry the action on the refreshed graph.")
        return
    view = event.get("view")
    positions = st.session_state.setdefault("editor_positions", {})
    prior = positions.setdefault(view, service.layout(view))
    prior["positions"] = {**prior.get("positions", {}), **event.get("positions", {})}
    prior["viewport"] = event.get("viewport")
    action = event.get("action")
    if action == "save_layout":
        service.save_layout(view, prior["positions"], prior["viewport"])
        st.session_state.editor_notice = "Layout saved. Diagnostic knowledge is unchanged."
    elif action == "select":
        st.session_state.editor_selection = {"collection": event["collection"], "id": event["id"]}
        st.session_state.editor_panel = "selection"
    elif action in {"create_node", "create_edge", "create_fault", "connect", "reconnect"} and edit:
        if action == "reconnect":
            edge = next(e for e in records(draft, "edges") if e["id"] == event["id"])
            edge = {**edge, "source": event["source"], "target": event["target"]}
            service.upsert(draft["id"], "edges", edge, draft["seq"])
            st.session_state.editor_selection = {"collection": "edges", "id": edge["id"]}
            st.session_state.editor_panel = "selection"
        else:
            st.session_state.editor_panel = {"create_node": "node", "create_edge": "edge", "create_fault": "fault", "connect": "edge"}[action]
            st.session_state.editor_connection = event if action == "connect" else {}
    st.rerun()


def render_editor():
    st.markdown("<style>.stMainBlockContainer{padding:2rem 2rem 3rem;}</style>", unsafe_allow_html=True)
    service = GraphService()
    current = service.current()
    with st.sidebar:
        st.header("Graph workspace")
        active = [d for d in service.drafts() if not d.get("published_version")]
        labels = {d["id"]: d["label"] + " · " + d["updated_at"][:16] for d in active}
        selected_id = st.session_state.get("editor_draft_id")
        if selected_id not in labels:
            selected_id = active[0]["id"] if active else None
        if not selected_id:
            draft = service.new_draft("Engineering draft")
            selected_id = draft["id"]
            labels[selected_id] = draft["label"]
        requested = st.session_state.pop("editor_open_draft", None)
        if requested in labels:
            st.session_state.editor_draft_picker = requested
        if st.session_state.get("editor_draft_picker") not in labels:
            st.session_state.editor_draft_picker = selected_id
        draft_id = st.selectbox("Saved draft", list(labels), format_func=labels.get, key="editor_draft_picker")
        if draft_id != st.session_state.get("editor_draft_id"):
            st.session_state.editor_selection = None
            st.session_state.editor_panel = "selection"
        st.session_state.editor_draft_id = draft_id
        if st.button("New draft from published graph"):
            draft = service.new_draft("Engineering revision")
            st.session_state.editor_draft_id = draft["id"]
            st.session_state.editor_open_draft = draft["id"]
            st.rerun()
        edit = st.toggle("Edit draft", value=True)
        search = st.text_input("Search nodes", placeholder="Component, fault, symptom or ID")
        with st.expander("Checks, rules and sources"):
            collection = st.selectbox("Record category", ["checks", "rules", "sources"])
            draft_for_list = service.get_draft(draft_id)
            choices = [x["id"] for x in records(draft_for_list, collection)]
            target = st.selectbox("Record", choices) if choices else None
            if st.button("Inspect record", disabled=not target):
                st.session_state.editor_selection = {"collection": collection, "id": target}
                st.session_state.editor_panel = "selection"
            if st.button("Create " + collection[:-1], disabled=not edit):
                st.session_state.editor_panel = collection
                st.session_state.editor_selection = None
                st.session_state.pop("editor_check_node", None)
    draft = service.get_draft(draft_id)
    notice = st.session_state.pop("editor_notice", None)
    if notice:
        st.success(notice)
    st.caption(f"Published: {current['version']} · Draft based on: {draft['base_version']} · Local edits save automatically to the draft")
    a, b, c, d = st.columns([2, 1, 1, 1.3])
    a.markdown("**Draft → Validate → Publish**")
    if b.button("Save draft", disabled=not edit):
        _change(service, draft, service.save_draft, draft_id, draft["seq"])
    if c.button("Validate", disabled=not edit):
        service.validate(draft_id, draft["seq"])
        st.session_state.editor_panel = "publish"
        st.rerun()
    if d.button("Review / publish", disabled=not edit):
        st.session_state.editor_panel = "publish"
    view_label = st.radio("Graph view", list(VIEWS), horizontal=True, label_visibility="collapsed")
    view = VIEWS[view_label]
    with st.sidebar:
        with st.expander("Visible types"):
            defaults = PHYSICAL if view == "architecture" else PHYSICAL | FUNCTIONAL if view == "dependencies" else PHYSICAL | {"fault", "condition", "symptom", "check"}
            kinds = st.multiselect("Node types", list(NODE_LAYERS), default=[k for k in NODE_LAYERS if k in defaults], key="node_filters_" + view)
            edge_kinds = st.multiselect("Relationship types", EDGE_TYPES, default=VIEW_EDGES[view], key="edge_filters_" + view)
    nodes = [n for n in records(draft, "nodes") if n["type"] in kinds]
    if view == "causal" and not search.strip():
        connected = {endpoint for e in records(draft, "edges") if e["type"] in edge_kinds for endpoint in (e["source"], e["target"])}
        nodes = [n for n in nodes if n["type"] not in PHYSICAL or n["id"] in connected]
    if search.strip():
        matches = {n["id"] for n in nodes if search.casefold() in " ".join([n["id"], n["label"], *n["aliases"]]).casefold()}
        included = matches.copy()
        for edge in records(draft, "edges"):
            if edge["source"] in matches or edge["target"] in matches:
                included.update([edge["source"], edge["target"]])
        for rule in records(draft, "rules"):
            path_nodes = {x for e in records(draft, "edges") if e["id"] in rule["path_edge_ids"] for x in (e["source"], e["target"])}
            if {rule["fault_id"], rule["component_id"], *rule["symptom_ids"], *rule["predictions"], *path_nodes} & matches:
                included.update([rule["fault_id"], rule["component_id"], *rule["symptom_ids"], *rule["predictions"]])
                included.update(path_nodes)
        nodes = [n for n in nodes if n["id"] in included]
    ids = {n["id"] for n in nodes}
    edges = [e for e in records(draft, "edges") if e["type"] in edge_kinds and e["source"] in ids and e["target"] in ids]
    canvas, panel = st.columns([2.1, 1], gap="medium")
    selection = st.session_state.get("editor_selection")
    with canvas:
        layout = st.session_state.get("editor_positions", {}).get(view, service.layout(view))
        if search.strip():
            layout = {**layout, "viewport": None}
        result = CANVAS(data={"nodes": nodes, "edges": edges, "view": view, "layout": layout,
                             "selected": selection, "edit": edit, "draft_id": draft_id, "seq": draft["seq"]},
                        key="graph_canvas_" + view, on_action_change=lambda: None, height=745)
        if result.action:
            try:
                _event(service, draft, result.action, edit)
            except (ValueError, KeyError, StopIteration) as exc:
                st.error("Canvas edit rejected: " + str(exc))
        st.caption("This canvas shows the draft. Only published revisions are used by ordinary troubleshooting.")
        with st.expander("Version history and rollback"):
            history = service.history()
            st.dataframe(history, hide_index=True)
            version = st.selectbox("Published version to inspect / restore", [h["version"] for h in history])
            old = service.revision(version)
            st.download_button("Export selected graph and provenance", json.dumps(old, indent=2), file_name=version + ".json", mime="application/json")
            if st.button("Restore this version as a draft", disabled=not edit):
                restored = service.new_draft("Restore " + version, restore_version=version)
                st.session_state.editor_draft_id = restored["id"]
                st.session_state.editor_open_draft = restored["id"]
                st.session_state.editor_panel = "publish"
                st.rerun()
            st.caption("Restore creates a draft. Validation and review publish it as a new revision; history is preserved.")
    with panel, st.container(height=800, border=False):
        which = st.session_state.get("editor_panel", "selection")
        value, collection = None, None
        if which in {"selection", "checks"} and selection:
            collection = selection["collection"]
            value = next((x for x in records(draft, collection) if x["id"] == selection["id"]), None)
        try:
            if which == "publish":
                _publication(service, draft)
            elif which == "fault":
                _fault_form(service, draft, edit)
            elif which == "node" or collection == "nodes" and value:
                _node_form(service, draft, value, edit)
            elif which == "edge" or collection == "edges" and value:
                _edge_form(service, draft, value, edit)
            elif which == "checks" or collection == "checks" and value:
                _check_form(service, draft, value, edit)
            elif which == "rules" or collection == "rules" and value:
                _rule_form(service, draft, value, edit)
            elif which == "sources" or collection == "sources" and value:
                _source_form(service, draft, value, edit)
            else:
                st.subheader("Knowledge inspector")
                st.write("Select a node or relationship to inspect its properties and evidence.")
                st.caption("Start with the system architecture, explore dependencies, or follow a causal fault path.")
                if st.button("Add Fault Mode", disabled=not edit):
                    st.session_state.editor_panel = "fault"
                    st.rerun()
        except ValueError as exc:
            st.error(str(exc))
