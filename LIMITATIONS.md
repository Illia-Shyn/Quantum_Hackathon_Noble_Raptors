# Limitations

What this work cannot support.

**No advantage claim.** Nothing here shows quantum beating a classical computer. Every problem we ran
was solved faster and exactly, or near-exactly, by the classical baseline.

**The success formula is optimistic.** It multiplies (1 - error) over every gate and readout. It leaves
out idle decoherence (T1 and T2), crosstalk, leakage and calibration drift. Real hardware should score
lower than the prediction, more so for deeper circuits.

**The simulator check is partly circular.** The noisy simulator is built from the same error rates the
formula uses, so their agreement shows the formula is computed correctly, not that it matches a real
device. Only the hardware points test that.

**Success is not solution quality.** The estimate is the chance that a shot has no error. It says
nothing about whether QAOA would find a good answer. In our noiseless test, one-layer QAOA on a
3-patient assignment returned the optimum in about 1% of shots.

**Device data is a snapshot.** The local copy of ibm_fez holds one past calibration. Error rates change
daily; the hardware cell records a fresh summary at run time. We drop couplers reported with an error
of 0.5 or more and keep the best of three transpiler seeds, which is itself a choice.

**Price is an estimate, not a quote.** It uses IBM's published starting prices (read 2026-11-10) and
IBM's usage formula with a 2-second per-job overhead. Queue time, failed jobs, error-mitigation
overhead and contract minimums (Flex 400 minutes, Premium 5,200 minutes) are not included. The "full
QAOA search" figure assumes 100 jobs, which is our assumption.

**Narrow problem coverage.** Circuits are built only for Max-Cut and assignment (general yes/no
optimisation is sized with a Max-Cut stand-in). Chemistry, factoring and search get a shape label and
no circuit estimate.

**Shape labels are our judgement.** "Classical-shaped", "quantum-shaped" and "open question" come from
a short table we wrote (`fitcheck/core.py`), not from a computation.

**Thresholds are ours.** "Noise dominates" means an estimated success below 10%. A different threshold
moves the boundary.

**The language model can misread a request.** It only picks a problem type and size, and the tool
shows how it understood the request. Without a key, keyword matching is used and is cruder. The Gemini
path has not been tested with a live key by us at the time of writing.

**Synthetic data.** Hospital costs and graphs are generated. No real hospital data is used.
