"""Quantum Fit Check: the interactive interface.

    streamlit run app.py

Never spends QPU time: it builds and compiles circuits but never submits a job. Device data comes from
the local copy of ibm_fez, or, when QISKIT_IBM_TOKEN is set, from ibm_fez's live calibration (read only).
Hardware results are read from results/, where the notebook saves them. A GEMINI_API_KEY turns on
plain-language reading with a language model; without it, keyword matching is used. Keys come from
environment variables or Streamlit secrets. Keep the IBM key on your own laptop, never on a public deploy.
"""
from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
import pandas as pd
import streamlit as st

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import fitcheck as fc  # noqa: E402
from fitcheck import visuals as vz  # noqa: E402
from fitcheck.core import OPTIMISATION_RUNS, SIZABLE, SUCCESS_THRESHOLD, pct  # noqa: E402
from fitcheck.device import PRICE_PER_MINUTE_USD  # noqa: E402
from fitcheck.estimate import usable_qubits  # noqa: E402

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
DRAW_LOGICAL_UP_TO = 16        # qubits: larger circuits are unreadable as drawings
DRAW_COMPILED_UP_TO = 80       # two-qubit gates
SPREAD_UP_TO = 40              # qubits: transpiler-seed spread is only fast for small circuits
EXAMPLES = [
    "We need to assign 4 patients to 4 hospital beds at the lowest total cost",
    "Assign 12 patients to 12 beds",
    "Find the ground-state energy of a drug molecule",
    "Split a network of 10 routers into two groups",
    "Cluster a network of 60 sensors into two communities",
    "Pick the best portfolio from 20 stocks",
    "Train an image classifier on 1 million photos",
]
PROBLEMS = {
    "maxcut_random": "Max-Cut: a random network",
    "maxcut_upload": "Max-Cut: upload an edge list (CSV)",
    "assignment_synthetic": "Hospital bed assignment: synthetic data",
    "assignment_upload": "Hospital bed assignment: upload a cost table (CSV)",
}
LIVE, LOCAL = "Live calibration", "Local copy"
SECRETS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_MODEL", "QISKIT_IBM_TOKEN", "QISKIT_IBM_INSTANCE")
VERDICT_BOX = {"worth a hardware test": st.success, "runs, but noise dominates": st.warning,
               "does not fit": st.error, "not sized": st.info}

st.set_page_config(page_title="Quantum Fit Check", page_icon=":material/memory:", layout="wide")

# Streamlit secrets (Community Cloud, or .streamlit/secrets.toml locally) become environment variables,
# which is where the fitcheck library looks for keys.
try:
    for _name in SECRETS:
        if not os.environ.get(_name) and _name in st.secrets:
            os.environ[_name] = str(st.secrets[_name])
except Exception:  # no secrets file: environment variables only
    pass
HAS_IBM_KEY = bool(os.environ.get("QISKIT_IBM_TOKEN"))


# ---------------------------------------------------------------- cached work

@st.cache_resource(show_spinner=False)
def local_device():
    return fc.local_backend("fez")


@st.cache_resource(show_spinner=False, ttl=3600)
def live_device():
    """ibm_fez as IBM publishes it now. Reads calibration data only; the app never submits a job."""
    backend = fc.connect_service().backend("ibm_fez")
    try:
        when = backend.properties().last_update_date.astimezone(timezone.utc)
    except Exception:
        when = datetime.now(timezone.utc)
    return backend, when.strftime("%Y-%m-%d %H:%M")


def pick_device(source: str):
    """(backend, short label, sidebar note, cache id)."""
    if source == LIVE:
        try:
            backend, when = live_device()
            return (backend, "ibm_fez (live)",
                    f"Device: IBM's 156-qubit **ibm_fez**, live calibration from {when} UTC, read with your IBM key. "
                    "The app only reads calibration data and never submits a job, so it spends no QPU time.",
                    f"live {when}")
        except Exception as exc:
            st.warning(f"Could not reach IBM ({type(exc).__name__}), so the local copy is used.")
    note = ("Device: local copy of IBM's 156-qubit **ibm_fez**, with the calibration saved in Qiskit. No QPU time."
            + ("" if HAS_IBM_KEY else " Set QISKIT_IBM_TOKEN to use today's live calibration instead."))
    return local_device(), "ibm_fez (local copy)", note, "local"


