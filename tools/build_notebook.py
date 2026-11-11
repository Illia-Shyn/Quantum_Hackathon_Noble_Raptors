"""Regenerates notebooks/quantum_fit_check.ipynb. Run: python tools/build_notebook.py"""
from pathlib import Path

import nbformat as nbf

REPO = "https://github.com/Illia-Shyn/Quantum_Hackathon_Noble_Raptors.git"
cells = []
md = lambda s: cells.append(nbf.v4.new_markdown_cell(s.strip()))
code = lambda s: cells.append(nbf.v4.new_code_cell(s.strip()))

md("""
# Quantum Fit Check

**Is this problem worth running on today's quantum computers, and what would it cost?**

**Who it is for:** an operations or analytics lead (a hospital bed manager, a logistics planner) who
has been told quantum might help and has to decide whether to spend time and budget finding out.

Give the tool a problem. It builds the quantum circuit in Qiskit, compiles it for a real IBM device,
and reports the qubits needed, the chance a shot finishes without an error, the QPU seconds, the price
on each IBM plan, and how long a classical computer takes on the same problem. Then it tests its own
estimates against a noisy simulator and real hardware.

The tool never claims quantum wins. A "worth a hardware test" verdict only means the circuit can run
cleanly enough to measure.

Everything up to section 7 runs without an IBM key and uses no QPU time.
""")

md("## 0. Setup")
code(f'''
import os, subprocess, sys

REPO = "{REPO}"
if not os.path.isdir("fitcheck"):
    if os.path.isdir("../fitcheck"):          # opened from the repository's notebooks/ folder
        os.chdir("..")
    else:                                     # fresh Colab session
        subprocess.run(["git", "clone", "-q", REPO, "quantum_fit_check"], check=True)
        os.chdir("quantum_fit_check")
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], check=True)
sys.path.insert(0, os.getcwd())

import warnings
warnings.filterwarnings("ignore")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import qiskit
from IPython.display import Markdown, display

import fitcheck as fc

backend = fc.local_backend("fez")             # local copy of ibm_fez: no key, no QPU time
print("Qiskit", qiskit.__version__)
print(fc.device_summary(backend))
''')

md("""
## 1. Ask in plain language

Type a task as a sentence. If a Gemini key is set (`GEMINI_API_KEY` in Colab Secrets or the
environment), a language model turns the sentence into a problem type and a size. Without a key the
tool falls back to keyword matching, so this cell always runs.

The language model never produces a number in the report. It only picks the template; Qiskit does the rest.
""")
code('''
request = "We need to assign 4 patients to 4 hospital beds at the lowest total cost"

spec, report = fc.check_request(request, backend)
print("How the request was understood:", spec)
display(Markdown(report.to_markdown()))
''')
code('''
# Tasks the tool cannot turn into a circuit still get a shape label and the reasoning behind it.
for text in ["Find the ground-state energy of a drug molecule",
             "Train an image classifier on 1 million photos",
             "Split a delivery network of 12 depots into two balanced regions"]:
    spec, rep = fc.check_request(text, backend)
    print(f"{text}\\n  -> type: {spec['problem_type']} | shape: {rep.shape} | verdict: {rep.verdict}\\n")
''')

md("""
## 2. The pipeline, step by step

The same five stages on one small example: Max-Cut on a 10-node network.

**Stage 1, the problem.** Split the nodes into two groups so that as many links as possible are cut.
""")
code('''
graph = fc.random_graph(10, degree=3, seed=7)
problem = fc.maxcut_problem(graph)
classical = fc.solve_classically(problem)
colors = ["#2a78d6" if b else "#eb6834" for b in classical["bits"]]
plt.figure(figsize=(4.5, 3.5))
nx.draw(problem.meta["graph"], pos=nx.spring_layout(problem.meta["graph"], seed=3), node_color=colors,
        with_labels=True, font_color="white")
plt.title(f"Best split (classical, exact): {classical['cut']:.0f} of {graph.number_of_edges()} links cut")
plt.show()
print("Cost Hamiltonian:", problem.hamiltonian().size, "ZZ terms on", problem.num_qubits, "qubits")
''')
md("**Stage 2, the circuit.** A QAOA circuit built gate by gate from the problem's terms: one qubit per node, one `RZZ` gate per link.")
code('''
circuit = fc.qaoa_circuit(problem, reps=1, measure=True)
print("Parameters:", [p.name for p in circuit.parameters])
circuit.draw("mpl", fold=40, scale=0.6)
''')
md("**Stage 3, transpile.** Compile for the device's own gates and wiring. Extra gates appear because the device only links neighbouring qubits.")
code('''
isa = fc.transpile_for(backend, fc.bind_random(circuit))
metrics = fc.circuit_metrics(backend, isa)
print("Before:", dict(circuit.count_ops()))
print("After: ", metrics["gate_counts"])
print(f"Depth {metrics['depth']}, two-qubit gates {metrics['two_qubit_gates']}, "
      f"duration {metrics['duration_seconds'] * 1e6:.1f} microseconds")
''')
md("**Stages 4 and 5, estimate and verdict.**")
code('''
report = fc.fit_check(problem, backend, reps=1, shots=1000)
display(Markdown(report.to_markdown()))
print("Where the errors come from (chance each gate type causes no error):")
for gate, value in report.success_by_gate.items():
    print(f"  {gate:8s} {value:.3f}")
''')

