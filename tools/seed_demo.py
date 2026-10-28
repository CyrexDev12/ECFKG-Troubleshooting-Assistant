"""One-time authoring utility. Runtime never imports this file or evaluation answers.

The committed JSON is authoritative; do not rerun over team edits without reviewing a diff.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def save(path, data):
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main():
    sources = []
    for sid, title, section, text in [
        ("SRC_MODEL", "Original generic voltage workflow", "Modeled mechanisms", "Conditional single-fault logical mechanisms; not equipment evidence."),
        ("SRC_CHECKS", "Original diagnostic check definitions", "Checks and observations", "Categorical state checks distinguish modeled conditions; no hardware procedures."),
        ("SRC_REFERENCE", "Synthetic development reference case", "Evidence status", "A development example records an output-disabled case; not independent validation.")]:
        sources.append(dict(id=sid, title=title, publisher="Prototype authors", reference="docs/synthetic-model.md",
                            section=section, paraphrase=text, access_date="2026-10-27", basis="synthetic_demo",
                            review_status="synthetic_unreviewed", permitted_use="Original synthetic data requested by user; engineering review pending.", approval_record=None))
    save("data/runtime/sources.json", sources)
    nodes, edges, checks, rules = [], [], [], []

    def node(id, type, layer, label, description, aliases=None, knowledge="theory", source="SRC_MODEL"):
        nodes.append(dict(id=id, type=type, layer=layer, knowledge=knowledge, label=label,
                          description=description, aliases=aliases or [], source_ids=[source]))

    def edge(id, source, target, type, condition=None, rule_id=None, basis_source="SRC_MODEL"):
        edges.append(dict(id=id, source=source, target=target, type=type, basis="synthetic_demo",
                          source_ids=[basis_source], condition=condition, rule_id=rule_id))

    components = [
        ("C_HOST", "software", "Host and sequence software", ["sequence", "host", "test software"]),
        ("C_CHASSIS", "component", "PXI chassis", ["chassis"]),
        ("C_CONTROLLER", "component", "PXI controller", ["controller"]),
        ("C_SUPPLY", "component", "Programmable supply", ["supply", "power"]),
        ("C_SWITCH", "component", "Switch matrix", ["switch", "route"]),
        ("C_DMM", "component", "Digital multimeter", ["dmm", "meter", "voltage reading"]),
        ("C_LEAD", "component", "Cables and fixture", ["lead", "connector", "fixture"]),
        ("C_CONFIG", "configuration", "Instrument configuration", ["configuration"]),
        ("C_LOAD", "interface", "Opaque external load", ["external load"])]
    for id, type, label, aliases in components:
        node(id, type, "physical", label, "Generic synthetic workflow element; no product internals.", aliases)
    node("FN_VERIFY", "function", "functional", "Verify DC stimulus", "Compare the modeled DC reading to the synthetic 5 V expectation.")
    node("M_VOLTAGE", "measurement", "functional", "DC voltage reading", "A logical reading category, not a physics simulation.")
    node("S_ZERO", "symptom", "causal", "Near-zero DMM reading", "Reported near-zero voltage during the modeled 5 V step.",
         ["near zero", "near-zero", "reads zero", "reading is zero", "0 v", "0v", "zero volts", "almost zero", "essentially zero"])
    node("S_TIMEOUT", "symptom", "causal", "No fresh instrument reading", "The modeled instrument resource does not return a fresh response.",
         ["timeout", "timed out", "no reading", "missing reading", "resource not found", "no response"])
    for source in sources:
        node(source["id"], "source", "evidence", source["title"], source["paraphrase"], source=source["id"])
    for a, b in [("C_SUPPLY", "C_LOAD"), ("C_LOAD", "C_SWITCH"), ("C_SWITCH", "C_LEAD"), ("C_LEAD", "C_DMM"), ("C_CONTROLLER", "C_CHASSIS")]:
        edge(f"E_CONNECT_{a}_{b}", a, b, "CONNECTED_TO")
    for a, b in [("C_DMM", "C_CONFIG"), ("C_DMM", "C_CONTROLLER"), ("C_CONTROLLER", "C_CHASSIS"), ("FN_VERIFY", "C_SUPPLY"), ("FN_VERIFY", "C_SWITCH"), ("FN_VERIFY", "C_LEAD"), ("FN_VERIFY", "C_DMM"), ("FN_VERIFY", "C_HOST")]:
        edge(f"E_DEP_{a}_{b}", a, b, "DEPENDS_ON")
    edge("E_HOST_PERFORMS", "C_HOST", "FN_VERIFY", "PERFORMS")
    edge("E_DMM_MEASURES", "C_DMM", "M_VOLTAGE", "MEASURES")
    fault_defs = [
        ("SUPPLY", "C_SUPPLY", "Supply disabled or zero setpoint", "No modeled stimulus", "output_disabled", "Supply output is disabled or setpoint is zero.", "S_ZERO"),
        ("ROUTE", "C_SWITCH", "Incorrect switch route", "Wrong measurement point", "wrong_route", "Route selects the modeled grounded spare channel.", "S_ZERO"),
        ("LEAD", "C_LEAD", "Open or misconnected lead", "Invalid measurement path", "open_path", "Lead path is open and the synthetic input bias produces a zero category.", "S_ZERO"),
        ("DMM", "C_DMM", "Incorrect measurement configuration", "Wrong measurement function", "wrong_mode", "AC mode is selected for the ideal steady DC stimulus.", "S_ZERO"),
        ("RESOURCE", "C_CONTROLLER", "Instrument communication or resource mismatch", "No fresh response", "unreachable", "Resource does not resolve; no cached reading is substituted.", "S_TIMEOUT"),
        ("SEQUENCE", "C_HOST", "Sequence/configuration mismatch", "Wrong active step", "profile_mismatch", "Sequence runs a zero-stimulus step while expecting the 5 V profile.", "S_ZERO")]
    check_labels = {
        "SUPPLY": "Inspect supply output and setpoint", "ROUTE": "Inspect selected measurement route",
        "LEAD": "Inspect the modeled lead path", "DMM": "Inspect measurement function",
        "RESOURCE": "Inspect resource response", "SEQUENCE": "Compare active step and expected profile"}
    for name, comp, label, condition, abnormal, mechanism, symptom in fault_defs:
        cid = f"CHECK_{name}"
        node(cid, "check", "diagnostic", check_labels[name], "Read synthetic state or record a categorical report.", source="SRC_CHECKS")
        checks.append(dict(id=cid, label=check_labels[name], instructions="Simulation: inspect the modeled state. Manual: record an already available observation; this is not a physical test procedure.",
                           outcomes={"normal": "Matches nominal synthetic configuration", abnormal: mechanism, "unknown": "Not checked or inconclusive"}, source_ids=["SRC_CHECKS"]))
        node(f"F_{name}", "fault", "causal", label, mechanism)
        node(f"COND_{name}", "condition", "causal", condition, mechanism)
        edge(f"E_AFFECTS_{name}", f"F_{name}", comp, "AFFECTS")
        edge(f"E_CHECK_{name}", cid, f"F_{name}", "CHECKS", basis_source="SRC_CHECKS")
        edge(f"E_CAUSE_{name}_1", f"F_{name}", f"COND_{name}", "CAUSES", mechanism, f"R_{name}")
        edge(f"E_CAUSE_{name}_2", f"COND_{name}", symptom, "CAUSES", "Single fault, stable 5 V verification workflow; " + mechanism, f"R_{name}")
        rules.append(dict(id=f"R_{name}", fault_id=f"F_{name}", component_id=comp,
                          symptom_ids=[symptom], conditions=["Single fault; stable 5 V verification step", mechanism],
                          predictions={f"CHECK_{other}": abnormal if other == name else "normal" for other, *_ in fault_defs},
                          path_edge_ids=[f"E_CAUSE_{name}_1", f"E_CAUSE_{name}_2"], basis="synthetic_demo", source_ids=["SRC_MODEL"]))
    node("DEV_SUPPLY_REFERENCE", "case", "scenario", "Synthetic output-disabled example", "Development example: near-zero reading with output_disabled observation. It illustrates R_SUPPLY and adds no ranking weight.", knowledge="scenario", source="SRC_REFERENCE")
    edge("E_REFERENCE_SUPPLY", "DEV_SUPPLY_REFERENCE", "F_SUPPLY", "EXEMPLIFIES", basis_source="SRC_REFERENCE")
    for item in list(nodes):
        if item["type"] != "source":
            edge("E_SOURCE_" + item["id"], item["id"], item["source_ids"][0], "SUPPORTED_BY", basis_source=item["source_ids"][0])
    save("data/runtime/graph.json", dict(version="generic-voltage-1.0", nodes=nodes, edges=edges, checks=checks, rules=rules))
    state_keys = dict(SUPPLY="supply", ROUTE="route", LEAD="lead", DMM="mode", RESOURCE="resource", SEQUENCE="sequence")
    base = {v: "normal" for v in state_keys.values()}
    presets = [{"id": "NORMAL", "label": "Nominal state", "state": base}]
    for name, _, label, _, abnormal, *_ in fault_defs:
        presets.append(dict(id=name, label=label, state={**base, state_keys[name]: abnormal}))
    save("data/simulator/station.json", dict(version="logical-station-1.0", presets=presets,
         check_fields={f"CHECK_{k}": v for k, v in state_keys.items()},
         symptom_rules=[dict(field="resource", equals="unreachable", text="The DMM timed out; no reading is available."),
                        *[dict(field=state_keys[n], equals=a, text="The voltage verification step is failing. The DMM reading is near zero.") for n, _, _, _, a, *_ in fault_defs if n != "RESOURCE"]],
         nominal_symptom="The DMM reads the expected 5 V DC."))
    save("data/review/public-source-candidates.json", [{
        "id": "REVIEW_NI_PXI", "title": "An Overview of the PXI Platform", "publisher": "NI",
        "url": "https://www.ni.com/en/shop/pxi/overview-pxi.html", "section": "Introduction, Figure 2; Chassis; Controller; Peripheral Modules",
        "paraphrase": "PXI systems combine chassis, controller and modular instrumentation.", "access_date": "2026-10-27",
        "review_status": "pending", "permitted_use": "Undetermined; team must review license, scope and sharing before promotion.",
        "runtime_use": False, "causal_support": "None established for this prototype's six faults."}])


if __name__ == "__main__":
    main()