@st.cache_data(show_spinner=False)
def understand(text: str) -> dict:
    return fc.parse_request(text)


def read_edges(data: bytes) -> list[tuple]:
    df = pd.read_csv(io.BytesIO(data), header=None, comment="#", skipinitialspace=True)
    if df.shape[1] < 2:
        raise ValueError("Each row needs two node names, and optionally a weight.")
    first = [str(v).strip().lower() for v in df.iloc[0, :2]]
    if first[0] in ("u", "source", "from", "node1", "a") or (df.shape[1] > 2 and pd.isna(pd.to_numeric(df.iloc[0, 2], errors="coerce"))):
        df = df.iloc[1:]
    edges = []
    for row in df.itertuples(index=False):
        if df.shape[1] > 2 and not pd.isna(row[2]):
            edges.append((str(row[0]).strip(), str(row[1]).strip(), float(row[2])))
        else:
            edges.append((str(row[0]).strip(), str(row[1]).strip()))
    if not edges:
        raise ValueError("The file has no links.")
    return edges


def read_costs(data: bytes):
    df = pd.read_csv(io.BytesIO(data), header=None, skipinitialspace=True)
    if df.shape[0] and pd.to_numeric(df.iloc[0], errors="coerce").isna().sum() > 1:
        df = df.iloc[1:]                                   # header row
    if df.shape[1] and pd.to_numeric(df.iloc[:, 0], errors="coerce").isna().all():
        df = df.iloc[:, 1:]                                # row labels
    costs = df.apply(pd.to_numeric, errors="coerce")
    if costs.isna().any().any():
        raise ValueError("Every cell must be a number.")
    if costs.shape[0] != costs.shape[1]:
        raise ValueError(f"The table must be square (patients x beds); this one is {costs.shape[0]} x {costs.shape[1]}.")
    if costs.shape[0] > 16:
        raise ValueError("Up to 16 patients: beyond that the problem needs far more qubits than any device has.")
    return costs.to_numpy(dtype=float)


def make_problem(kind: str, size: int, degree: int, seed: int, upload: bytes | None):
    if kind == "maxcut_random":
        return fc.maxcut_problem(fc.random_graph(size, degree, seed))
    if kind == "maxcut_upload":
        return fc.maxcut_from_edges(read_edges(upload))
    if kind == "assignment_synthetic":
        return fc.assignment_problem(fc.synthetic_costs(size, seed))
    if kind == "assignment_upload":
        return fc.assignment_problem(read_costs(upload))
    raise ValueError(kind)


# `device_id` names the device and its calibration for the cache; `_backend` (not hashed) is the device itself.
@st.cache_resource(show_spinner=False, max_entries=24)
def run_check(kind: str, size: int, degree: int, seed: int, upload: bytes | None, reps: int, shots: int,
              device_id: str, _backend):
    problem = make_problem(kind, size, degree, seed, upload)
    return problem, fc.fit_check(problem, _backend, reps, shots, seed)


@st.cache_data(show_spinner=False, max_entries=24)
def seed_spread(kind: str, size: int, degree: int, seed: int, upload: bytes | None, reps: int,
                device_id: str, _backend) -> list[dict]:
    problem = make_problem(kind, size, degree, seed, upload)
    circuit = fc.bind_random(fc.qaoa_circuit(problem, reps, measure=True), seed)
    rows = []
    for s in range(5):
        isa = fc.transpile_for(_backend, circuit, seed=s, tries=1)
        rows.append({"seed": s, "success": fc.success_estimate(_backend, isa)["success"],
                     "two_qubit_gates": fc.circuit_metrics(_backend, isa)["two_qubit_gates"]})
    return rows


@st.cache_data(show_spinner=False)
def saved_results(stamp: tuple):
    sim_path, hw_path = RESULTS / "simulator_validation.json", RESULTS / "hardware_run.json"
    sim = fc.load_json(sim_path) if sim_path.exists() else None
    hw = fc.load_json(hw_path) if hw_path.exists() else None
    return sim, (hw if hw and "runs" in hw else None)


def results_stamp() -> tuple:
    return tuple(p.stat().st_mtime if p.exists() else 0
                 for p in (RESULTS / "simulator_validation.json", RESULTS / "hardware_run.json"))


def show_fig(fig):
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})


def show_mpl(fig):
    st.pyplot(fig, width="stretch")
    plt.close(fig)


