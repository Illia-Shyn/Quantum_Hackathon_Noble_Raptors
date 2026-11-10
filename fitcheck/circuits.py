"""QAOA and mirror circuits, built gate by gate from the problem's Ising terms."""
from __future__ import annotations

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit import ParameterVector

from .problems import Problem


def qaoa_circuit(problem: Problem, reps: int = 1, measure: bool = False) -> QuantumCircuit:
    """QAOA ansatz with `reps` layers. Parameters: gamma[0..reps-1], beta[0..reps-1]."""
    if reps < 1:
        raise ValueError("reps must be at least 1")
    n = problem.num_qubits
    gamma = ParameterVector("gamma", reps)
    beta = ParameterVector("beta", reps)
    qc = QuantumCircuit(n, name=f"qaoa_p{reps}")
    qc.h(range(n))
    for layer in range(reps):
        for (i, j), w in problem.quadratic.items():      # problem layer: exp(-i gamma H)
            if w != 0:
                qc.rzz(2 * w * gamma[layer], i, j)
        for i, w in enumerate(problem.linear):
            if w != 0:
                qc.rz(2 * w * gamma[layer], i)
        qc.rx(2 * beta[layer], range(n))                 # mixer layer
    if measure:
        qc.measure_all()
    return qc


def bind_random(circuit: QuantumCircuit, seed: int = 7) -> QuantumCircuit:
    """Bind every parameter to a fixed random angle (used for sizing and mirror circuits)."""
    rng = np.random.default_rng(seed)
    values = {p: float(rng.uniform(0.1, 1.0)) for p in circuit.parameters}
    return circuit.assign_parameters(values)


def mirror_circuit(circuit: QuantumCircuit) -> QuantumCircuit:
    """The circuit followed by its inverse. A perfect device returns all zeros,
    so the measured all-zeros rate is the circuit's success rate."""
    if circuit.parameters:
        raise ValueError("Bind the parameters before building a mirror circuit")
    body = circuit.remove_final_measurements(inplace=False)
    qc = QuantumCircuit(body.num_qubits, name=f"mirror_{body.name}")
    qc.compose(body, inplace=True)
    qc.barrier()                                         # stops the transpiler cancelling the two halves
    qc.compose(body.inverse(), inplace=True)
    qc.measure_all()
    return qc
