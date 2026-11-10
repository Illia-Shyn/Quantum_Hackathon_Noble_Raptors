# Q&A cheat sheet

Short answers to the questions the judging rubric tells judges to ask. Numbers are from the notebook
run on the local copy of ibm_fez with one QAOA layer.

## One sentence, no physics

Before you spend a cent, our tool tells you whether today's quantum computers can run your problem,
what it would cost, and how a normal computer compares.

## Problem

**What problem are you solving, and for whom?**
Decision-makers such as a hospital bed manager or a logistics planner are told quantum might help.
They have no quick, honest way to check. We give them an answer before any quantum time is spent.

**Why does it matter?**
Hardware time is scarce and expensive: 10 free minutes on IBM's Open Plan, then from $96 a minute. A
wrong guess wastes both and feeds hype.

## Quantum rationale

**Why quantum instead of a classical approach?**
For the problems we tested, it isn't better, and the tool says so. Bed assignment is solved exactly by
the Hungarian algorithm in polynomial time, so it is classical-shaped. Max-Cut is an open question: no
advantage has been proven for QAOA. Chemistry simulation is quantum-shaped, because exact classical
cost doubles with every orbital, but useful sizes are far beyond today's devices.

**What would need to improve for this to beat classical?**
The tool reports it per problem. A 12-patient assignment needs device errors about 34 times lower just
to return a readable signal, and that is still a tiny problem. Useful sizes need error correction, and
even then assignment has no known quantum speed-up worth having.

**Why QAOA?**
It is the standard near-term algorithm for yes/no optimisation, it maps directly from the problem's
cost function, and its circuit size is easy to reason about: one RZZ gate per pair of linked variables.

## Technical

**Walk me through your circuit.**
One qubit per variable. Hadamard gates put every qubit in superposition. The problem layer applies an
RZZ gate for every pair of linked variables and an RZ for single-variable terms, scaled by an angle
gamma. The mixer layer applies RX on every qubit, scaled by beta. Repeat for more layers, then measure.

**How do you estimate success?**
We compile the circuit for the device, then multiply (1 - error) over every gate and every readout,
using the device's published error rates for the exact qubits used. Rz is virtual and costs nothing;
two-qubit CZ gates dominate.

**How do you estimate QPU time and price?**
IBM's usage formula: about 2 seconds of overhead per job, plus (250 microseconds reset delay + circuit
duration) per shot. Price is that time at IBM's published per-minute rate. A full QAOA search is priced
as 100 jobs, which is our assumption.

**What did you build versus reuse?**
Built: the problem-to-Ising mapping, the QAOA circuit, the mirror circuits, the success and cost
estimates, the verdict logic, and the validation flow. Reused: Qiskit's transpiler and primitives,
Aer's noise simulator, SciPy's optimiser and Hungarian solver, NetworkX graphs.

**What was hardest to get working?**
The device's calibration data lists a few couplers with an error of 1.0, meaning dead. The transpiler
routed through them and our estimate collapsed to almost zero. We now remove those couplers before
compiling and keep the best of three layouts. With them removed, only 154 of the 156 qubits are
connected, so a full-width problem is reported as "does not fit".

**Which Qiskit features do you use?**
Parameterised circuits, SparsePauliOp Hamiltonians, the preset pass manager with a custom Target,
StatevectorEstimator and StatevectorSampler in a hybrid optimisation loop, Aer's device noise model,
and Runtime SamplerV2 with dynamical decoupling and gate twirling.

## Results

**How do you know it worked?**
Three checks. The cost functions are tested against brute force and the Hungarian algorithm. The
success formula is tested with mirror circuits on a noisy simulator: within about 2 percentage points
for 4 to 12 qubits, three graphs per size. And [hardware result once run].

**What did you compare against?**
Every report includes a timed classical solver on the same problem: 1,000 patients assigned exactly in
about 3 ms, against a quantum circuit drowned by noise at 6 patients.

**What surprised you?**
How fast compiling inflates the circuit: a 12-patient assignment becomes about 15,000 two-qubit gates.
Also that noiseless one-layer QAOA found the best 3-patient assignment in only about 1% of shots.

**Isn't the simulator check circular?**
Partly, and we say so. The simulator uses the same error rates as the formula, so it checks the
formula is computed correctly. Only real hardware tests whether it matches a device.

## Innovation

**What makes your approach different?**
Most projects run one algorithm and report a result. Ours is a tool whose most common answer is "don't
use quantum for this", with a price and a classical time attached, and it tests its own predictions.

## Honesty checks

**Does the AI model decide anything?**
No. It only turns a sentence into a problem type and a size, and the tool shows how it understood the
request. Without a key it falls back to keyword matching.

**Is the hospital data real?**
No, it is synthetic, generated with a fixed seed and labelled as such.

**Could your verdict be wrong?**
Yes. The formula ignores idle decoherence, crosstalk and drift, so it is optimistic. The 10% threshold
is our choice. See LIMITATIONS.md.

## Next steps

Add idle decoherence to the formula, size chemistry problems, and let people upload their own tables.
