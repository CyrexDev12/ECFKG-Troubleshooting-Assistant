"""Human-authored fault bundles; no model-generated or automatically approved facts."""
from ecfkg.schema import Node, Edge, Rule, Check


DEMO_SYMPTOM = "The DMM displays the synthetic amber aperture flag 018."
DEMO_FIELDS = {
    "stem": "APERTURE_018", "component_id": "C_DMM",
    "fault_label": "Synthetic DMM aperture configuration mismatch",
    "description": "Hypothetical configuration mismatch in the generic DMM; introduced solely to test graph editing.",
    "condition_label": "Synthetic aperture mismatch condition",
    "symptom_label": "Synthetic amber aperture flag 018", "alias": "amber aperture flag 018",
    "conditions": "Synthetic demonstration only; generic voltage verification is active and aperture mismatch is explicitly observed.",
    "check_label": "Review the synthetic DMM aperture setting",
    "instructions": "Record the hypothetical aperture setting from the supplied generic observation; do not operate hardware.",
}


def fault_operations(*, stem, component_id, fault_label, description, condition_label,
                     symptom_label, alias, conditions, check_label, instructions,
                     source_id, basis="synthetic_demo"):
    ids = {kind: f"{prefix}_{stem}" for kind, prefix in [("fault", "F"), ("condition", "COND"),
                                                       ("symptom", "S"), ("check", "CHECK"), ("rule", "R")]}
    nodes = [Node(id=ids[kind], type=kind, layer="diagnostic" if kind == "check" else "causal",
                  label=label, description=description if kind == "fault" else conditions,
                  aliases=[alias] if kind == "symptom" else [], source_ids=[source_id],
                  status="reviewed" if basis == "verified_public" else "synthetic")
             for kind, label in [("fault", fault_label), ("condition", condition_label),
                                  ("symptom", symptom_label), ("check", check_label)]]
    edges = []
    for suffix, start, end, kind in [("1", ids["fault"], ids["condition"], "CAUSES"),
                                    ("2", ids["condition"], ids["symptom"], "CAUSES"),
                                    ("AFFECTS", ids["fault"], component_id, "AFFECTS"),
                                    ("CHECKS", ids["check"], ids["fault"], "CHECKS")]:
        edges.append(Edge(id=f"E_{stem}_{suffix}", source=start, target=end, type=kind,
                          basis=basis, source_ids=[source_id], description=conditions,
                          condition=conditions if kind == "CAUSES" else None,
                          rule_id=ids["rule"] if kind == "CAUSES" else None))
    check = Check(id=ids["check"], label=check_label, instructions=instructions,
                  outcomes={"configuration_mismatch": "Synthetic mismatch observed", "normal": "Expected configuration observed",
                            "unknown": "Not checked or inconclusive"}, source_ids=[source_id])
    rule = Rule(id=ids["rule"], fault_id=ids["fault"], component_id=component_id,
                symptom_ids=[ids["symptom"]], conditions=[conditions], predictions={ids["check"]: "configuration_mismatch"},
                path_edge_ids=[e.id for e in edges if e.type == "CAUSES"], basis=basis, source_ids=[source_id])
    return [*(('nodes', n.model_dump(), True) for n in nodes),
            *(('edges', e.model_dump(), True) for e in edges),
            ('checks', check.model_dump(), True), ('rules', rule.model_dump(), True)]
