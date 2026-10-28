import copy
import json

import pytest

from ecfkg.agent import Agent, export_session
from ecfkg.fault_authoring import DEMO_FIELDS, DEMO_SYMPTOM, fault_operations
from ecfkg.graph import KnowledgeGraph
from ecfkg.graph_service import GraphService, records
from ecfkg.schema import Node, Edge, Observation
from ecfkg.storage import atomic_json, digest, read_json
from ecfkg.tools import ToolRouter


@pytest.fixture
def service(tmp_path, monkeypatch):
    root = tmp_path / "graph-store"
    monkeypatch.setenv("ECFKG_GRAPH_STORE", str(root))
    return GraphService(root)


def extra_node(identifier="C_EXTRA"):
    return Node(id=identifier, type="component", layer="physical", label="Extra generic component",
                description="Synthetic architecture addition", source_ids=["SRC_MODEL"], properties={"slot": "7"}).model_dump()


def publish(service, draft):
    report = service.validate(draft["id"], draft["seq"])
    assert report["valid"], report["errors"]
    return service.publish(draft["id"], draft["seq"], "Automated synthetic verification", "Automated test reviewer", approved=True)


def add_fault(service):
    draft = service.new_draft("Synthetic aperture example")
    return service.upsert_many(draft["id"], fault_operations(**DEMO_FIELDS, source_id="SRC_MODEL"), draft["seq"])


def test_node_and_relationship_crud_round_trip(service):
    draft = service.new_draft()
    node = extra_node()
    draft = service.upsert(draft["id"], "nodes", node, draft["seq"], create=True)
    node["label"] = "Updated component"
    draft = service.upsert(draft["id"], "nodes", node, draft["seq"])
    edge = Edge(id="E_EXTRA", source="C_DMM", target="C_EXTRA", type="DEPENDS_ON", basis="synthetic_demo", source_ids=["SRC_MODEL"]).model_dump()
    draft = service.upsert(draft["id"], "edges", edge, draft["seq"], create=True)
    edge.update(source="C_HOST", type="CONTROLS", description="Explicit logical control")
    draft = service.upsert(draft["id"], "edges", edge, draft["seq"])
    loaded = GraphService(service.root).get_draft(draft["id"])
    assert loaded == draft
    assert next(n for n in loaded["knowledge"]["nodes"] if n["id"] == "C_EXTRA")["properties"] == {"slot": "7"}
    with pytest.raises(ValueError, match="confirmation"):
        service.delete(draft["id"], "nodes", "C_EXTRA", draft["seq"])
    assert service.deletion_plan(draft["id"], "nodes", "C_EXTRA")["remove"]["edges"] == ["E_EXTRA"]
    draft = service.delete(draft["id"], "nodes", "C_EXTRA", draft["seq"], confirmed=True)
    assert not any(n["id"] == "C_EXTRA" for n in records(draft, "nodes"))
    assert not any(e["id"] == "E_EXTRA" for e in records(draft, "edges"))


@pytest.mark.parametrize("mutation", ["wrong_type", "missing_node", "duplicate_id", "causal_no_condition"])
def test_invalid_mutations_rejected_without_changing_draft(service, mutation):
    draft = service.new_draft()
    edge = Edge(id="E_TEST", source="C_DMM", target="C_HOST", type="CONNECTED_TO", basis="synthetic_demo", source_ids=["SRC_MODEL"]).model_dump()
    if mutation == "wrong_type": edge.update(type="CAUSES", condition="assumed", rule_id="R_DMM")
    if mutation == "missing_node": edge["target"] = "MISSING"
    if mutation == "duplicate_id": edge["id"] = "E_DMM_MEASURES"
    if mutation == "causal_no_condition": edge.update(source="F_DMM", target="COND_DMM", type="CAUSES", rule_id="R_DMM")
    with pytest.raises(ValueError): service.upsert(draft["id"], "edges", edge, draft["seq"], create=True)
    assert service.get_draft(draft["id"]) == draft


