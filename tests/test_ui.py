from streamlit.testing.v1 import AppTest
from ecfkg.graph import ROOT


def click(at, label):
    next(b for b in at.button if b.label == label).click().run()


def test_interactive_demo_and_reset():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    assert not at.exception
    click(at, "Assess symptom")
    assert not at.exception
    assert at.session_state.turns[-1].assessment.next_check == "CHECK_SUPPLY"
    click(at, "Simulate check")
    assert not at.exception
    assert at.session_state.turns[-1].assessment.candidates[0].fault_id == "F_SUPPLY"
    assert at.session_state.observations[0].origin == "simulator"
    click(at, "Reset / new session")
    assert not at.session_state.turns


def test_loading_different_fault_does_not_leak_to_agent():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    next(s for s in at.selectbox if s.label == "Hidden station state").select("ROUTE")
    click(at, "Load simulated station")
    click(at, "Assess symptom")
    assert at.session_state.turns[-1].assessment.eligible_count == 5
    click(at, "Simulate check")
    assert at.session_state.turns[-1].assessment.next_check == "CHECK_ROUTE"
    click(at, "Simulate check")
    assert at.session_state.turns[-1].assessment.candidates[0].fault_id == "F_ROUTE"
    assert not at.exception


def test_project_identity_and_api_controls(monkeypatch):
    monkeypatch.delenv("ECFKG_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    assert any("ASU Capstone IEE-018" in m.value for m in at.markdown)
    assert "Local LLM-assisted" not in at.radio[0].options
    at.radio[0].set_value("API-assisted").run()
    assert any(t.label == "API base URL" for t in at.text_input)
    key_widget = next(t for t in at.text_input if t.label == "API key")
    assert key_widget.proto.type == key_widget.proto.PASSWORD
    next(t for t in at.text_input if t.label == "API model").set_value("test-model").run()
    click(at, "Assess symptom")
    assert not at.exception
    assert at.session_state.turns[-1].assessment.status == "model_error"
    assert at.session_state.turns[-1].mode == "api"
    assert any("Enter an API key" in error.value for error in at.error)
    assert any("API route: Responses" in c.value for c in at.caption)

