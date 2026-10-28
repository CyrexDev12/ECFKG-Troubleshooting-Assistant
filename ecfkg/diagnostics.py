"""Transparent synthetic rule scoring. Scores are not probabilities."""
from __future__ import annotations

from collections import Counter
import re

from ecfkg.graph import KnowledgeGraph
from ecfkg.schema import Assessment, Candidate, Interpretation, Observation

OUT_OF_SCOPE = re.compile(r"adcp|f-?15|weapon|radar|uut\s+(?:internal|fault)|patient|medical|password|credential|ignore.{0,30}instruction|shell command", re.I)


def interpret_baseline(text: str, graph: KnowledgeGraph) -> Interpretation:
    if not text.strip() or len(text) > 2000 or OUT_OF_SCOPE.search(text):
        return Interpretation(supported=False)
    entities = graph.find_relevant_entities(text)
    symptoms = [e["id"] for e in entities if e["type"] == "symptom"]
    # Denials and uncertainty about whether a symptom exists are deliberately conservative.
    if re.search(r"\b(?:not|never|no longer|isn't|is not)\b.{0,25}(?:zero|failing|timeout|missing)", text, re.I):
        symptoms = []
    return Interpretation(symptom_ids=symptoms[:3],
                          component_ids=[e["id"] for e in entities if e["type"] != "symptom"][:8],
                          supported=bool(symptoms))


def abstain(reason: str) -> Assessment:
    return Assessment(status="abstain", reason=reason, candidates=[], next_check=None,
                      eligible_count=0, truncated=False, evidence_ids=[])


def assess(graph: KnowledgeGraph, interpretation: Interpretation,
           observations: list[Observation], limit: int = 3) -> Assessment:
    if not interpretation.supported or not interpretation.symptom_ids:
        return abstain("No supported station symptom. Describe the voltage reading or communication error.")
    if any(s not in graph.nodes or graph.nodes[s].type != "symptom" for s in interpretation.symptom_ids):
        return abstain("Unknown symptom identifier.")
    seen: dict[str, str] = {}
    for obs in observations:
        if obs.check_id not in graph.checks or obs.outcome not in graph.checks[obs.check_id].outcomes:
            raise ValueError("Invalid observation")
        if obs.outcome == "unknown":
            continue
        if obs.check_id in seen and seen[obs.check_id] != obs.outcome:
            return abstain("Conflicting outcomes for the same check. Start a new session after resolving the conflict.")
        seen[obs.check_id] = obs.outcome
    rules = [graph.rules[r["id"]] for r in graph.get_candidate_faults(
        interpretation.symptom_ids, interpretation.component_ids)]
    rules = [r for r in rules if set(interpretation.symptom_ids) <= set(r.symptom_ids)]
    scored = []
    for rule in rules:
        support = [f"Symptom {s} matches {rule.id}" for s in interpretation.symptom_ids if s in rule.symptom_ids]
        contra = []
        for check, outcome in seen.items():
            expected = rule.predictions.get(check)
            if expected is not None:
                message = f"{check}={outcome}; {rule.id} predicts {expected}"
                (support if outcome == expected else contra).append(message)
        symptom_count = len(set(rule.symptom_ids) & set(interpretation.symptom_ids))
        score = 2 * symptom_count + 3 * (len(support) - symptom_count) - 4 * len(contra)
        scored.append((score, rule, support, contra))
    # Contradictions remain visible, but cannot establish a single-fault solution.
    consistent = [x for x in scored if not x[3]]
    if not consistent:
        return abstain("No modeled single fault explains these observations. Recheck evidence or extend the reviewed model.")
    scored.sort(key=lambda x: (-x[0], x[1].fault_id))
    best_score = max(x[0] for x in consistent)
    plausible = [x for x in consistent if x[0] == best_score]
    unresolved = [c for c in graph.checks if c not in seen]
    next_check = None
    # Gini partition score; use every plausible cause, not just the displayed top three.
    gains = []
    for check_id in unresolved:
        counts = Counter(x[1].predictions.get(check_id, "unknown") for x in plausible)
        gain = 1 - sum((n / len(plausible)) ** 2 for n in counts.values())
        if gain > 0:
            gains.append((gain, check_id))
    if gains:
        next_check = sorted(gains, key=lambda x: (-x[0], list(graph.checks).index(x[1])))[0][1]
    elif len(plausible) == 1:
        rule = plausible[0][1]
        # Prefer a direct abnormal confirmation over another normal check.
        next_check = next((c for c in unresolved if rule.predictions.get(c) not in {None, "normal"}), None)
    displayed = [x for x in scored if x[0] > 0][:max(1, min(limit, 3))]
    candidates = []
    for score, rule, support, contra in displayed:
        candidates.append(Candidate(
            fault_id=rule.fault_id, description=graph.nodes[rule.fault_id].description,
            score=score, supporting=support, contradicting=contra,
            path_edge_ids=rule.path_edge_ids, source_ids=rule.source_ids, basis=rule.basis,
            uncertainty="Single-fault logical model only; conditions require confirmation. Scores are not probabilities.",
            suggested_check=next_check,
            reference_case_ids=[n["id"] for n in graph.reference_cases(rule.fault_id)]))
    distinct = len(plausible) == 1
    return Assessment(
        status="candidate_identified" if distinct else "needs_observations",
        reason=("One candidate fits the recorded evidence within the synthetic single-fault model. Human review required."
                if distinct else f"{len(plausible)} causes remain tied. Only up to three are displayed; order within ties is by ID. Record a distinguishing check."),
        candidates=candidates, next_check=next_check, eligible_count=len(consistent),
        truncated=len([x for x in scored if x[0] > 0]) > len(displayed),
        evidence_ids=sorted({e for c in candidates for e in [*c.source_ids, *c.path_edge_ids]}))

