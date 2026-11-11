# Submission form text

Copy each block into the DeepStation Submission tab.

## Project Name

Quantum Fit Check

## Description

**The problem.** Hospitals, logistics teams and finance groups keep hearing that quantum computing may
solve their hardest scheduling and optimisation problems. The people who must decide, such as a
hospital bed manager, have no quick, honest way to tell whether their own problem is worth a quantum
experiment, or what it would cost. Today that answer needs a specialist or scarce hardware time: IBM's
free plan gives 10 minutes, and paid time starts at $96 a minute.

**What we built.** Quantum Fit Check takes a problem described in plain English (or an uploaded CSV),
turns it into a quantum optimisation circuit with Qiskit (an Ising cost function and a QAOA circuit),
compiles it for IBM's real 156-qubit ibm_fez processor, and answers before any quantum time is spent:
how many qubits and gates it needs, the chance a shot runs without error, the QPU seconds and price on
each IBM plan, how long a classical computer takes, and a verdict: does not fit, runs but noise
dominates, or worth a hardware test. When the answer is no, it says how much lower the device's errors
would need to be. It runs as a Jupyter notebook and an interactive Streamlit app with a live map of
the chip.

**The quantum opportunity.** Quantum computers are expected to help with problems whose classical cost
grows exponentially, such as molecular simulation and some optimisation problems. The opportunity is
real, but so is the noise on today's devices. Our tool makes that trade-off visible per problem, so
teams spend hardware time where it can teach them something, and not where a laptop already wins.

**Results on a simulator.** On a noisy simulator built from ibm_fez's error rates, our predicted
success matched the simulated success within 2 percentage points for circuits of 4 to 12 qubits. Our
hospital example shows why the tool matters: assigning 12 patients to 12 beds needs 144 of the chip's
156 qubits and about 15,000 two-qubit gates, so noise dominates (under 0.01% chance of an error-free
shot), while a classical algorithm assigns 1,000 patients exactly in milliseconds.

**Results on real quantum hardware.** We ran our own test on IBM's ibm_fez (156-qubit Heron r2) on
2026-11-10 with Qiskit Runtime's SamplerV2 on the Open Plan. We built six mirror circuits (QAOA on 4 to
14 qubits followed by its inverse, so a perfect device returns all zeros), saved our predictions and
the job IDs before any result came back, and ran two jobs of 1,000 shots: error mitigation off, and on
(dynamical decoupling plus Pauli twirling). Job IDs: dbpq5q44148s739v19j0 and dbpq5r8ou4as73cu2ts0.
Measured success was below our prediction at every size: 82% against 90% at 4 qubits, 23% against 54%
at 12 qubits. The gap grows with the circuit because real hardware also loses accuracy to idle
decoherence, crosstalk and drift, which the simulator could not show. QPU time matched the estimate
(4 seconds per job against 3.6 predicted). The hardware made our tool more honest: its verdicts are,
if anything, generous, and we report that in LIMITATIONS.md.

**No hype.** We never claim quantum beats classical. "Worth a hardware test" only means a circuit can
run cleanly enough to measure.

## GitHub Repository

https://github.com/Illia-Shyn/Quantum_Hackathon_Noble_Raptors

## Files to upload

- `notebooks/quantum_fit_check.ipynb` (code with outputs, including the hardware run in section 7)
- the slide deck (PDF or PPTX)
- `results/validation.png` (predicted against simulator and hardware)
- screenshots from `submission/screenshots/`
- the video (MP4, under 5 minutes)
