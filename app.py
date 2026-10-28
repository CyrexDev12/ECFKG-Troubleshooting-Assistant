"""Local Streamlit entry point. The UI alone owns the simulator."""
import os
import uuid

import graphviz
import streamlit as st

from ecfkg.agent import Agent, export_session
from ecfkg.graph import KnowledgeGraph
from ecfkg.llm import ModelError
from ecfkg.api_llm import DEFAULT_API_BASE, OpenAICompatibleAdapter, resolve_protocol
from ecfkg.schema import Observation
from ecfkg.simulator import Simulator

st.set_page_config(page_title="ASU Capstone IEE-018 | PXI Troubleshooting Lab", layout="wide")
st.markdown("""
<style>
.project-label { color: #A84B15; font-size: .85rem; font-weight: 650; letter-spacing: .09em; margin-bottom: .3rem; }
.project-watermark { position: fixed; bottom: .7rem; right: 1.25rem; color: rgba(36,39,43,.28);
    font-size: .8rem; letter-spacing: .08em; pointer-events: none; user-select: none; z-index: 10; }
</style>
<div class="project-label">ASU Capstone IEE-018</div>
<div class="project-watermark" aria-hidden="true">ASU Capstone IEE-018</div>
""", unsafe_allow_html=True)
workspace_page = st.sidebar.selectbox("Workspace", ["Troubleshooting", "Knowledge graph editor"], key="workspace_page")
if workspace_page == "Knowledge graph editor":
    # Keep session-only widget values while their troubleshooting widgets are absent.
    for key in ["mode", "api_key", "api_endpoint", "api_model", "use_cases", "api_protocol",
                "api_format", "api_token_parameter", "station_preset", "symptom_input"]:
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]
    st.title("System Knowledge Graph")
    st.caption("ASU Capstone IEE-018 · Generic/synthetic station · Local engineer workspace")
    from ecfkg.editor_ui import render_editor
    render_editor()
    st.stop()
st.title("PXI Troubleshooting Lab")
st.warning("Research prototype — generic/synthetic test station")
st.caption("Voltage verification • Traceable evidence • Human review required")


def reset():
    for key in ["turns", "observations", "active_symptom", "run_signature", "api_connection", "session_graph"]:
        st.session_state.pop(key, None)


with st.sidebar:
    st.markdown("**ASU Capstone IEE-018**")
    st.header("Session")
    modes = ["Deterministic baseline/demo", "API-assisted"]
    if st.session_state.get("mode") not in [None, *modes]:
        st.session_state.pop("mode", None)
    mode = st.radio("Execution mode", modes, key="mode")
    use_cases = st.checkbox("Include synthetic reference cases", value=True, key="use_cases")
    model, endpoint, api_key = "", "", ""
    response_format, token_parameter = "json_schema", "max_completion_tokens"
    protocol = "auto"
    if mode.startswith("Deterministic"):
        st.info("Baseline active. No LLM calls.")
    else:
        st.caption("OpenAI-compatible API. Local model hosting is deferred.")
        endpoint = st.text_input("API base URL", value=os.environ.get("ECFKG_API_BASE_URL", DEFAULT_API_BASE), key="api_endpoint")
        model = st.text_input("API model", value=os.environ.get("ECFKG_MODEL", ""), placeholder="Model ID from your provider", key="api_model")
        api_key = st.text_input("API key", type="password", key="api_key", on_change=reset,
                                help="Held in this session only. Leave blank to use ECFKG_API_KEY or OPENAI_API_KEY from the server environment.")
        with st.expander("Provider compatibility"):
            protocols = ["auto", "responses", "chat_completions"]
            protocol_default = os.environ.get("ECFKG_API_PROTOCOL", "auto")
            protocol = st.selectbox("API protocol", protocols,
                                    key="api_protocol",
                                    index=protocols.index(protocol_default) if protocol_default in protocols else 0,
                                    help="Auto uses Responses for api.openai.com and Chat Completions for other providers. GPT-6.1 Sol requires Responses for tools.")
            formats = ["json_schema", "json_object"]
            format_default = os.environ.get("ECFKG_API_RESPONSE_FORMAT", "json_schema")
            response_format = st.selectbox("Structured output format", formats,
                                          key="api_format",
                                          index=formats.index(format_default) if format_default in formats else 0,
                                          help="Use JSON schema when supported; JSON object mode still validates all returned fields locally.")
            resolved_protocol = resolve_protocol(endpoint, protocol)
            if resolved_protocol == "chat_completions":
                params = ["max_completion_tokens", "max_tokens"]
                param_default = os.environ.get("ECFKG_API_TOKEN_PARAMETER", "max_completion_tokens")
                token_parameter = st.selectbox("Token limit parameter", params,
                                              key="api_token_parameter",
                                              index=params.index(param_default) if param_default in params else 0,
                                              help="Some compatible providers require max_tokens.")
        st.caption("API route: " + ("Responses" if resolved_protocol == "responses" else "Chat Completions"))
        st.info("API mode sends your symptom, recorded observations and retrieved synthetic evidence to the configured provider. Use approved generic data only.")
        connection_settings = (endpoint, model, response_format, token_parameter, protocol)
        if st.button("Check API connection"):
            try:
                status = OpenAICompatibleAdapter(model, endpoint, api_key or None, response_format, token_parameter, protocol=protocol).status()
                st.session_state.api_connection = (connection_settings, status)
            except (ValueError, ModelError) as exc:
                st.session_state.pop("api_connection", None)
                st.error(str(exc))
        connection = st.session_state.get("api_connection")
        if connection and connection[0] == connection_settings:
            if connection[1]["listed"]:
                st.success("API key accepted; model is listed")
            else:
                st.warning("API reachable, but this model is not listed. Check the model ID and project access.")
            st.caption("This checks model access only. Assess symptom tests inference and tools.")
        else:
            st.caption("API connection: not checked for these settings.")
    st.button("Reset / new session", on_click=reset)
    st.divider()
    with st.expander("Operator simulation controls"):
        st.caption("These controls are outside the assistant's evidence view. Loading a state starts a new session.")
        presets = Simulator.presets()
        preset = st.selectbox("Hidden station state", list(presets), index=1, format_func=presets.get, key="station_preset")
        if st.button("Load simulated station"):
            reset()
            st.session_state.simulator = Simulator(preset)
            st.session_state.symptom_input = st.session_state.simulator.symptom()
            st.rerun()