# ---------------------------------------------------------------- sidebar

with st.sidebar:
    st.title("Quantum Fit Check")
    mode = st.radio("Describe the problem", ["In plain words", "Pick a problem"], horizontal=True, key="mode")

    params: dict = {}
    if mode == "In plain words":
        st.session_state.setdefault("request_text", EXAMPLES[0])

        def use_example():
            if st.session_state.get("example"):
                st.session_state["request_text"] = st.session_state["example"]

        st.selectbox("Start from an example", EXAMPLES, index=None, key="example", on_change=use_example,
                     placeholder="Choose an example")
        params["text"] = st.text_area("Your task, in one sentence", key="request_text", height=100).strip()
        has_llm = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
        st.caption("Read by the Gemini language model. It only picks the problem type and size; Qiskit does the rest."
                   if has_llm else "Read by keyword matching. Set GEMINI_API_KEY to have a language model read it.")
    else:
        kind = st.selectbox("Problem", list(PROBLEMS), format_func=PROBLEMS.get, key="kind")
        params["kind"] = kind
        if kind == "maxcut_random":
            params["size"] = st.slider("Nodes (one qubit each)", 2, 160, 10, key="mc_size")
            params["degree"] = st.slider("Links per node", 2, 6, 3, key="mc_degree")
        elif kind == "assignment_synthetic":
            params["size"] = st.slider("Patients and beds (qubits = patients squared)", 2, 16, 4, key="as_size")
        else:
            maxcut = kind == "maxcut_upload"
            st.caption("One link per row: `node_a,node_b` or `node_a,node_b,weight`." if maxcut else
                       "A square table of numbers: one row per patient, one column per bed, the cost of each pairing. "
                       "A header row and a first column of names are allowed.")
            up = st.file_uploader("CSV file", type=["csv", "txt"], key="upload_" + kind)
            params["upload"] = up.getvalue() if up else None
            params["upload_name"] = up.name if up else None

    params["reps"] = st.slider("QAOA layers", 1, 3, 1, key="reps",
                               help="More layers can give better answers but make the circuit longer and noisier.")
    params["shots"] = int(st.number_input("Shots per job", 100, 100_000, 1000, step=100, key="shots",
                                          help="How many times the circuit runs. Drives the QPU time and price."))
    with st.expander("Advanced"):
        params["seed"] = int(st.number_input("Seed for generated data and compiling", 0, 10_000, 7, key="seed"))
    params["mode"] = mode

    if st.button("Run fit check", type="primary", width="stretch"):
        st.session_state["job"] = dict(params)
    st.session_state.setdefault("job", {"mode": "In plain words", "text": EXAMPLES[0], "reps": 1, "shots": 1000, "seed": 7})
    if {k: v for k, v in params.items() if k != "upload_name"} != {k: v for k, v in st.session_state["job"].items() if k != "upload_name"}:
        st.caption(":orange[Settings changed. Press **Run fit check** to update.]")

    st.divider()
    source = (st.radio("Device data", [LIVE, LOCAL], horizontal=True, key="device_source",
                       help="Live: ibm_fez's calibration as IBM publishes it now, read with your IBM key. "
                            "Local: the copy saved in Qiskit. Neither spends QPU time.")
              if HAS_IBM_KEY else LOCAL)
    with st.spinner("Reading ibm_fez's calibration from IBM..."):
        backend, DEVICE_LABEL, device_note, device_id = pick_device(source)
    st.caption(device_note + " Prices: IBM's published rates (ibm.com/quantum/pricing), checked 2026-11-10.")


# ---------------------------------------------------------------- run

job = st.session_state["job"]
reps, shots, seed = job["reps"], job["shots"], job["seed"]
spec = problem = report = None
key = None
upload = None
error = None