md("""
## 3. How far does it scale? Two problems

**Problem A, hospital bed assignment (synthetic data).** One qubit per patient-bed pair, so the qubits
grow as the square of the number of patients. The classical Hungarian algorithm solves it exactly.
""")
code('''
rows = []
for n in [2, 3, 4, 5, 6, 8, 10, 12, 13]:
    r = fc.fit_check(fc.assignment_problem(fc.synthetic_costs(n)), backend)
    rows.append((n, r))
    print(f"{n:>2} patients | {r.logical_qubits:>3} qubits | 2q gates {r.metrics.get('two_qubit_gates', '-'):>6} | "
          f"success {fc.core.pct(r.success) if r.success is not None else '-':>11} | "
          f"classical {r.classical['seconds'] * 1000:.3f} ms | {r.verdict}"
          + (f" (errors must be {r.error_reduction_needed:,.1f}x lower)" if r.error_reduction_needed else ""))
print()
for row in fc.assignment_scaling((10, 100, 1000)):
    print(f"Classical: {row['patients']:>4} patients solved exactly in {row['classical_seconds'] * 1000:8.2f} ms "
          f"(QAOA would need {row['qubits_needed']:,} qubits)")
''')
md("**Problem B, Max-Cut on growing networks.** One qubit per node, so it fits on the device for much longer, but the success chance still falls quickly.")
code('''
sizes = [4, 8, 12, 16, 20, 30, 40, 60, 80, 100, 140, 156]
maxcut_reports = [fc.fit_check(fc.maxcut_problem(fc.random_graph(n)), backend) for n in sizes]
for n, r in zip(sizes, maxcut_reports):
    if r.success is None:
        print(f"{n:>3} nodes | {r.verdict}: {r.reasons[0]}")
        continue
    print(f"{n:>3} nodes | 2q gates {r.metrics['two_qubit_gates']:>5} | success {fc.core.pct(r.success):>11} | "
          f"QPU {r.qpu_seconds:.2f} s | ${r.price['Pay-As-You-Go']:.2f} pay-as-you-go | {r.verdict}"
          + (f" (errors must be {r.error_reduction_needed:,.1f}x lower)" if r.error_reduction_needed else ""))

fig, ax = plt.subplots(figsize=(7.5, 4.2))
fitting = [r for r in maxcut_reports if r.success is not None]
FLOOR = 1e-12                                 # smaller values are left off the chart
fitting = [r for r in fitting if r.success >= FLOOR]
ax.semilogy([r.logical_qubits for r in fitting], [r.success for r in fitting], "o-", color="#2a78d6", label="Max-Cut (qubits = nodes)")
beds_fit = [r for _, r in rows if r.success is not None and r.success >= FLOOR]
ax.semilogy([r.logical_qubits for r in beds_fit], [r.success for r in beds_fit], "s-", color="#eb6834",
            label="Bed assignment (qubits = patients squared)")
ax.axhline(fc.core.SUCCESS_THRESHOLD, color="gray", linestyle="--", label="Our 10% threshold")
ax.set_xlabel("Qubits needed"); ax.set_ylabel("Estimated success chance per shot (log scale)")
ax.set_title(f"Estimated success on {backend.name}, 1 QAOA layer"); ax.grid(alpha=0.3); ax.legend(loc="upper right")
os.makedirs("results", exist_ok=True)
fig.savefig("results/success_vs_size.png", dpi=150, bbox_inches="tight"); plt.show()
''')

