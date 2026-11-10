# Test questions

Paste each sentence into the `request = "..."` line in section 1 of the notebook and run the cell.
Expected results are from the local copy of ibm_fez with keyword matching (no Gemini key). With a
Gemini key the type and size should match; the wording of "how it was understood" will differ.

| # | Question | Type | Qubits | Shape | Verdict | Success |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Assign 3 nurses to 3 shifts at the lowest cost | assignment | 9 | classical-shaped | worth a hardware test | 77.60% |
| 2 | We need to assign 4 patients to 4 hospital beds | assignment | 16 | classical-shaped | worth a hardware test | 46.29% |
| 3 | Match 6 drivers to 6 delivery routes | assignment | 36 | classical-shaped | runs, but noise dominates | 1.13% |
| 4 | Assign 12 patients to 12 beds | assignment | 144 | classical-shaped | runs, but noise dominates | under 0.01% |
| 5 | Allocate 13 patients to 13 beds | assignment | 169 | classical-shaped | does not fit | none |
| 6 | Split a network of 10 routers into two groups | maxcut | 10 | open question | worth a hardware test | 74.01% |
| 7 | Partition a graph of 30 nodes | maxcut | 30 | open question | worth a hardware test | 21.85% |
| 8 | Cluster a network of 60 sensors into two communities | maxcut | 60 | open question | runs, but noise dominates | 0.16% |
| 9 | Split a network of 156 nodes into two groups | maxcut | 156 | open question | does not fit | none |
| 10 | Pick the best portfolio from 20 stocks | qubo | 20 | open question | worth a hardware test | 43.56% |
| 11 | Find the ground-state energy of a drug molecule | molecule_energy | none | quantum-shaped | not sized | none |
| 12 | Break RSA encryption with a 2048-bit key | factoring | none | quantum-shaped | not sized | none |
| 13 | Look up one record in an unsorted database | search | none | classical-shaped | not sized | none |
| 14 | Train an image classifier on 1 million photos | other | none | classical-shaped | not sized | none |
| 15 | Add up the numbers in my spreadsheet | other | none | classical-shaped | not sized | none |

## What each group checks

- **1 to 5:** the assignment problem from easy to impossible; all three verdicts appear.
- **6 to 9:** Max-Cut from easy to too wide for the device (only 154 of 156 qubits are connected).
- **10:** general yes/no optimisation, sized with a Max-Cut stand-in.
- **11 to 15:** tasks the tool cannot turn into a circuit; it should give a shape label and say "not sized".

## Good ones for the live demo

Questions 2, 4 and 11 in that order: one that passes, one that fails with "what would need to
improve", and one that is quantum-shaped but out of reach today.