with st.spinner("Building the circuit and compiling it for the device..."):
    try:
        if job["mode"] == "In plain words":
            if not job.get("text"):
                raise ValueError("Type a task first.")
            spec = understand(job["text"])
            if spec["problem_type"] in SIZABLE:
                size = spec.get("size") or 0
                key = (("assignment_synthetic", max(2, size or 3), 3) if spec["problem_type"] == "assignment"
                       else ("maxcut_random", max(2, size or 10), 3))
                if key[0] == "assignment_synthetic" and key[1] > 16:
                    key = ("assignment_synthetic", 16, 3)
                    st.toast("Capped at 16 patients (256 qubits), already far beyond the device.")
                if key[0] == "maxcut_random" and key[1] > 400:
                    key = ("maxcut_random", 400, 3)
            else:
                report = fc.shape_only_report(spec["problem_type"], spec["understood"])
        else:
            upload = job.get("upload")
            if job["kind"].endswith("upload") and not upload:
                raise ValueError("Upload a CSV file in the sidebar, then press Run fit check.")
            key = (job["kind"], job.get("size", 0), job.get("degree", 3))
        if key is not None:
            problem, report = run_check(key[0], key[1], key[2], seed, upload, reps, shots, device_id, backend)
    except ValueError as exc:
        error = str(exc)
    except Exception as exc:  # a broken upload should explain itself, not crash the page
        error = f"Could not read that problem: {exc}"


# ---------------------------------------------------------------- header

head, switch = st.columns([3, 1], vertical_alignment="center")
head.title("Quantum Fit Check")
# A toggle, not a two-option picker: it always has a state, and it sits by the title so it stays
# visible when the sidebar is folded away on a narrow screen.
expert = switch.toggle("Expert view", key="expert")
st.markdown("**Is this problem worth running on today's quantum computers, and what would it cost?** "
            "Answered before any quantum time is spent.")

if error:
    st.error(error)
    st.stop()

if spec:
    by_llm = spec["source"].startswith("gemini")
    size_txt = f", size **{spec['size']:,}**" if spec.get("size") else ""
    st.info((f"**How I understood it:** {spec['understood']}  \n" if by_llm else "**How I understood it:** ")
            + f"problem type **{spec['problem_type'].replace('_', ' ')}**{size_txt}, read by "
            + ("the Gemini language model" if by_llm else "keyword matching")
            + ". If this is wrong, rephrase the sentence or use **Pick a problem**.")
    if problem is not None and spec["problem_type"] == "qubo":
        st.caption("General yes/no optimisation is sized with a Max-Cut stand-in of the same number of variables.")

VERDICT_BOX.get(report.verdict, st.info)(f"**Verdict: {report.verdict}.** {report.summary}")

sized = bool(report.metrics)
c1, c2, c3 = st.columns(3)
if report.verdict == "not sized":
    c1.metric("Problem shape", report.shape)
    c2.metric("Qubits needed", "not sized")
    c3.metric("QPU time", "none")
else:
    c1.metric("Qubits needed", f"{report.logical_qubits}", f"of {report.device_qubits} on {DEVICE_LABEL}",
              delta_color="off", delta_arrow="off")
    c2.metric("Chance a shot has no error", pct(report.success) if sized else "none",
              f"threshold {SUCCESS_THRESHOLD:.0%}" if sized else None, delta_color="off", delta_arrow="off")
    c3.metric("One job: QPU time and price", f"{report.qpu_seconds:.2f} s" if sized else "none",
              f"${report.price['Pay-As-You-Go']:.2f} Pay-As-You-Go" if sized else None, delta_color="off", delta_arrow="off")

st.download_button("Download this report (Markdown)", report.to_markdown(),
                   file_name=f"fit-check-{report.problem_name.lower().replace(' ', '-')}.md", mime="text/markdown")

if expert:
    st.caption(":blue[**Expert view.**] Each tab adds the numbers behind it: the cost-function heatmap, gate counts and "
               "circuit drawings, error rates on every qubit and link, prices on every plan, error sources, and every "
               "hardware run with its job ID.")
else:
    st.caption("**Simple view.** Switch on **Expert view** (top right) for the diagrams and numbers behind each tab.")

tab_problem, tab_circuit, tab_qubits, tab_estimates, tab_validation = st.tabs(
    ["Problem", "Circuit", "Qubits", "Estimates", "Validation"])
isa = report.compiled


# ---------------------------------------------------------------- Problem

