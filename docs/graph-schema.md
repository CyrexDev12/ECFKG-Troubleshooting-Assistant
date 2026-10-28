# ECFKG schema and contribution guide

The initial seed is JSON under `data/runtime/`. After the first editor opening, the authoritative
published snapshot is selected by `data/workspace/current.json`; use the draft/validate/publish
editor rather than editing that snapshot. Schema definitions are in
`ecfkg/schema.py`; referential/semantic checks are in `KnowledgeGraph._validate()`.
Stable uppercase IDs survive display-name changes. JSON objects reject extra fields.

| Layer | Node types in this prototype | Example |
|---|---|---|
| System physical | component, interface, software, configuration | C_DMM, C_LOAD, C_HOST, C_CONFIG |
| Functional/signal | function, measurement | FN_VERIFY, M_VOLTAGE |
| Fault/causal | fault, condition, symptom | F_SUPPLY, COND_SUPPLY, S_ZERO |
| Diagnostic | check | CHECK_SUPPLY |
| Scenario/historical | case, with knowledge=scenario | DEV_SUPPLY_REFERENCE |
| Evidence/provenance | source | SRC_MODEL |

Theory nodes use `knowledge=theory`; reference cases use `scenario`. Theory here describes
the representational layer, not a claim that its contents are verified engineering theory.
Observations, expected outcomes and procedural instructions are typed check/session fields;
separate nodes for each are not needed in this first workflow.

| Edge type | Meaning | Diagnostic use |
|---|---|---|
| CONNECTED_TO | Physical topology only | Never converted to a cause |
| HAS_COMPONENT | Explicit directed containment; one parent, no cycles | Architecture grouping only |
| CONTROLS / PRODUCES / CONSUMES / FLOWS_TO | Logical control, functional production/consumption and directed flow | Dependency exploration only |
| DEPENDS_ON | Functional reliance in the original model | Bounded dependency exploration |
| PERFORMS / MEASURES | Functional role | Context only |
| AFFECTS | Fault's associated component | Context only |
| CAUSES | Conditional fault → condition → symptom | Must reference a rule, condition and evidence |
| CHECKS | Check addresses a fault | Diagnostic mapping |
| EXEMPLIFIES | Designated development example → fault | Optional context, no score bonus |
| SUPPORTED_BY | Entity → source | Provenance |

Each rule contains `id`, `fault_id`, `component_id`, `symptom_ids`, explicit `conditions`,
per-check categorical `predictions`, ordered `path_edge_ids`, `basis` and `source_ids`.
Paths must be contiguous causal edges belonging to that rule and end at a declared symptom.
The causal label must not be inferred from a generic connection.

Every source includes ID, title, publisher, reference, section, short original paraphrase,
access date, basis, review status, permitted use and optional approval record. Runtime
`verified_public` sources require `review_status=approved` and an approval record; source
metadata validates syntax but cannot verify whether approval is authentic. Original
synthetic data uses `synthetic_unreviewed`, as authorized by the user, not fake approval.
Engineering assumptions must remain labeled and identify review status. Rule and edge
evidence bases must agree with their source records.

## Scoring and uncertainty

A matching symptom contributes +2. Each unique known observation matching a prediction
adds +3; each contradiction subtracts 4. `unknown` is neutral. Duplicate identical checks
are not counted twice. Two different known outcomes for the same check cause abstention.
A single-fault explanation must cover all interpreted symptoms and have no contradictory
known check. If none does, the engine abstains even if some scores remain positive.

Candidates with positive scores are sorted by score, then ID, and capped at three. When
several consistent causes share the best score, the UI reports ambiguity and truncation.
Contradicted positive-score candidates may still appear with their contradictions visible.
The check selector maximizes `1 - sum((group_count / candidate_count)^2)` across predictions
for all best-scoring consistent candidates. Check declaration order breaks equal gains.
With one cause it prefers an unobserved abnormal confirmation check. Scores are neither
probabilities nor calibrated confidence. No proposed maintenance action is automated.

## Add knowledge without changing application code

Use **Knowledge graph editor** and the typed forms described in `editor-guide.md`. Nodes
now also support configuration/functional `properties` and `status`; relationships support
`description` and `status`. Defaults preserve existing seed records. Check/source nodes retain
their paired metadata records. IDs survive label edits. Multiple relationships between the
same endpoints are allowed when types, conditions or rule membership differ; exact duplicate
meaning is rejected. The manual process below describes the original seed authoring workflow.

1. Screen a proposed public reference and record it in `data/review/`; obtain authorized
   project-use/license review before promotion. Record only minimal permitted paraphrases.
2. For synthetic additions, document assumptions in `synthetic-model.md` and label the
   source `synthetic_demo`. Do not claim manufacturer support for the mechanism.
3. Add stable nodes, typed edges, explicit causal rules and check outcomes. Add source
   nodes and provenance edges. Keep case examples designated as development/reference.
4. Update independent simulator states only if a logical demonstration is needed. Do not
   have the agent read the simulator file or derive observations from evaluation answers.
5. Run integrity tests and evaluation. Obtain team review before accepting knowledge changes.
   Do not tune rules against a blind set and then report it as independent validation.

`tools/seed_demo.py` records initial authoring only. Rerunning it overwrites the original
fixtures; review a diff before using it once team edits begin. Runtime never invokes it.

