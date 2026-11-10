"""Run QAOA on an ideal simulator for small problems, to compare its answer with the classical one."""
from __future__ import annotations

import numpy as np
from qiskit.primitives import StatevectorEstimator, StatevectorSampler
from scipy.optimize import minimize

from .circuits import qaoa_circuit
from .classical import brute_force
from .problems import Problem

QAOA_LIMIT = 16   # qubits


def solve_qaoa(problem: Problem, reps: int = 1, shots: int = 2000, seed: int = 7, restarts: int = 3) -> dict:
    """Optimise the QAOA angles with COBYLA on a noiseless simulator, then sample the best circuit."""
    if problem.num_qubits > QAOA_LIMIT:
        raise ValueError(f"The simulator run is limited to {QAOA_LIMIT} qubits")
    circuit = qaoa_circuit(problem, reps)
    hamiltonian = problem.hamiltonian()
    scale = max(1.0, float(np.abs(hamiltonian.coeffs).max()))     # keeps angles in a sensible range
    estimator = StatevectorEstimator(seed=seed)

    def energy(theta):
        result = estimator.run([(circuit, hamiltonian, theta)]).result()
        return float(result[0].data.evs) + problem.offset

    rng = np.random.default_rng(seed)
    best = None
    for _ in range(restarts):
        x0 = np.concatenate([rng.uniform(0, np.pi, reps) / scale, rng.uniform(0, np.pi / 2, reps)])
        res = minimize(energy, x0, method="COBYLA", options={"maxiter": 200, "rhobeg": 0.5 / scale})
        if best is None or res.fun < best.fun:
            best = res
    measured = circuit.copy()
    measured.measure_all()
    sampler = StatevectorSampler(seed=seed)
    counts = sampler.run([(measured, best.x)], shots=shots).result()[0].data.meas.get_counts()
    costs = {b: problem.cost_of_bitstring(b) for b in counts}
    best_bits = min(costs, key=costs.get)
    exact = brute_force(problem)
    out = {
        "expected_cost": float(best.fun), "best_sampled_cost": float(costs[best_bits]),
        "best_sampled_bitstring": best_bits, "optimal_cost": exact["cost"],
        "share_of_shots_optimal": sum(v for b, v in counts.items()
                                      if abs(costs[b] - exact["cost"]) < 1e-9) / shots,
        "angles": [float(v) for v in best.x], "shots": int(shots),
    }
    if problem.kind == "maxcut" and exact["cost"] != 0:
        out["approximation_ratio"] = float(best.fun / exact["cost"])
    return out