with tab_problem:
    st.markdown(f"**Problem shape: {report.shape}.** {report.shape_reason}")
    if problem is None:
        st.markdown("This tool builds circuits for graph partitioning (Max-Cut), assignment and yes/no "
                    "optimisation problems. For this kind of task it gives the shape label and its reasoning only.")
    else:
        st.markdown(problem.description)
        if problem.kind == "maxcut":
            show_fig(vz.problem_graph(problem, report.classical))
            st.caption("Blue and orange are the two groups in the best split found by the classical solver; "
                       "dotted orange links are the ones cut." if report.classical.get("bits") else
                       "Too many nodes for an exact classical split, so the groups are not coloured.")
        elif problem.kind == "assignment":
            show_fig(vz.assignment_table(problem, report.classical))
            synthetic = job.get("mode") == "In plain words" or job.get("kind") == "assignment_synthetic"
            st.caption(("Synthetic costs, generated with a fixed seed: not real hospital data. " if synthetic else "")
                       + "Orange squares: the best assignment, found exactly by the classical Hungarian algorithm.")
        if expert:
            links = sum(1 for w in problem.quadratic.values() if w)
            singles = sum(1 for w in problem.linear if w)
            e1, e2, e3 = st.columns(3)
            e1.metric("Qubits (variables)", problem.num_qubits)
            e2.metric("Two-qubit terms (ZZ)", links)
            e3.metric("Single-qubit terms (Z)", singles)
            st.caption("Cost function: offset + sum h_i z_i + sum J_ij z_i z_j, minimised over z in {+1, -1}.")
            if problem.num_qubits <= 200:
                show_fig(vz.coupling_matrix(problem))
            if problem.kind == "assignment":
                st.caption("Each patient-bed pair is one qubit. The rule 'one bed per patient, one patient per bed' "
                           "is written as a penalty, which is where most of the couplings come from.")


# ---------------------------------------------------------------- Circuit

with tab_circuit:
    if problem is None:
        st.info("No circuit: this kind of task is not turned into a circuit by the tool.")
    else:
        st.markdown(f"A QAOA circuit with {reps} layer{'s' if reps > 1 else ''}, built gate by gate from the cost function.")
        cols = st.columns(4)
        for col, block in zip(cols, vz.circuit_blocks(problem, reps)):
            with col.container(border=True):
                st.markdown(f"**{block['name']}**")
                st.markdown(f"### {block['gates']:,} gates")
                st.caption(block["text"])
        if isa is None:
            st.warning(f"Not compiled: the problem needs {problem.num_qubits} qubits and only "
                       f"{usable_qubits(backend)} of the device's {backend.num_qubits} are connected by working links.")
        else:
            m = report.metrics
            logical_gates = sum(b["gates"] for b in vz.circuit_blocks(problem, reps))
            compiled_gates = sum(v for k, v in m["gate_counts"].items() if k != "barrier")
            st.markdown(f"**After compiling for {DEVICE_LABEL}:** {compiled_gates:,} gates "
                        f"({compiled_gates / max(logical_gates, 1):.1f}x the {logical_gates:,} above), of which "
                        f"**{m['two_qubit_gates']:,} are two-qubit gates**, the main source of errors. Depth "
                        f"{m['depth']:,}, lasting {m['duration_seconds'] * 1e6:.1f} microseconds per shot.")
            st.caption("The device only links neighbouring qubits and has its own small set of gates, so compiling "
                       "adds gates that move information around and rewrites every gate in the device's own set.")
        if expert:
            logical = fc.qaoa_circuit(problem, reps, measure=True)
            before = {k: int(v) for k, v in logical.count_ops().items() if k != "barrier"}
            after = {k: int(v) for k, v in (report.metrics.get("gate_counts") or {}).items() if k != "barrier"}
            table = pd.DataFrame({"Before compiling": pd.Series(before), "After compiling": pd.Series(after)}).fillna(0).astype(int)
            st.markdown("**Gate counts**")
            st.dataframe(table.sort_values("After compiling", ascending=False), width="content")
            if problem.num_qubits <= DRAW_LOGICAL_UP_TO:
                st.markdown("**The circuit as built** (angles gamma and beta are set by the optimiser)")
                show_mpl(logical.draw("mpl", fold=30, scale=0.55))
            else:
                st.caption(f"Circuit drawings are shown up to {DRAW_LOGICAL_UP_TO} qubits.")
            if isa is not None:
                if report.metrics["two_qubit_gates"] <= DRAW_COMPILED_UP_TO:
                    st.markdown("**The compiled circuit** (device qubits, idle ones hidden)")
                    show_mpl(isa.draw("mpl", fold=40, scale=0.45, idle_wires=False))
                else:
                    st.caption(f"The compiled drawing is shown up to {DRAW_COMPILED_UP_TO} two-qubit gates.")
                show_fig(vz.gate_durations(backend, isa))


