# ASU Capstone IEE-018 — PXI Troubleshooting Lab

**Research prototype — generic/synthetic test station.** A small, working feasibility
prototype for the capstone scope. It models one voltage-verification workflow with six
station fault categories. It does not model a restricted station, product internals,
physical instruments, or maintenance operations.

## Run locally

Python 3.11 or later is required (tested with Python 3.12). From this directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open **http://127.0.0.1:8501**. The prepared `.venv` already has the dependencies installed
on the development machine. On another OS use `.venv/bin/python`. The frozen requirements
record the tested environment; `pip install -e ".[dev]"` installs the declared compatible
dependency ranges for future development. Keep this repository checkout with its data files.

1. Leave **Deterministic baseline/demo** selected and press **Assess symptom**.
2. Five causes remain tied for the near-zero symptom. The list is capped at three and
   explicitly identifies tied omissions. Scores are not probabilities.
3. Press **Simulate check** for the suggested supply check. The default synthetic state
   returns `output_disabled`, which makes `F_SUPPLY` the leading modeled cause.
4. Load a different state under **Operator simulation controls**, assess again and
   follow the checks. The assistant receives only the reported symptom and check outcomes.
5. Export the session as JSON if needed. No user session file is written automatically.

The [user guide](docs/user-guide.md) includes a switch-route walkthrough and manual entry.

## Two operating modes

**Baseline** uses lexical symptom matching, graph retrieval and deterministic rule scoring.
It makes no model calls. **API-assisted** uses a configurable OpenAI-compatible
adapter to interpret a symptom, call bounded graph tools, and select
references for an explanation.
The scorer remains deterministic. Only validated IDs and stored evidence descriptions reach
the UI; free-form model technical assertions are deliberately excluded.

Local LLM hosting is deferred. The old Ollama adapter remains in the code for future work
but is not offered in the UI or evaluation CLI. API inference is an explicit user-authorized
revision of the initial local-only plan. The API receives the entered symptom, observations
and retrieved synthetic evidence. Use approved generic data only.

Select **API-assisted**, enter an HTTPS **API base URL**, an **API model** identifier from
that provider and a masked **API key**. The default URL is `https://api.openai.com/v1`.
The automatic protocol uses `/responses` for OpenAI, including GPT-6.1 Sol, and
`/chat/completions` for other compatible providers. The selected route appears in the sidebar.
Click **Check API connection** to check the model inventory, then **Assess symptom** to
run inference. The model must support function tools and structured outputs (or JSON mode).
Keys remain in server/session memory and are excluded from diagnostic exports. Environment
configuration is also supported:

```powershell
$env:ECFKG_API_BASE_URL = "https://api.openai.com/v1"
$env:ECFKG_MODEL = "YOUR_PROVIDER_MODEL_ID"
# Set ECFKG_API_KEY / OPENAI_API_KEY securely, or use the app's masked key field.
.\.venv\Scripts\python.exe -m streamlit run app.py
```

The **Provider compatibility** panel supports protocol overrides and JSON schema or JSON
object output. Chat Completions also offers `max_completion_tokens` or `max_tokens`.
Responses uses `max_output_tokens`. Invalid output is always validated locally. Provider
credentials, billing, retention and model availability remain under your provider account.
Redirects and environment proxies are disabled. No retry, provider switch or baseline fallback
runs automatically. See [API setup](docs/api-setup.md) for the request contract and limits.

## Verification and evaluation

```powershell
.\.venv\Scripts\python.exe -m pytest -q --junitxml=outputs/verification/pytest.xml
.\.venv\Scripts\python.exe -m ecfkg.evaluate --out outputs/baseline
.\.venv\Scripts\python.exe -m ecfkg.evaluate --theory-only --out outputs/theory-only
.\.venv\Scripts\python.exe -m ecfkg.evaluate --mode api --out outputs/local-api
```

Each run exports JSON (including configuration, prompts and per-turn evidence) and CSV.
`outputs/capstone/evaluation.xlsx` includes the cases, results, comparisons and a blank
time-savings form. To rebuild it, run `node tools/export_workbook.mjs` with the Codex
bundled Node runtime and `@oai/artifact-tool` available to the script. Excel authoring is
an optional reporting dependency, not required to run or evaluate the Python application.
The existing workbook and CSV can be opened in Excel without that library. They preserve
the initial prototype evaluation, including its unavailable local-model comparison. New
API runs should use a separate output directory; missing API configuration records `not_run`.

The initial synthetic suite returned the expected root cause in 12/14 applicable cases
(85.7%), with a three-candidate cap. All six unsupported/contradictory cases abstained.
The two misses are ambiguous cases without decisive observations. These cases were
created alongside the implementation and do not provide independent validation.
See [evaluation method](docs/evaluation.md) for denominators and limitations.

## Repository map

| Path | Purpose |
|---|---|
| `ecfkg/schema.py`, `graph.py` | Validation, provenance and bounded graph retrieval |
| `ecfkg/diagnostics.py` | Transparent scoring and check selection |
| `ecfkg/agent.py`, `api_llm.py`, `tools.py` | Orchestration and bounded API adapter |
| `ecfkg/llm.py` | Shared model interface and deferred Ollama implementation |
| `ecfkg/simulator.py` | Operator-owned logical station state |
| `app.py` | Streamlit interface |
| `data/runtime/` | Editable graph and original synthetic source records |
| `data/review/` | Quarantined public source candidates; never loaded by the agent |
| `data/simulator/` | Hidden simulation presets, outside retrieval |
| `data/evaluation/` | Offline cases and answer keys, outside retrieval |
| `outputs/` | Actual synthetic evaluation results and report |
| `tests/` | Integrity, diagnostic, protocol, privacy-boundary and UI checks |

## Scope and limitations

Start with [traceability](docs/requirements-traceability.md), [architecture](docs/architecture.md),
[schema](docs/graph-schema.md), [data handling](docs/data-handling.md) and
[feasibility assessment](docs/feasibility.md). Interfaces were checked against the
[official library references](docs/implementation-references.md).

All active diagnostic evidence is synthetic and awaits engineering review. An accessed
NI public overview is retained only as a pending source candidate. Public availability
does not establish project permission. Real measurement behavior, multiple simultaneous
faults, unrestricted language understanding, source approval, live LLM performance,
engineer time savings and legal compliance remain unestablished. Human review is required.