signature = (mode, use_cases, model, endpoint, response_format, token_parameter, protocol)
if st.session_state.get("run_signature") not in {None, signature}:
    reset()
st.session_state.run_signature = signature
current_graph = KnowledgeGraph(include_scenarios=use_cases)
graph = st.session_state.get("session_graph", current_graph)
if graph.knowledge.version != current_graph.knowledge.version:
    st.info("A new graph version is published. This session keeps its original evidence; Assess symptom starts with the new version.")
st.session_state.setdefault("turns", [])
st.session_state.setdefault("observations", [])
st.session_state.setdefault("simulator", Simulator())
st.session_state.setdefault("symptom_input", "The voltage verification step is failing. The DMM reading is near zero.")


def run_turn():
    try:
        adapter = OpenAICompatibleAdapter(model, endpoint, api_key or None, response_format, token_parameter, protocol=protocol) if mode == "API-assisted" else None
        with st.spinner("Assessing recorded evidence..."):
            turn = Agent(graph, adapter).run(st.session_state.active_symptom, st.session_state.observations)
        st.session_state.turns.append(turn)
    except (ValueError, ModelError) as exc:
        st.error(str(exc))


symptom = st.text_area("Reported symptom", key="symptom_input", max_chars=2000, height=100)
st.caption("Enter approved generic observations only. Do not paste restricted documents, credentials or personal data.")
if st.button("Assess symptom", type="primary"):
    graph = current_graph
    st.session_state.session_graph = graph
    st.session_state.assessment_id = uuid.uuid4().hex
    st.session_state.observations = []
    st.session_state.turns = []
    st.session_state.active_symptom = symptom
    run_turn()

if not st.session_state.turns:
    st.info("Describe a voltage symptom, then assess it. Record observations to distinguish competing causes.")
    st.stop()

turn = st.session_state.turns[-1]
assessment = turn.assessment
st.caption(f"Current result: {turn.mode} • {assessment.status} • {turn.elapsed_ms:.1f} ms • graph {graph.knowledge.version}")
if turn.mode in {"llm", "api"}:
    st.caption("API turn status: " + ("failed; no fallback ran" if assessment.status == "model_error" else
               "completed" if turn.config["llm_inference_requests"] else "no model call; input handled by local scope guard"))
if symptom != st.session_state.active_symptom:
    st.warning("The symptom text has changed. Press Assess symptom to start a fresh assessment; checks below still apply to the previous report.")
if assessment.status == "model_error":
    st.error(assessment.reason)
else:
    st.info(assessment.reason)