def test_draft_isolation_publication_engine_reload_and_provenance(service):
    before_graph = KnowledgeGraph()
    before = Agent(before_graph).run(DEMO_SYMPTOM, [])
    assert before.assessment.status == "abstain"
    old_export = export_session([before])
    draft = add_fault(service)
    assert Agent(KnowledgeGraph()).run(DEMO_SYMPTOM, []).assessment.status == "abstain"
    version = publish(service, draft)["version"]
    after_graph = KnowledgeGraph()
    after = Agent(after_graph).run(DEMO_SYMPTOM, [])
    assert [c.fault_id for c in after.assessment.candidates] == ["F_APERTURE_018"]
    assert after.assessment.next_check == "CHECK_APERTURE_018"
    assert after.assessment.candidates[0].basis == "synthetic_demo"
    assert after.config["graph_version"] == version
    assert export_session([before]) == old_export
    assert before_graph.knowledge.version != after_graph.knowledge.version
    tool = ToolRouter(after_graph)
    assert tool.invoke("get_candidate_faults", {"symptom_ids": ["S_APERTURE_018"], "component_ids": ["C_DMM"]})[0]["fault_id"] == "F_APERTURE_018"
    restored_process = GraphService(service.root).graph()
    assert restored_process.sources["SRC_MODEL"].model_dump() == before_graph.sources["SRC_MODEL"].model_dump()
    assert restored_process.edges["E_APERTURE_018_1"].source_ids == ["SRC_MODEL"]
    assert restored_process.data_hash == after_graph.data_hash


def test_layout_only_does_not_change_data_version_or_validation(service):
    draft = service.new_draft()
    draft = service.upsert(draft["id"], "nodes", extra_node(), draft["seq"], create=True)
    report = service.validate(draft["id"], draft["seq"])
    before = service.current()
    service.save_layout("architecture", {"C_DMM": {"x": 42, "y": 89}}, {"x": 0, "y": 1, "zoom": .7})
    assert service.current() == before
    assert service.get_draft(draft["id"])["validation"] == report
    assert GraphService(service.root).layout("architecture")["positions"]["C_DMM"]["x"] == 42


def test_history_diff_and_rollback_publish_a_new_revision(service):
    original = service.current()
    draft = add_fault(service)
    changes = service.diff(draft["id"])
    assert any(c["id"] == "F_APERTURE_018" and c["before"] is None for c in changes)
    newer = publish(service, draft)
    rollback = service.new_draft("Restore original", restore_version=original["version"])
    assert service.current()["version"] == newer["version"]
    restored = publish(service, rollback)
    assert restored["version"] not in {newer["version"], original["version"]}
    assert len(service.history()) == 3
    assert Agent(KnowledgeGraph()).run(DEMO_SYMPTOM, []).assessment.status == "abstain"
    assert any(c["id"] == "F_APERTURE_018" and c["after"] is None for c in restored["changes"])


def test_causal_deletion_updates_evidence_and_keeps_existing_cases(service):
    publish(service, add_fault(service))
    draft = service.new_draft()
    plan = service.deletion_plan(draft["id"], "edges", "E_APERTURE_018_1")
    assert "R_APERTURE_018" in plan["remove"]["rules"]
    assert "E_APERTURE_018_2" in plan["remove"]["edges"]
    draft = service.delete(draft["id"], "edges", "E_APERTURE_018_1", draft["seq"], confirmed=True)
    report = service.validate(draft["id"], draft["seq"])
    assert report["valid"] and len(report["cases"]) == 20
    assert not any(c["changed"] for c in report["cases"])
    publish(service, draft)
    assert Agent(KnowledgeGraph()).run(DEMO_SYMPTOM, []).assessment.status == "abstain"


