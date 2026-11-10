# Use case

**Problem.** Teams in hospitals, logistics and finance are told quantum computing may help them, but
they cannot tell whether their own problem is worth a quantum experiment, or what it would cost.
Finding out today means hiring an expert or spending scarce hardware time.

**Current method.** Read vendor material, or hand-build a circuit and try it. Neither gives a number
before time and money are spent.

**Classical baseline.** Every check runs a classical solver on the same problem and times it: the
Hungarian algorithm for assignment (exact), brute force for small graphs (exact), and a local-search
heuristic for larger graphs.

**Quantum hypothesis.** We do not hypothesise an advantage. Our hypothesis is about prediction: the
success of a QAOA circuit on a given IBM device can be estimated from the device's published error
rates, before running it, well enough to sort problems into "does not fit", "runs, but noise
dominates" and "worth a hardware test".

**Experiment.** Two problems go through the tool at growing sizes: hospital bed assignment (synthetic
costs) and Max-Cut on random 3-regular graphs. We then test the estimate with mirror circuits, on a
noisy simulator and on a real IBM device with error mitigation off and on.

**Metrics.** Qubits, two-qubit gates, estimated success per shot, QPU seconds, price per IBM plan,
classical solve time, and predicted against measured success.

**Evidence.** In `results/` and the notebook. On the local copy of ibm_fez: 12 patients need 144 of 156
qubits and about 15,000 two-qubit gates, with an estimated success under 0.01%, while the classical
solver handles 1,000 patients exactly in milliseconds. Max-Cut passes our 10% threshold up to about 30
nodes. Predicted and simulated success agree within about 2 percentage points for 4 to 12 nodes.

**Limitations.** See `LIMITATIONS.md`. The main ones: the formula ignores idle decoherence and
crosstalk, the simulator shares the formula's error rates, and the shape labels are our documented
judgement.

**Recommendation.** Bed assignment is classical-shaped: keep it classical. Max-Cut is an open question:
small instances are worth a hardware test for learning, with no advantage expected. Use the tool as a
first filter before spending hardware time, not as proof of anything.

**Data.** Hospital costs and graphs are synthetic, generated with fixed seeds. Device error rates and
prices are IBM's published figures.
