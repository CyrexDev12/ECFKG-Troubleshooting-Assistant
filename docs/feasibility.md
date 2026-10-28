# Feasibility assessment

Initial-build assessment as of 2026-10-27: runnable deterministic prototype; live LLM comparison not run.

**Subsequent API-first revision:** the interface now identifies ASU Capstone IEE-018 and offers
OpenAI-compatible API inference in place of the local-model selector. Local hosting is deferred.
The original results below remain historical; API protocol tests are mocked, not live model
performance. See `api-setup.md` and `outputs/verification/pytest-api.xml` for the new route.

## Demonstrated

The app loads a validated MultiDiGraph, retrieves conditional causal paths, scores competing
station faults, proposes distinguishing checks, accepts recorded/simulated observations and
updates its assessment. Removing a causal edge removes its corresponding candidate. Five
faults share the near-zero symptom; communication failure instead produces missing data.
The same assistant input produces the same result regardless of which hidden state generated
it. The evaluator and simulator keep answers outside the agent's input/tool boundary.

The UI was exercised with Streamlit AppTest and in a running local browser. The automated
suite passed **45 tests**, including graph corruption, reference validity, candidate changes,
abstention, duplicate/conflicting evidence, tool limits, remote endpoint rejection, timeouts,
malformed JSON and invented model citations. Model tests use mocks explicitly labeled as such.
Evidence: `outputs/verification/pytest.xml`.

| Actual baseline measure | Result |
|---|---|
| Diagnostic cases | 20 total; 14 known-root and 6 abstention cases |
| Scope candidate inclusion | 12/14 = 85.7% |
| Top-1 / top-3 | Both 12/14 = 85.7% on final turns |
| Mean returned list size | 1.30 overall; 1.86 on applicable cases; maximum 3 |
| Appropriate abstention | 6/6 |
| Evidence ID validity | 100% of returned IDs resolve |
| Verified-public diagnostic evidence | 0% |
| Synthetic diagnostic evidence | 100% |
| Mean response time | Approximately 0.18 ms per baseline turn in this run; see JSON for exact measurements |
| Engineer estimated/measured time savings | Unmeasured |

The 80% threshold is met **on this developer-created synthetic suite only**. These results
demonstrate software feasibility, not accuracy on actual avionics test equipment or independent
acceptance. Each fault's observations were constructed using the same modeling assumptions.
Candidate-reference validity checks existence, not the truth of a technical claim.

## Observed failure cases

`EVAL_013` (hidden supply cause, no checks) and `EVAL_014` (hidden sequence mismatch, unknown
supply check) miss the capped candidate list. Five causes remain tied, and ID-based tie order
does not put those causes in the top three. The UI discloses the ambiguity and requests a
check. Neither failure is removed from the accuracy denominator. This demonstrates why a
reported near-zero symptom alone cannot establish a cause in this model.

The Ollama preflight returned a connection failure at the default local endpoint. No model
inference was run, no weights were downloaded, and `outputs/llm/results.json` records
`not_run` with null metrics. A successful mocked adapter exchange is not a live LLM result.

## Attribution and open questions

The graph/rules currently provide causal eligibility, transparent evidence, deterministic
ranking and check selection. The LLM adapter is intended to add language interpretation,
bounded evidence requests and evidence selection; its benefit remains unmeasured. The current
explanation renderer deliberately excludes free-form generated technical facts.

Theory-only and theory-plus-reference runs produced identical rankings because the one
reference example carries no score bonus. They establish that the toggle works and evaluation
answers remain separate. They do not establish the value of historical fault data. A flat-fact
LLM comparison to isolate graph value is documented in `evaluation.md` and remains not run.

## Next decisions and experiments

1. Obtain engineering review of the six conditional mechanisms, simplified meter behavior,
   check semantics and representativeness of the voltage workflow.
2. Complete source screening and permitted-use review, then add narrowly supported public
   claims. Keep causal hypotheses distinct from documented manufacturer statements.
3. Select an API provider/model and configure credentials; run the same frozen cases and record
   model/version/digest, prompts, settings and failure rate. Compare against the baseline.
4. Have teammates create a blind set after freezing the graph and prompts, including negation,
   partial symptoms, misleading observations, genuinely unknown conditions and multiple faults.
5. Conduct an approved generic task study with real engineer estimates and separately measured
   times. Do not use response latency as evidence of the scope's 25% reduction.
6. Agree institutional workspace permissions, backup/retention and authorized compliance review.

No production equipment performance, legal compliance, source approval, engineer feedback,
time savings or independent external validation has been established.