md("""
## 4. Does QAOA find the answer at all?

On a noiseless simulator, for sizes small enough to check exactly. This uses Qiskit's `StatevectorEstimator`
inside a classical optimiser loop (a hybrid workflow), then samples the best circuit.
""")
code('''
small_graph = fc.maxcut_problem(fc.random_graph(8))
q = fc.solve_qaoa(small_graph, reps=2)
print(f"Max-Cut, 8 nodes, 2 layers: best cut sampled {-q['best_sampled_cost']:.0f}, optimum {-q['optimal_cost']:.0f}, "
      f"approximation ratio {q['approximation_ratio']:.2f}, {q['share_of_shots_optimal']:.0%} of shots optimal")

beds = fc.assignment_problem(fc.synthetic_costs(3))
q = fc.solve_qaoa(beds, reps=1)
print(f"Bed assignment, 3 patients, 1 layer: best cost sampled {q['best_sampled_cost']:.0f}, optimum {q['optimal_cost']:.0f}, "
      f"only {q['share_of_shots_optimal']:.1%} of shots optimal")
''')
md("""
QAOA does well on the small graph. On the assignment problem most shots break the one-bed-per-patient
rule, even with no noise, while the classical method is exact in microseconds. That matches its
"classical-shaped" label.
""")

md("""
## 5. Testing our own estimate on a noisy simulator

A **mirror circuit** is a circuit followed by its inverse. A perfect device returns all zeros, so the
share of all-zero shots is the measured success. We compare that with our prediction for growing
problems, three random graphs per size, on a simulator built from the device's error rates. No QPU time.
""")
code('''
sim_rows = fc.simulator_sweep(sizes=(4, 6, 8, 10, 12), backend=backend, reps=1, shots=2000, seeds=(1, 2, 3))
fc.save_json({"backend": backend.name, "rows": sim_rows}, "results/simulator_validation.json")
for r in sim_rows:
    print(f"{r['num_nodes']:>2} nodes | predicted {r['predicted_mean']:.3f} +/- {r['predicted_std']:.3f} | "
          f"simulated {r['simulated_mean']:.3f} +/- {r['simulated_std']:.3f}")
''')

md("""
## 6. Hardware rehearsal on the local device copy

The exact code path of the real run (two Sampler jobs, error mitigation off then on), against the
local copy. It costs nothing and proves the hardware cell will work before any QPU time is spent.
On a simulator mitigation cannot help, it only adds gates; the comparison is meaningful on real hardware only.
""")
code('''
rehearsal = fc.run_experiment(backend, sizes=(4, 6, 8), shots=500)
for key, run in rehearsal["runs"].items():
    print(f"mitigation {key:>3}:", [(r["num_nodes"], round(r["predicted_success"], 3), round(r["measured_success"], 3)) for r in run["rows"]])
print(f"Predicted QPU time per job on real hardware: {rehearsal['predicted_qpu_seconds_per_job']:.1f} s")
''')

