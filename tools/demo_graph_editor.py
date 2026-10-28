"""Reproducible isolated before/after publication demo; never edits the live workspace."""
import json
from pathlib import Path
import tempfile

from ecfkg.agent import Agent, export_session
from ecfkg.fault_authoring import DEMO_FIELDS, DEMO_SYMPTOM, fault_operations
from ecfkg.graph import ROOT
from ecfkg.graph_service import GraphService
from ecfkg.schema import Observation


def main():
    scratch = ROOT / "tmp"
    scratch.mkdir(exist_ok=True)
    out = ROOT / "outputs/editor-demo"
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as directory:
        service = GraphService(Path(directory))
        initial = service.current()
        before = Agent(service.graph()).run(DEMO_SYMPTOM, [])
        draft = service.new_draft("Isolated synthetic DMM aperture demonstration")
        draft = service.upsert_many(draft["id"], fault_operations(**DEMO_FIELDS, source_id="SRC_MODEL"), draft["seq"])
        during_draft = Agent(service.graph()).run(DEMO_SYMPTOM, [])
        validation = service.validate(draft["id"], draft["seq"])
        assert validation["valid"], validation["errors"]
        revision = service.publish(draft["id"], draft["seq"], "Add uniquely identifiable synthetic aperture fault",
                                   "Automated demonstration (not independent human review)", approved=True)
        after = Agent(GraphService(Path(directory)).graph()).run(DEMO_SYMPTOM, [])
        confirmed = Agent(service.graph()).run(DEMO_SYMPTOM, [Observation(check_id="CHECK_APERTURE_018", outcome="configuration_mismatch")])
        rollback = service.new_draft("Restore initial demonstration data", restore_version=initial["version"])
        service.validate(rollback["id"], rollback["seq"])
        service.publish(rollback["id"], rollback["seq"], "Rollback demonstration", "Automated demonstration", approved=True)
        restored = Agent(service.graph()).run(DEMO_SYMPTOM, [])
        result = {"notice": "Actual isolated deterministic-agent run. No live LLM call, actual equipment or independent validation.",
                  "symptom": DEMO_SYMPTOM, "before": before.model_dump(), "during_draft": during_draft.model_dump(),
                  "after_publish": after.model_dump(), "after_observation": confirmed.model_dump(),
                  "after_rollback": restored.model_dump(), "validation": validation, "history": service.history()}
        (out / "before-after.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        (out / "published-example.json").write_text(json.dumps(revision, indent=2), encoding="utf-8")
        (out / "session.json").write_text(export_session([before, during_draft, after, confirmed, restored]), encoding="utf-8")
        print(json.dumps({"before": before.assessment.status, "during_draft": during_draft.assessment.status,
                          "after_publish": [c.fault_id for c in after.assessment.candidates],
                          "check": after.assessment.next_check, "confirmed": confirmed.assessment.status,
                          "after_rollback": restored.assessment.status, "existing_cases": len(validation["cases"]),
                          "changed_existing_cases": sum(c["changed"] for c in validation["cases"]),
                          "regressions": sum(c["regression"] for c in validation["cases"])}, indent=2))


if __name__ == "__main__":
    main()
