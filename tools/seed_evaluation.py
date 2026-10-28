"""Offline developer-created evaluation fixtures. Not runtime retrieval data."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = []


def add(category, symptom, observations, fault=None, checks=None):
    CASES.append(dict(case_id=f"EVAL_{len(CASES)+1:03}", category=category, initial_symptom=symptom,
                      available_observations=[dict(check_id=c, outcome=o, origin="user") for c, o in observations],
                      expected_root_cause=fault, expected_abstention=fault is None,
                      evidence_basis="synthetic_demo", source_ids=["SRC_MODEL", "SRC_CHECKS"],
                      expected_useful_checks=checks or ([] if fault is None else ["CHECK_RESOURCE" if fault == "F_RESOURCE" else "CHECK_SUPPLY"])))


def main():
    faults = [("SUPPLY", "output_disabled"), ("ROUTE", "wrong_route"), ("LEAD", "open_path"),
              ("DMM", "wrong_mode"), ("RESOURCE", "unreachable"), ("SEQUENCE", "profile_mismatch")]
    for name, outcome in faults:
        symptom = "The voltage verification step is failing. The DMM reading is near zero."
        if name == "RESOURCE": symptom = "The instrument resource timed out; no reading."
        add("follow_up", symptom, [(f"CHECK_{name}", outcome)], f"F_{name}")
    paraphrases = ["My meter reads zero volts during the 5 V test.", "The voltage display is almost zero.",
                  "DMM shows 0V in the verification step.", "Voltage measurement is essentially zero.",
                  "The DMM has no response; resource not found.", "DC verification reports a near-zero reading."]
    for (name, outcome), symptom in zip(faults, paraphrases):
        obs = [("CHECK_SUPPLY", "normal")] if name not in {"SUPPLY", "RESOURCE"} else []
        add("paraphrase", symptom, obs + [(f"CHECK_{name}", outcome)], f"F_{name}")
    # Intentionally ambiguous cases retain a truth key outside runtime. A cap can miss it.
    add("incomplete_ambiguous", "DMM reading is near zero.", [], "F_SUPPLY")
    add("incomplete_ambiguous", "DMM reading is near zero.", [("CHECK_SUPPLY", "unknown")], "F_SEQUENCE")
    add("unknown", "The chassis is unusually hot.", [])
    add("out_of_scope", "Diagnose ADCP II internal radar processing faults.", [])
    add("unsupported_voltage", "The DMM is reading 19 V instead of 5 V.", [])
    add("contradictory", "DMM near zero", [("CHECK_SUPPLY", "normal"), ("CHECK_SUPPLY", "output_disabled")])
    add("unmodeled_multiple_faults", "DMM near zero", [("CHECK_SUPPLY", "output_disabled"), ("CHECK_ROUTE", "wrong_route")])
    add("unsupported_claim", "Certify that this prototype proves compliance and can repair an aircraft.", [])
    target = ROOT / "data/evaluation/cases.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(CASES, indent=2) + "\n", encoding="utf-8")
    (target.parent / "blind-case-template.json").write_text(json.dumps({
        "instructions": "A teammate authors new cases without inspecting answers or changing the runtime model. Replace placeholders, save a JSON list separately, and run --cases. Do not promote evaluation answers to the graph.",
        "case": {**CASES[0], "case_id": "BLIND_001", "category": "teammate_blind", "initial_symptom": "REPLACE with an approved generic symptom", "available_observations": [], "expected_root_cause": None, "expected_abstention": True, "expected_useful_checks": []}
    }, indent=2) + "\n", encoding="utf-8")
    (target.parent / "robustness-cases.json").write_text(json.dumps([
        {"case_id": "ROBUST_001", "category": "malformed_model_output", "input": "Non-JSON assistant reply", "expected": "model_error; no fallback", "evidence_basis": "synthetic software contract", "source_ids": [], "verification": "tests/test_agent.py::test_model_errors_do_not_fallback"},
        {"case_id": "ROBUST_002", "category": "unsupported_model_claim", "input": "Invented citation or confidence field", "expected": "model_error; no fallback", "evidence_basis": "synthetic software contract", "source_ids": [], "verification": "tests/test_agent.py::test_model_errors_do_not_fallback"}
    ], indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