md("""
## 7. Real hardware: our run on IBM's ibm_fez

**We ran this on 2026-11-10** on `ibm_fez`, IBM's 156-qubit Heron r2 processor, through Qiskit
Runtime's `SamplerV2` on the free Open Plan. How it ran:

1. Six mirror circuits (Max-Cut QAOA on 4 to 14 nodes, followed by the inverse) were compiled for
   ibm_fez with the same code as section 6.
2. **Before submitting**, our predicted success for each circuit was computed from that day's
   calibration and saved to `results/hardware_run.json` with the job IDs, so the prediction could not
   be adjusted after seeing the results.
3. Two jobs ran the six circuits with 1,000 shots each: one with error mitigation **off**, one
   **on** (dynamical decoupling plus Pauli twirling).
4. The collect cell fetched the results by job ID and measured the share of all-zero shots.

The cells below show the saved results, so they run without a key and spend nothing. To repeat the
run, set `RUN_ON_HARDWARE = True`. It needs `QISKIT_IBM_TOKEN` (and optionally `QISKIT_IBM_INSTANCE`)
in Colab Secrets (the key icon in the sidebar) or environment variables. Never paste a key into a cell.
It costs about 8 seconds of QPU time.
""")
code('''
RUN_ON_HARDWARE = False
PLAN_FILE = "results/hardware_run.json"

if RUN_ON_HARDWARE:
    service = fc.connect_service()
    real = fc.connect_ibm(service=service)
    print("Device:", real.name, fc.device_summary(real))
    plan, jobs = fc.submit_experiment(real, sizes=(4, 6, 8, 10, 12, 14), reps=1, shots=1000)
    plan["device_snapshot"] = fc.device_summary(real)
    fc.save_json(plan, PLAN_FILE)             # predictions and job IDs on record first
    print("Submitted:", plan["job_ids"])
elif os.path.exists(PLAN_FILE):
    saved = fc.load_json(PLAN_FILE)
    snap = saved.get("device_snapshot", {})
    print(f"Not resubmitting. Saved run: {saved['backend']}, predictions made {saved['prepared_at'][:19]} UTC")
    print(f"That day's calibration: two-qubit ({snap.get('two_qubit_gate')}) error {snap.get('median_two_qubit_error', 0):.3%}, "
          f"readout error {snap.get('median_readout_error', 0):.3%}, {snap.get('num_qubits')} qubits")
    print("Job IDs:", saved["job_ids"])
else:
    print("Skipped. Nothing was submitted.")
''')
code('''
# Collect: fetches the results by job ID once the jobs have finished (also works in a new session).
if os.path.exists(PLAN_FILE):
    plan = fc.load_json(PLAN_FILE)
    if "runs" not in plan and RUN_ON_HARDWARE:
        plan = fc.collect_experiment(plan, service=fc.connect_service())
        fc.save_json(plan, PLAN_FILE)
    hardware_results = plan if "runs" in plan else None
else:
    hardware_results = None
print("Hardware results available:", hardware_results is not None)
if hardware_results:
    for key, run in hardware_results["runs"].items():
        print(f"\\nmitigation {key}: job {run['job_id']}, QPU seconds used {run['qpu_seconds_used']} "
              f"(predicted {hardware_results['predicted_qpu_seconds_per_job']:.1f})")
        for r in run["rows"]:
            print(f"   {r['num_nodes']:>2} qubits | {r['two_qubit_gates']:>3} two-qubit gates | predicted {r['predicted_success']:.3f} | "
                  f"measured {r['measured_success']:.3f} +/- {r['measured_stderr']:.3f}")
''')
md("""
**What the hardware said.** Measured success is below our prediction at every size, and the gap mostly
grows with the circuit: from about 9 points at 4 qubits to about 31 points at 12 qubits (mitigation off).
Our formula counts gate and readout errors only; real hardware also loses accuracy while qubits wait,
to crosstalk between neighbours and to drift, so the formula is optimistic. The noisy simulator could
not show this, because it is built from the same error rates as the formula. Error mitigation lowered
the score on these short circuits: twirling adds gates and randomness, and dynamical decoupling helps
most on long idle periods, which these circuits do not have. QPU time used: 4 seconds per job, close
to the 3.6 seconds we predicted, so the cost side of the estimate held up.
""")

md("## 8. Headline chart: predicted against measured success")
code('''
ax = fc.plot_validation(sim_rows, hardware_results)
ax.figure.savefig("results/validation.png", dpi=150, bbox_inches="tight")
plt.show()
''')

md("""
## What this shows, and what it does not

- **The tool gives a defensible answer before any QPU time is spent**: qubits, gates, success chance,
  QPU seconds and price, next to a measured classical time.
- **Bed assignment is classical-shaped.** Twelve patients need 144 of 156 qubits and the circuit is
  drowned by noise, while the classical solver handles a thousand patients exactly in well under a second.
- **Max-Cut is an open question.** Small graphs run cleanly; beyond a few dozen nodes noise dominates,
  and no quantum advantage has been proven for it.
- **What would have to change.** For each problem that fails, the tool reports how many times lower
  the device's errors would need to be for the same circuit to pass. For the 12-patient assignment
  that is tens of times lower than this device's error rates (see the table in section 3), and it
  would still only be a 12-patient problem.
- **Our formula is optimistic, and real hardware proved it.** It counts gate and readout errors only.
  It agrees with the noisy simulator because that simulator is built from the same error rates. On
  ibm_fez, measured success fell 9 to 31 points below the prediction, and the gap grew with size. The
  verdicts lean the right way (a circuit we call borderline is worse in practice, not better), and the
  QPU-time estimate held: 4 seconds used against 3.6 predicted.
- **Price** uses IBM's published per-minute rates and IBM's own usage formula. It is an estimate, not
  a quote. One job is dominated by a fixed overhead of about 2 seconds; a full QAOA angle search is
  priced as 100 such jobs.

See `LIMITATIONS.md` for the full list.
""")

nb = nbf.v4.new_notebook(cells=cells, metadata={
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"}})
out = Path(__file__).resolve().parent.parent / "notebooks" / "quantum_fit_check.ipynb"
out.parent.mkdir(exist_ok=True)
nbf.write(nb, out)
print("wrote", out)