# ---------------------------------------------------------------- Qubits

with tab_qubits:
    if isa is None:
        if problem is not None:
            st.warning(f"The problem needs {problem.num_qubits} qubits, more than the "
                       f"{usable_qubits(backend)} connected ones, so nothing is placed on the chip.")
        show_fig(vz.chip_map(backend, expert=expert))
    else:
        used, layout = vz.used_qubits(isa)
        routing = len(used - set(layout.values()))
        st.markdown(f"**{len(used)} of {backend.num_qubits} qubits in use**: {len(layout)} hold the problem"
                    + (f", {routing} more only pass information along." if routing else "."))
        show_fig(vz.chip_map(backend, used, layout, expert=expert))
        quality = vz.qubit_quality(backend)
        median = pd.Series([q["readout"] for q in quality.values()]).median()
        st.caption(f"Colour of a used qubit: its readout error against the device's typical {median:.2%}. "
                   "Hover a qubit to see its numbers." + (" Links are coloured by two-qubit error; hover the middle of a "
                                                         "link to see it. Numbers on qubits are problem qubits." if expert else ""))
        if expert:
            rows = [{"Device qubit": q, "Problem qubit": next((v for v, p in layout.items() if p == q), None),
                     "Readout error": quality[q]["readout"],
                     "T1 (us)": (quality[q]["t1"] or 0) * 1e6, "T2 (us)": (quality[q]["t2"] or 0) * 1e6}
                    for q in sorted(used)]
            st.dataframe(pd.DataFrame(rows).sort_values("Readout error", ascending=False),
                         hide_index=True, width="stretch",
                         column_config={"Readout error": st.column_config.NumberColumn(format="percent"),
                                        "T1 (us)": st.column_config.NumberColumn(format="%.0f"),
                                        "T2 (us)": st.column_config.NumberColumn(format="%.0f"),
                                        "Problem qubit": st.column_config.NumberColumn(format="%d")})


# ---------------------------------------------------------------- Estimates

with tab_estimates:
    if not sized:
        st.markdown("\n".join(f"- {r}" for r in report.reasons))
        if report.classical.get("seconds") is not None:
            st.markdown(f"Classical computer on the same problem: **{vz.fmt_seconds(report.classical['seconds'])}** "
                        f"({report.classical['method']}).")
    else:
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Chance a shot has no error", pct(report.success))
        e2.metric("QPU time, one job", f"{report.qpu_seconds:.2f} s", f"{shots:,} shots", delta_color="off", delta_arrow="off")
        e3.metric("Price, one job", f"${report.price['Pay-As-You-Go']:.2f}", "Pay-As-You-Go", delta_color="off", delta_arrow="off")
        e4.metric("Classical computer", vz.fmt_seconds(report.classical.get("seconds")),
                  "exact" if report.classical.get("exact") else "heuristic" if report.classical.get("seconds") else None,
                  delta_color="off", delta_arrow="off")
        if report.error_reduction_needed:
            st.warning(f"**What would need to improve:** the device's gate and readout errors would need to be about "
                       f"**{report.error_reduction_needed:,.1f} times lower** for this same circuit to reach "
                       f"{SUCCESS_THRESHOLD:.0%}.")
        g1, g2 = st.columns(2)
        with g1:
            show_fig(vz.qpu_meter(report.qpu_seconds, "One job, of the 600 free seconds"))
        with g2:
            show_fig(vz.qpu_meter(report.full_run_seconds,
                                  f"Full QAOA search ({OPTIMISATION_RUNS} jobs), of the 600 free seconds"))
        st.caption("QPU time uses IBM's own usage formula: a fixed overhead of about 2 seconds per job plus the "
                   "circuit time per shot. A full search for good QAOA angles is counted as 100 such jobs.")
        if expert:
            st.markdown("**Why this verdict**")
            st.markdown("\n".join(f"- {r}" for r in report.reasons))
            plans = [{"Plan": plan, "Per minute": rate, "One job": report.price[plan],
                      f"Full search ({OPTIMISATION_RUNS} jobs)": report.full_run_price[plan]}
                     for plan, rate in PRICE_PER_MINUTE_USD.items()]
            plans.append({"Plan": "Open (free, 10 min)", "Per minute": 0.0, "One job": report.price["Open (free)"],
                          f"Full search ({OPTIMISATION_RUNS} jobs)": report.full_run_price["Open (free)"]})
            money = st.column_config.NumberColumn(format="$%.2f")
            st.dataframe(pd.DataFrame(plans), hide_index=True, width="stretch",
                         column_config={"Per minute": money, "One job": money,
                                        f"Full search ({OPTIMISATION_RUNS} jobs)": money})
            st.caption("An empty price on the free plan means it does not fit in the 10 free minutes.")
            x1, x2 = st.columns(2)
            with x1:
                show_fig(vz.error_by_gate(report.success_by_gate))
            with x2:
                if problem.num_qubits <= SPREAD_UP_TO:
                    with st.spinner("Compiling with five transpiler seeds..."):
                        show_fig(vz.seed_spread(seed_spread(key[0], key[1], key[2], seed, upload, reps,
                                                            device_id, backend)))
                else:
                    st.caption(f"The transpiler-seed spread is computed up to {SPREAD_UP_TO} qubits.")
            d = report.device
            st.caption(f"Device medians used: two-qubit ({d['two_qubit_gate']}) error {d['median_two_qubit_error']:.3%}, "
                       f"single-qubit (sx) error {d['median_sx_error']:.3%}, readout error {d['median_readout_error']:.3%}. "
                       "The estimate counts gate and readout errors only, so it is optimistic: real hardware also "
                       "loses accuracy while qubits wait, to crosstalk and to drift.")


