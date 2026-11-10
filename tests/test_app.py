"""Smoke tests for the Streamlit app: every verdict type renders in both views without an exception.
Runs the real script headless (no browser), with keyword intake so no API key is needed."""
from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
pytest.importorskip("plotly")

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)


def run(view="Simple", **job):
    at = st_testing.AppTest.from_file(APP, default_timeout=300)
    at.session_state["expert"] = view == "Expert"
    if job:
        at.session_state["job"] = {"reps": 1, "shots": 1000, "seed": 7, **job}
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def verdict(at) -> str:
    boxes = [*at.success, *at.warning, *at.error, *at.info]
    return next(b.value for b in boxes if b.value.startswith("**Verdict:"))


@pytest.mark.parametrize("view", ["Simple", "Expert"])
def test_default_request(view):
    at = run(view)
    assert "worth a hardware test" in verdict(at)
    assert len(at.tabs) == 5


@pytest.mark.parametrize("view", ["Simple", "Expert"])
def test_maxcut_pick(view):
    at = run(view, mode="Pick a problem", kind="maxcut_random", size=10, degree=3)
    assert "worth a hardware test" in verdict(at)


def test_view_switch_changes_the_tabs_and_back():
    def expert_only(at):
        return any(m.value == "**Why this verdict**" for m in at.markdown)

    at = run("Simple")
    assert at.toggle(key="expert").value is False and not expert_only(at)
    at.toggle(key="expert").set_value(True).run()
    assert not at.exception and expert_only(at)
    at.toggle(key="expert").set_value(False).run()
    assert not at.exception and not expert_only(at)


def test_noise_dominates():
    at = run("Expert", mode="In plain words", text="Match 6 drivers to 6 delivery routes")
    assert "noise dominates" in verdict(at)


def test_does_not_fit():
    at = run("Expert", mode="Pick a problem", kind="assignment_synthetic", size=13)
    assert "does not fit" in verdict(at)


def test_not_sized():
    at = run("Expert", mode="In plain words", text="Find the ground-state energy of a drug molecule")
    assert "not sized" in verdict(at)


def test_uploaded_cost_table_with_names():
    csv = b"patient,Bed A,Bed B,Bed C\nAna,4,1,3\nBo,2,0,5\nCy,3,2,2\n"
    at = run("Expert", mode="Pick a problem", kind="assignment_upload", upload=csv, upload_name="beds.csv")
    assert "worth a hardware test" in verdict(at)
    assert at.metric[0].value == "9"


def test_uploaded_edge_list_with_header():
    csv = b"source,target,weight\nrouter1,router2,1\nrouter2,router3,2\nrouter3,router1,1\nrouter3,router4,1\n"
    at = run(mode="Pick a problem", kind="maxcut_upload", upload=csv, upload_name="net.csv")
    assert "worth a hardware test" in verdict(at)
    assert at.metric[0].value == "4"


def test_bad_upload_explains_itself():
    at = run(mode="Pick a problem", kind="assignment_upload", upload=b"1,2,3\n4,5,6\n", upload_name="bad.csv")
    assert any("square" in e.value for e in at.error)


def test_missing_upload_explains_itself():
    at = run(mode="Pick a problem", kind="assignment_upload")
    assert any("Upload a CSV" in e.value for e in at.error)
