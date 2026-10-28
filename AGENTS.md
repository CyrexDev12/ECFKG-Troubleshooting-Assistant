# Project boundaries

This is a research prototype for a generic, synthetic PXI voltage-measurement station.
Never ingest restricted product manuals, proprietary station data, credentials, personal
information, export-controlled material, or production configurations. The supplied scope
is requirements input only. Do not copy signatures or correspondence into this repository.
No instrument control, maintenance automation, model downloads, or automatic promotion
of user/model statements into the knowledge graph. The user's API-first revision permits
explicit OpenAI-compatible API inference for approved generic/synthetic inputs. Show the
provider destination and transmission boundary. Never send restricted data or store/export
API keys. Local LLM hosting is deferred; keep the deterministic demo available.
The user authorized an interactive engineer graph editor. Human-authored changes must stay
in drafts until validation and explicit local review publish an immutable revision. Never let
the LLM approve edits. Keep layout separate and preserve revision references in past sessions.

Preserve theory/scenario separation and provenance on every causal/diagnostic claim.
Public availability is not approval: pending sources stay outside runtime data.
Label synthetic demonstrations and engineering assumptions. Do not claim legal compliance,
real equipment validation, completed live LLM runs, or engineer time savings without evidence.

# Development

Python 3.11+, typed small modules, Pydantic validation, JSON data, NetworkX MultiDiGraph.
Keep agent inputs independent of simulator fault state and evaluation keys.
Bound read-only tools, traversal, HTTP size, model calls, and argument lengths.
No unrestricted execution tools. No hidden fallback from LLM mode to baseline.
Keep all raw LLM text untrusted; only validated evidence references reach the UI.
Use local, explicit exports. Generated user sessions, weights and secrets are git-ignored.
Repository documentation uses Markdown; no external publication is requested.

# Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ecfkg.evaluate --out outputs/baseline
.\.venv\Scripts\python.exe -m ecfkg.evaluate --mode api --out outputs/local-api
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Keep JSON/CSV evaluation results reproducible and clearly distinguish real versus mock
execution. Read `docs/evaluation.md` before altering scoring, case eligibility or metrics.