def test_regression_conflicts_and_publication_approval(service):
    draft = service.new_draft()
    draft = service.delete(draft["id"], "edges", "E_CAUSE_SUPPLY_1", draft["seq"], confirmed=True)
    report = service.validate(draft["id"], draft["seq"])
    assert not report["valid"] and any(c["regression"] for c in report["cases"])
    with pytest.raises(ValueError): service.publish(draft["id"], draft["seq"], "Remove supply", "Local reviewer", approved=True)
    good = add_fault(service)
    service.validate(good["id"], good["seq"])
    with pytest.raises(ValueError, match="approval"): service.publish(good["id"], good["seq"], "Example", "Reviewer")
    publish(service, good)
    stale = service.validate(draft["id"], draft["seq"])
    assert not stale["valid"] and any("Published version changed" in e for e in stale["errors"])


def test_edit_invalidates_validation_and_stale_write_is_rejected(service):
    draft = add_fault(service)
    service.validate(draft["id"], draft["seq"])
    updated = service.upsert(draft["id"], "nodes", extra_node(), draft["seq"], create=True)
    assert updated["validation"] is None
    with pytest.raises(ValueError, match="another session"): service.save_draft(draft["id"], draft["seq"])
    with pytest.raises(ValueError, match="Validate"): service.publish(updated["id"], updated["seq"], "Changed", "Reviewer", approved=True)


def test_atomic_pointer_failure_keeps_last_published_graph(service, monkeypatch):
    import ecfkg.storage as storage
    draft = add_fault(service)
    service.validate(draft["id"], draft["seq"])
    original = service.current()
    replace = storage.os.replace
    def fail_pointer(src, dst):
        if str(dst).endswith("current.json"):
            raise OSError("Simulated interrupted publication")
        return replace(src, dst)
    monkeypatch.setattr(storage.os, "replace", fail_pointer)
    with pytest.raises(OSError): service.publish(draft["id"], draft["seq"], "Example", "Reviewer", approved=True)
    assert service.current() == original
    assert len(service.history()) == 1
    assert read_json(service.root / "current.json.bak")["version"] == original["version"]


def test_reconnect_and_parallel_relationships_preserve_ids(service):
    draft = service.new_draft()
    original = next(e for e in records(draft, "edges") if e["id"] == "E_CONNECT_C_LEAD_C_DMM")
    edge = {**original, "target": "C_HOST"}
    draft = service.upsert(draft["id"], "edges", edge, draft["seq"])
    parallel = {**edge, "id": "E_PARALLEL", "condition": "A distinct synthetic condition"}
    draft = service.upsert(draft["id"], "edges", parallel, draft["seq"], create=True)
    report = service.validate(draft["id"], draft["seq"])
    assert report["valid"] and any("Parallel conditional" in w for w in report["warnings"])
    publish(service, draft)
    graph = service.graph()
    assert graph.edges[original["id"]].target == "C_HOST"
    assert graph.graph.number_of_edges("C_LEAD", "C_HOST") == 2


def test_causal_condition_and_source_changes_survive_publish_and_export(service):
    draft = add_fault(service)
    for edge in [e for e in records(draft, "edges") if e.get("rule_id") == "R_APERTURE_018"]:
        edge = {**edge, "condition": "Only while synthetic configuration mode 018 is enabled"}
        draft = service.upsert(draft["id"], "edges", edge, draft["seq"])
    version = publish(service, draft)
    restored = KnowledgeGraph.from_data(version["knowledge"], version["sources"])
    assert restored.edges["E_APERTURE_018_1"].condition.startswith("Only while")
    turn = Agent(restored).run(DEMO_SYMPTOM, [Observation(check_id="CHECK_APERTURE_018", outcome="configuration_mismatch")])
    assert turn.assessment.status == "candidate_identified"
    assert "E_APERTURE_018_1" in export_session([turn])


def test_editor_page_and_saved_draft_reload(service):
    from streamlit.testing.v1 import AppTest
    from ecfkg.graph import ROOT
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    next(s for s in at.selectbox if s.label == "Workspace").select("Knowledge graph editor").run()
    assert not at.exception
    assert any("System Knowledge Graph" in t.value for t in at.title)
    draft_id = at.session_state.editor_draft_id
    next(b for b in at.button if b.label == "Save draft").click().run()
    assert not at.exception and service.get_draft(draft_id)["seq"] == 1
    next(b for b in at.button if b.label == "Validate").click().run()
    assert not at.exception and service.get_draft(draft_id)["validation"]["valid"]