left, right = st.columns([1.65, 1])
with left:
    st.subheader("Ranked candidate causes")
    for rank, candidate in enumerate(assessment.candidates, 1):
        with st.expander(f"{rank}. {candidate.fault_id} — {graph.nodes[candidate.fault_id].label} | score {candidate.score}", expanded=rank == 1):
            st.write(candidate.description)
            st.caption(f"Basis: {candidate.basis}. Score is a rule score, not confidence.")
            st.write("Supporting observations")
            for item in candidate.supporting:
                st.text(item)
            st.write("Contradicting observations")
            for item in candidate.contradicting or ["None recorded; this does not confirm the fault."]:
                st.text(item)
            st.caption(candidate.uncertainty)
            for rule in graph.rules.values():
                if rule.fault_id == candidate.fault_id:
                    st.write("Required model conditions")
                    for condition in rule.conditions:
                        st.write("• " + condition)
            st.caption("Evidence IDs: " + ", ".join(candidate.path_edge_ids + candidate.source_ids))
            if candidate.reference_case_ids:
                st.caption("Synthetic reference examples (no ranking weight): " + ", ".join(candidate.reference_case_ids))
    if assessment.truncated:
        st.caption(f"Display capped at three. {assessment.eligible_count} causes remain consistent with observations. Tied omissions are not ruled out.")
    st.subheader("Relevant causal paths")
    dot = graphviz.Digraph()
    dot.attr(rankdir="TB", bgcolor="transparent")
    dot.attr("node", shape="box", style="rounded,filled", fillcolor="#F4F4F3", fontname="Arial", fontsize="11")
    for edge_id in dict.fromkeys(e for c in assessment.candidates for e in c.path_edge_ids):
        edge = graph.edges[edge_id]
        for node_id in [edge.source, edge.target]:
            dot.node(node_id, graph.nodes[node_id].label)
        dot.edge(edge.source, edge.target, label=edge.id, color="#D85F16")
    if assessment.candidates:
        st.graphviz_chart(dot)
        st.caption("Every displayed arrow is a conditional synthetic rule. Full conditions appear above.")
with right:
    st.subheader("Record a diagnostic check")
    if assessment.next_check:
        st.success("Suggested: " + graph.checks[assessment.next_check].label)
    check_ids = list(graph.checks)
    check_id = st.selectbox("Check", check_ids, index=check_ids.index(assessment.next_check) if assessment.next_check else 0,
                           format_func=lambda c: graph.checks[c].label, key=f"check_{st.session_state.get('assessment_id', 'initial')}_{len(st.session_state.turns)}")
    check = graph.checks[check_id]
    st.caption(check.instructions)
    outcome = st.selectbox("Observed outcome", list(check.outcomes), format_func=lambda x: f"{x}: {check.outcomes[x]}", key=f"outcome_{check_id}")
    manual = st.button("Record observation")
    simulator_checks = st.session_state.simulator.available_checks()
    simulated = st.button("Simulate check", disabled=check_id not in simulator_checks)
    if check_id not in simulator_checks:
        st.caption("This engineer-authored check is not in the logical simulator. Record a generic observation manually.")
    if manual or simulated:
        if len(st.session_state.observations) >= 40:
            st.error("Session limit reached. Start a new session.")
        else:
            obs = (st.session_state.simulator.check(check_id) if simulated else
                   Observation(check_id=check_id, outcome=outcome, origin="user"))
            st.session_state.observations.append(obs)
            run_turn()
            st.rerun()
    st.subheader("Observation history")
    if st.session_state.observations:
        for number, obs in enumerate(st.session_state.observations, 1):
            st.write(f"{number}. {graph.checks[obs.check_id].label}: **{obs.outcome}**")
            st.caption(f"Recorded from {obs.origin} • {obs.check_id}")
    else:
        st.caption("No observations recorded.")
    if len(st.session_state.turns) > 1:
        prev = st.session_state.turns[-2].assessment
        st.write(f"Candidate count consistent with evidence: {prev.eligible_count} → {assessment.eligible_count}")
        st.caption("Compare each candidate's supporting/contradicting checks above to see why its score changed.")
    st.download_button("Export session JSON", export_session(st.session_state.turns),
                       file_name="diagnostic-session.json", mime="application/json")

with st.expander("Source and evidence panel"):
    st.caption("Runtime evidence is original synthetic material awaiting engineering review. Public candidates are excluded until approved.")
    source_ids = sorted({s for c in assessment.candidates for s in c.source_ids} |
                        ({"SRC_CHECKS"} if st.session_state.observations or assessment.next_check else set()))
    for source_id in source_ids:
        st.json(graph.get_source(source_id))
with st.expander("Execution trace and configuration"):
    st.json(turn.config)
    st.json(turn.trace)
    if turn.model_selection:
        st.json(turn.model_selection.model_dump())

