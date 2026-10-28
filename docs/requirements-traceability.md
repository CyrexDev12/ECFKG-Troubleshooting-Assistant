# Requirements and traceability

Baseline: supplied scope statement, sections 2–7, especially Figure 1 (page 4), Figure 2
(page 7), constraints (pages 9–10), acceptance (pages 10–11) and data plan (pages 12–15).
The document is requirements input only and is not a graph source. No signature or sponsor
correspondence has been reproduced. Implementation choices remain exploratory.

## Scope requirements

| ID | Scope requirement | Implementation | Verification evidence | Status |
|---|---|---|---|---|
| S01 | Generic representative PXI station; exclude restricted product and production integration (§3) | Generic host/controller/chassis, supply, DMM, switch, fixture, opaque load | Data review; no instrument interfaces; boundary tests | Implemented narrow workflow; representativeness needs team review |
| S02 | Theory-based and scenario-based knowledge (§2, Fig. 1) | Typed layers; separate theory/scenario nodes; one synthetic development reference | Theory-only comparison and scenario toggle test | Implemented structurally; no authentic historical cases |
| S03 | Natural-language symptom to causes and troubleshooting suggestions (§2, §4) | Baseline parser; API model tools; deterministic assessment and checks | UI, HTTP contract and diagnostic tests | Baseline demonstrated; live API evaluation pending |
| S04 | Correct root cause included in at least 80% of predefined cases (§4) | 20 diagnostic cases, 14 applicable known-root cases; cap three | `outputs/baseline/results.json`: 12/14, 85.7% | Threshold met on developer-created synthetic suite only; full acceptance pending |
| S05 | Traceable evidence (§4) | Stable rule/edge/source IDs, conditional paths, source panel and export | Graph corruption tests; citation validity metric | Implemented; provenance validity does not prove technical truth |
| S06 | At least 25% estimated troubleshooting-time reduction (§4) | Excel time-estimate form and CSV template | Blank fields and tested formulas | Unmeasured; genuine engineer estimates required |
| S07 | Secure data handling and ITAR restrictions (§3, §4, §6–7) | Synthetic-only runtime, no-network baseline default, explicit API transmission notice, source gate, no telemetry setting, ignored sessions/secrets | Loading/network/export tests and documented controls | Controls implemented; compliance cannot be established by this prototype |
| S08 | Human input/review (§3, §6) | Manual observations; explicit source review; no automatic KG promotion | Manual-entry tests; no graph mutation APIs | Implemented; operating review process to be agreed |
| S09 | Excel test cases, requirements, architecture, KG design, guide and prototype (§5) | Repository documents, workbook, JSON/CSV and app | Test run, report generation and UI inspection | Delivered |
| S10 | Source metadata, screening and permitted use (§6) | Synthetic source metadata; quarantined NI candidate | Source schema and rejection tests | Public approval pending |
| S11 | Shared workspace access control, backup and retention (§6) | Local files and version-control-ready ignore rules; handoff process documented | Data-handling checklist | Team-managed workspace, backup and archive not provisioned |
| S12 | Consider listed standards and risk principles (§7) | Traceability, bounded tools, review boundaries, reproducible tests | Documents and software checks | No standard conformity or certification claimed |

## Decisions introduced by the implementation

These are proposed decisions, not additional approved scope requirements:

| ID | Decision and reason | Verification |
|---|---|---|
| D01 | Python, Streamlit, JSON, Pydantic and NetworkX MultiDiGraph; student-readable local stack | Locked installed versions and test suite |
| D02 | Six single-fault logical categories for one stable 5 V workflow | Per-fault convergence tests |
| D03 | +2 symptom match, +3 matching check, −4 contradiction; cap three, disclose ties | Scoring tests and intentionally missed ambiguous cases |
| D04 | Choose a check by its partition of all tied consistent causes | Supply-to-route interactive test |
| D05 | Six allowlisted tools, six calls, depth four, 24 paths, 25 s/request for Chat Completions or 60 s for Responses, 120 s turn deadline | Tool and HTTP failure tests |
| D06 | LLM selects only validated evidence IDs; stored descriptions provide the technical explanation | Hallucinated citation, extra confidence and changed-output rejection tests |
| D07 | Reference examples explain but do not change scores | Theory-only versus enriched comparison |
| D08 | Top-1, top-3, list size, abstention, provenance mix and latency | Evaluation exports; these supplement S04 |

## Assumptions, conflicts and deferred work

The scope assumes sufficient approved data and enough generic complexity to represent the
target problem. Neither is established. Runtime public documentation remains absent until
authorized review. A narrow workflow tests software feasibility, not representative station
coverage. Figure 2 includes additional DAQ, oscilloscope and bus modules; these are deferred
under the user's explicit narrow-workflow instruction. Figure 1's corrective-action output
is conservatively limited to human review and observation checks, consistent with §6's
restriction on autonomous maintenance decisions.

The scope's compliance acceptance language cannot be fulfilled through a synthetic demo or
local execution alone. The implementation documents controls and leaves institutional/legal
review open. The scope's broad statement about proprietary material with permission does
not override this request's explicit ban on ingesting that material.

Repository files provide a versionable deliverable; no remote repository, shared account
management, institutional archive or scheduled backup was requested or configured. The
team must implement those organizational controls. The user subsequently authorized an API-first
revision and deferred local LLM hosting. The UI now offers a configurable OpenAI-compatible API
with an explicit data-transmission notice and private credential handling. This is a documented
exploratory deviation from the original local-inference direction, not approval for restricted
data or a claim of compliance. No external publication, complex graph database, fine-tuning or
real equipment connection is included.

## Build record

1. Read the scope, inspect its two diagrams and confirm the directory was empty.
2. Build the JSON graph, six competing rules and logical simulator. Run the first loop tests.
3. Add Streamlit and the restricted local adapter. Verify mock protocol and UI behavior.
4. Add evaluation cases outside runtime, comparisons, exports, source screening and documents.