def test_fault_wizard_publish_and_existing_session_version_pin(service):
    from streamlit.testing.v1 import AppTest
    from ecfkg.graph import ROOT
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    next(b for b in at.button if b.label == "Assess symptom").click().run()
    initial_version = at.session_state.turns[-1].config["graph_version"]
    next(s for s in at.selectbox if s.label == "Workspace").select("Knowledge graph editor").run()
    next(b for b in at.button if b.label == "Add Fault Mode").click().run()
    next(c for c in at.checkbox if c.label == "Use the synthetic aperture demonstration").check().run()
    next(b for b in at.button if b.label == "Add fault path to draft").click().run()
    assert not at.exception
    draft = service.get_draft(at.session_state.editor_draft_id)
    assert any(s["id"] == "SRC_APERTURE_018" for s in draft["sources"])
    next(b for b in at.button if b.label == "Validate").click().run()
    assert not at.exception
    assert service.get_draft(draft["id"])["validation"]["valid"]
    next(c for c in at.checkbox if "approve publication" in c.label).check()
    next(b for b in at.button if b.label == "Publish reviewed changes").click().run()
    assert not at.exception
    assert not at.error, [e.value for e in at.error]
    assert service.current()["version"] != initial_version
    next(s for s in at.selectbox if s.label == "Workspace").select("Troubleshooting").run()
    assert not at.exception
    assert at.session_state.turns[-1].config["graph_version"] == initial_version
    next(t for t in at.text_area if t.label == "Reported symptom").set_value(DEMO_SYMPTOM).run()
    next(b for b in at.button if b.label == "Assess symptom").click().run()
    assert not at.exception
    assert at.session_state.turns[-1].assessment.candidates[0].fault_id == "F_APERTURE_018"
    assert next(b for b in at.button if b.label == "Simulate check").disabled


def test_editor_navigation_retains_api_settings_in_memory(service):
    from streamlit.testing.v1 import AppTest
    from ecfkg.graph import ROOT
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    at.radio(key="mode").set_value("API-assisted").run()
    at.text_input(key="api_model").set_value("synthetic-test-model").run()
    at.text_input(key="api_key").set_value("test-only-not-a-credential").run()
    at.text_area(key="symptom_input").set_value(DEMO_SYMPTOM).run()
    signature = at.session_state.run_signature
    at.selectbox(key="workspace_page").select("Knowledge graph editor").run()
    next(b for b in at.button if b.label == "Validate").click().run()
    at.selectbox(key="workspace_page").select("Troubleshooting").run()
    assert not at.exception
    assert at.radio(key="mode").value == "API-assisted"
    assert at.text_input(key="api_model").value == "synthetic-test-model"
    assert at.text_input(key="api_key").value == "test-only-not-a-credential"
    assert at.text_area(key="symptom_input").value == DEMO_SYMPTOM
    assert at.session_state.run_signature == signature


def test_new_check_node_can_open_and_complete_procedure(service):
    from streamlit.testing.v1 import AppTest
    from ecfkg.graph import ROOT
    draft = service.new_draft()
    node = {**extra_node(), "id": "CHECK_NEW", "type": "check", "layer": "diagnostic"}
    draft = service.upsert(draft["id"], "nodes", node, draft["seq"], create=True)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    at.selectbox(key="workspace_page").select("Knowledge graph editor").run()
    at.session_state.editor_selection = {"collection": "nodes", "id": "CHECK_NEW"}
    at.session_state.editor_panel = "selection"
    at.run()
    next(b for b in at.button if b.label == "Edit diagnostic procedure").click().run()
    assert not at.exception
    assert next(t for t in at.text_input if t.label == "Stable check ID").value == "CHECK_NEW"
    next(b for b in at.button if b.label == "Save check to draft").click().run()
    assert not at.exception
    assert any(c["id"] == "CHECK_NEW" for c in records(service.get_draft(draft["id"]), "checks"))
