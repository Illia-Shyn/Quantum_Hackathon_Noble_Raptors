# Quantum Fit Check

**Is this problem worth running on today's quantum computers, and what would it cost?**

Team Noble Raptors · Qiskit Fall Fest 2026, Miami Dade College

## The problem

Operations and analytics teams in hospitals, logistics and finance keep hearing that quantum computing
may help them. They have no quick way to tell whether their own problem is worth a quantum experiment,
or what one would cost. Today the answer needs a specialist, or scarce hardware time: the free IBM plan
gives 10 minutes, and paid time starts at $96 a minute. A wrong guess wastes both, and feeds hype.

**Who it is for:** the person who has to decide, such as a hospital bed manager or a logistics planner,
and the quantum team that has to give them an honest answer.

## What it does

Quantum Fit Check takes a problem, builds its quantum circuit in Qiskit, compiles it for a real IBM
device, and answers before any quantum time is spent:

- how many qubits and gates the problem needs on that device,
- the chance a shot finishes without an error, from IBM's published error rates,
- the QPU seconds and the price on each IBM plan,
- how long a classical computer takes on the same problem,
- a verdict: **does not fit**, **runs, but noise dominates**, or **worth a hardware test**,
- when it fails, what would need to improve: how many times lower the device's errors must be,
- a one-sentence summary in plain words.

It then tests its own estimates with mirror circuits on a noisy simulator and on real hardware.

## What it does not claim

It never says quantum beats classical. "Worth a hardware test" only means the circuit can run cleanly
enough to measure. See [LIMITATIONS.md](LIMITATIONS.md).

## Run it

**Google Colab:** open [notebooks/quantum_fit_check.ipynb](notebooks/quantum_fit_check.ipynb) in Colab
and choose Runtime, Run all. The first cell clones this repository and installs everything. No key is
needed up to section 7.

**On a laptop** (Python 3.10 or later):

```bash
pip install -r requirements.txt
```

```bash
jupyter notebook notebooks/quantum_fit_check.ipynb
```

**The interactive app** (Streamlit, on a laptop):

```bash
streamlit run app.py
```

It opens at http://localhost:8501. Describe a task in plain words or pick a problem (a random network,
synthetic hospital data, or your own CSV), press **Run fit check**, and read the answer in five tabs:
Problem, Circuit, Qubits (a live map of the 156-qubit chip), Estimates and Validation. **Simple** view is
for the decision maker; **Expert** view adds the cost-function heatmap, gate counts and drawings, per-link
error rates, the price on every plan and the transpiler-seed spread. Hover any chart for its numbers, and
download the report as Markdown. The app uses the local copy of ibm_fez, so it needs no IBM key and spends
no QPU time; the Validation tab reads the hardware results saved in `results/`.

To publish it, deploy the repository on Streamlit Community Cloud with `app.py` as the entry point. For
plain-language intake there, add `GEMINI_API_KEY` under the app's Secrets; locally, use an environment
variable or `.streamlit/secrets.toml` (git-ignored). Never give the app an IBM key: anyone with the link
could spend your minutes.

**In code:**

```python
import fitcheck as fc

report = fc.fit_check(fc.maxcut_problem(fc.random_graph(10)))   # local copy of ibm_fez, no key
print(report.to_markdown())

spec, report = fc.check_request("Assign 4 patients to 4 hospital beds at the lowest cost")
```

**Tests:**

```bash
python -m pytest -q
```

## Optional keys

Keys go in Colab Secrets (the key icon in the sidebar) or environment variables. Never in a cell or a commit.

| Name | Used for |
| --- | --- |
| `GEMINI_API_KEY` | Plain-language intake, in the notebook and the app. Without it the tool uses keyword matching. `GEMINI_MODEL` overrides the model. |
| `QISKIT_IBM_TOKEN`, `QISKIT_IBM_INSTANCE` | The real hardware run in section 7 of the notebook. |

## How it works

| Stage | What happens | Code |
| --- | --- | --- |
| Intake | A sentence becomes a problem type and size. The language model only picks the template. | `fitcheck/intake.py` |
| Build | The problem becomes an Ising cost function and a QAOA circuit, gate by gate. | `fitcheck/problems.py`, `fitcheck/circuits.py` |
| Transpile | The circuit is compiled for the device, avoiding dead couplers and keeping the best of three layouts. | `fitcheck/estimate.py` |
| Estimate | Success chance, QPU seconds (IBM's usage formula) and price (IBM's published rates). | `fitcheck/estimate.py`, `fitcheck/device.py` |
| Baseline | The same problem is solved classically and timed. | `fitcheck/classical.py` |
| Verdict | Fit verdict plus a documented problem-shape label. | `fitcheck/core.py` |
| Validate | Mirror circuits: predicted against measured success, simulator and hardware. | `fitcheck/validate.py`, `fitcheck/hardware.py` |

Prices were read from https://www.ibm.com/quantum/pricing on 2026-11-10: Pay-As-You-Go $96, Flex $72
and Premium $48 per minute; the Open Plan gives up to 10 free minutes. The QPU-time formula is from
IBM's "Workload usage" guide.

## Results

Saved in [results/](results/): the simulator validation data, the headline chart, and the hardware run
once it has been submitted. All generated graphs and cost tables use fixed seeds, so every number can
be reproduced. The hospital data is synthetic.

## Files

- `fitcheck/` the library (`fitcheck/visuals.py` holds the interactive Plotly charts)
- `app.py` the interactive Streamlit app
- `notebooks/quantum_fit_check.ipynb` the demo, with outputs
- `tools/build_notebook.py` regenerates the notebook
- `tests/` the test suite
- `USE-CASE.md`, `LIMITATIONS.md`
- `slides/QA-CHEAT-SHEET.md` short answers to likely judging questions
