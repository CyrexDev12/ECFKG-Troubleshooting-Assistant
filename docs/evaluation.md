# Evaluation protocol

The scope requires correct-root inclusion in at least 80% of predefined applicable cases.
The current primary population is 14 cases with a specified modeled root cause. Six
unknown/out-of-scope/contradictory cases form the abstention population. Do not silently
exclude failures, ambiguous cases or malformed-model failures from their intended population.

## Case sets and isolation

`data/evaluation/cases.json` contains 20 developer-authored diagnostic cases: six direct
follow-ups, six paraphrases with observations, two intentionally ambiguous/incomplete cases
and six abstention cases. Every case includes ID, category, initial symptom, observations,
expected root or abstention, basis, sources and useful initial checks. Two additional
software contract definitions in `robustness-cases.json` cover malformed output and invented
claims; their tests use mocks and are excluded from diagnostic accuracy denominators.

Runtime retrieval can see only the designated synthetic development example. The evaluator
passes a symptom first, then each available observation in order; final-turn results own the
reported diagnostic metrics. It does not request observations from the answer key or expose
case IDs. Stored per-turn outputs permit separate analysis of initial ambiguity. Available
observations are authored inputs, not evidence that a human would have chosen the same path.

## Measures and definitions

| Measure | Definition |
|---|---|
| Scope candidate coverage | Known root included in returned capped candidates / all known-root cases |
| Top-1 | First returned candidate is the known root / all known-root cases; tied ID order still counts literally |
| Top-3 | Known root in first three / all known-root cases; equals scope coverage at this cap |
| Average list size | Mean returned size, reported for all cases and known-root cases separately |
| Appropriate abstention | Explicit `abstain` on expected-abstention cases / all such cases; `model_error` is not a correct abstention |
| Citation/reference validity | Exported evidence IDs that resolve to loaded edges/sources / exported evidence IDs; not semantic correctness |
| Evidence coverage | Returned candidate records with verified-public versus synthetic basis / all returned candidate records |
| Latency | `perf_counter` elapsed time per agent turn; case latency sums its turns; excludes UI think time and startup preflight |
| Model errors | Final turns with model_error; failures remain in accuracy denominators if a live run began |

Additional measures are proposed operational measures, not new scope acceptance requirements.
No calibrated confidence is calculated. A cap of three prevents satisfying coverage by listing
all six faults. All tied omissions are disclosed, and incomplete cases remain failures when
their truth falls outside that list. Unique synthetic fault identification still requires review.

## Comparisons and reproducibility

**API-first revision:** the active model mode now uses a configurable OpenAI-compatible API.
Use `--mode api --out outputs/local-api` after configuring credentials and a model. `--mode llm`
is an API alias. The original `outputs/baseline`, `outputs/theory-only`, `outputs/llm` and Excel
report are preserved as historical initial-build results; the local comparison below describes
that original run. New API tests use mock HTTP and must not be reported as live-model success.

A: baseline graph workflow, actually run. B: local LLM-assisted graph workflow, preflight
attempted but **not run** because the local service refused connection. Metrics are null,
not zero, for a comparison that did not run. Baseline theory-only and theory-plus-reference
runs are also included. Their rankings are identical because references add context, not
score. This is a software ablation check, not proof that historical cases add no value.

Run commands are in the README. Results record data/case/code hashes, graph version,
dependency/Python versions, full system prompts, model identifier/digest when available,
generation settings, mock status, per-turn inputs, tool trace and outputs. `requirements-lock.txt`
records the installed environment. Fixed temperature/seed do not guarantee cross-hardware
model reproducibility. Keep future model/library versions explicit.

## Planned graph-value comparison (not run)

Once an API model is configured and sources are approved, compare B against C: the same model
and settings receiving the same allowed source facts as a flat list without relationship
traversal. Freeze cases before running both. Give both arms the same symptom, sequential
observations, facts/provenance budget and final output schema. Log exactly which facts were
accessible and the prompt token budget. Do not give C answer labels, hidden state or extra
facts. Report retrieval budget differences and whether candidate generation/scoring is held
fixed; changing the scorer as well as graph access would confound attribution. A second,
separately labeled end-to-end comparison can assess unconstrained candidate generation.
This protocol is documented, not implemented or claimed complete.

## Blind extension and human time study

A teammate should author new generic cases using `blind-case-template.json` after the graph
and prompts are frozen, without inspecting evaluation outcomes. Keep the key separate and
run `--cases path/to/new-cases.json`. Record authorship process by role and review decisions
without personal contact information. Cases designed by the same implementer are not external
validation even when stored in a separate folder.

Use the workbook's **Time estimates** sheet or `evaluation/time-estimates.csv`. For each
approved generic scenario, record anonymous participant code, manual and assisted estimates,
then separately observed task times if a controlled exercise is performed. Explain task
start/stop, document access, experience, assistance permitted and order effects. Compute
`(manual - assisted) / manual`; a valid baseline must exceed zero. The target is at least
25% lower estimated time. Keep estimates and measured times separate and blank until genuine
data exists. Response latency cannot substitute for engineer troubleshooting time.