# ---------------------------------------------------------------- Validation

with tab_validation:
    sim, hw = saved_results(results_stamp())
    st.markdown("We test our own estimates with **mirror circuits**: a circuit followed by its inverse. A perfect "
                "device returns all zeros, so the share of all-zero shots is the measured success.")
    if not sim:
        st.info("No simulator validation saved yet. Run section 5 of the notebook.")
    else:
        show_fig(vz.validation_chart(sim["rows"], hw))
        if hw:
            rows = hw["runs"]["off"]["rows"]
            gaps = [r["predicted_success"] - r["measured_success"] for r in rows]
            st.markdown(f"**Real hardware ({hw['backend']}, {hw['prepared_at'][:10]}):** measured success was "
                        f"{min(gaps):.0%} to {max(gaps):.0%} below our prediction, and the gap grows with size. "
                        "The formula leaves out idle decoherence, crosstalk and drift, so it is too optimistic, as "
                        "LIMITATIONS.md says. Error mitigation (dynamical decoupling and twirling) lowered the "
                        "score on these short circuits.")
        else:
            st.caption("No hardware run saved yet: the chart shows the noisy simulator only.")
        if expert:
            st.markdown("**Noisy simulator** (three random graphs per size)")
            st.dataframe(pd.DataFrame(sim["rows"]), hide_index=True, width="stretch")
            if hw:
                on = {r["num_nodes"]: r for r in hw["runs"].get("on", {}).get("rows", [])}
                table = [{"Qubits": r["num_nodes"], "Two-qubit gates": r["two_qubit_gates"],
                          "Predicted that day": r["predicted_success"],
                          "Measured, mitigation off": r["measured_success"], "+/- off": r["measured_stderr"],
                          "Measured, mitigation on": on.get(r["num_nodes"], {}).get("measured_success"),
                          "+/- on": on.get(r["num_nodes"], {}).get("measured_stderr")}
                         for r in hw["runs"]["off"]["rows"]]
                share = st.column_config.NumberColumn(format="percent")
                st.markdown("**Real hardware**")
                st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch",
                             column_config={c: share for c in table[0] if c not in ("Qubits", "Two-qubit gates")})
                runs = [{"Mitigation": k, "Job ID": v["job_id"], "QPU seconds used": v["qpu_seconds_used"],
                         "Predicted QPU seconds": hw["predicted_qpu_seconds_per_job"], "Collected": v["collected_at"][:19]}
                        for k, v in hw["runs"].items()]
                st.dataframe(pd.DataFrame(runs), hide_index=True, width="stretch")
                snap = hw.get("device_snapshot", {})
                st.caption(f"Predictions made {hw['prepared_at'][:19]} UTC, before submitting, from that day's "
                           f"calibration: two-qubit error {snap.get('median_two_qubit_error', 0):.3%}, readout error "
                           f"{snap.get('median_readout_error', 0):.3%}. {hw['shots']:,} shots per circuit.")
