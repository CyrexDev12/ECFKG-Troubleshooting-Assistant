# User guide

Start the app using the README command and open http://127.0.0.1:8501. Read the visible
research notice. The interface identifies **ASU Capstone IEE-018** and includes a text
watermark. Baseline needs no model or API key. API controls appear in **API-assisted** mode.
Changing mode, model, endpoint or the reference-case toggle clears old results
so the displayed configuration cannot misrepresent a previous run.

## Complete switch-route walkthrough

1. Expand **Operator simulation controls**. Select **Incorrect switch route** and click
   **Load simulated station**. This resets observations and loads the same near-zero
   report used for several other faults. The selected preset is not sent to the agent.
2. Click **Assess symptom**. Five modeled causes remain tied. The display shows up to
   three and discloses the omitted ties. Candidate order within a tie is not evidence.
3. The suggested check is **Inspect supply output and setpoint**. Click **Simulate check**.
   The recorded `normal` observation rules out the supply-only explanation in this model.
4. The next suggested check is **Inspect selected measurement route**. Click **Simulate
   check** again. The `wrong_route` observation makes `F_ROUTE` the leading candidate.
5. Expand that candidate. Inspect its supporting checks, contradictions, required model
   conditions, two causal edges and `SRC_MODEL` reference. The source panel shows that
   the mechanism is original synthetic data awaiting engineering review.
6. Examine the graph and export the session JSON. It includes each input, output, recorded
   observation, evidence ID and configuration. It excludes the selected hidden preset.
7. Click **Reset / new session** before trying another report. Loading a new simulated
   state also resets the evidence. Nothing changes real instruments.

## Manual observations and uncertainty

Select a check and categorical outcome, then **Record observation**. Only record observations
already available in an approved generic/synthetic exercise. The interface is not a physical
maintenance or measurement procedure. Origins distinguish manual reports from simulator output.
An `unknown` outcome adds no diagnostic weight. Repeating the same observation adds no
weight. Contradictory known observations remain visible and trigger abstention; start a
new session after resolving the discrepancy rather than silently replacing the history.

Try `The DMM is reading 19 V instead of 5 V` to see an unsupported-symptom abstention.
Try a nominal simulator state to see that a healthy 5 V report is not forced into a fault.
Try near-zero with both `output_disabled` and `wrong_route` observations: the single-fault
model cannot explain both and should abstain. A real station may have multiple faults;
the current simulator and scorer deliberately do not resolve that case.

## API-assisted mode

Enter an HTTPS API base URL, a provider model ID and a masked key as described in `api-setup.md`.
Leave **API protocol** at `auto`: OpenAI uses Responses, as required for GPT-6.1 Sol tools.
The sidebar shows the chosen route. API failures now display the HTTP category and a next
step; keys and raw provider error text remain hidden.
Check the API connection and assess. The trace panel shows actual tool names,
validated arguments/results and model-call counts. The model interprets language and selects
references; deterministic rules own scores and check selection. Failed or malformed model
responses yield `model_error` with no candidate fallback. Select baseline explicitly to
continue without the model. A locally blocked unsupported request may make zero API calls,
which the interface labels. Mocked protocol tests do not establish live inference. The API
receives symptoms, observations and retrieved evidence; keys are excluded from exports.
Local LLM hosting is deferred.

## Maintaining the station graph

Switch Workspace to **Knowledge graph editor** for architecture, dependency and causal views.
Select an element for its typed properties, use the toolbar for creation or draw relationships,
then validate and review the diff before publishing. Drafts are persistent but do not affect
diagnostics. New assessments load the published revision; active assessments keep their old
evidence. Engineer-authored checks use manual observations unless the simulator implements
them. See `editor-guide.md` for the full workflow and synthetic DMM demonstration.

