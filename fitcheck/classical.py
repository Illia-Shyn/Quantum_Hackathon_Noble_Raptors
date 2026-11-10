"""Classical baselines, timed on the same problem the quantum estimate is for."""
from __future__ import annotations

import time

import networkx as nx
import numpy as np
from scipy.optimize import linear_sum_assignment

from .problems import Problem

BRUTE_FORCE_LIMIT = 22   # qubits


def brute_force(problem: Problem) -> dict:
    """Exact minimum by checking every assignment (only up to BRUTE_FORCE_LIMIT variables)."""
    n = problem.num_qubits
    if n > BRUTE_FORCE_LIMIT:
        raise ValueError(f"Brute force is limited to {BRUTE_FORCE_LIMIT} variables")
    start = time.perf_counter()
    idx = np.arange(2 ** n, dtype=np.int64)
    z = [1.0 - 2.0 * ((idx >> i) & 1) for i in range(n)]
    cost = np.full(idx.shape, problem.offset, dtype=float)
    for i, w in enumerate(problem.linear):
        if w != 0:
            cost += w * z[i]
    for (i, j), w in problem.quadratic.items():
        cost += w * z[i] * z[j]
    best = int(np.argmin(cost))
    seconds = time.perf_counter() - start
    bits = [(best >> i) & 1 for i in range(n)]
    return {"method": "brute force (exact)", "cost": float(cost[best]), "bits": bits,
            "seconds": seconds, "exact": True}


def solve_classically(problem: Problem, seed: int = 7) -> dict:
    """Best available classical answer for this problem type, with its measured time."""
    if problem.kind == "assignment":
        costs = problem.meta["costs"]
        start = time.perf_counter()
        rows, cols = linear_sum_assignment(costs)
        seconds = time.perf_counter() - start
        return {"method": "Hungarian algorithm (exact, polynomial time)",
                "cost": float(costs[rows, cols].sum()), "seconds": seconds, "exact": True,
                "assignment": [int(c) for c in cols]}
    if problem.kind == "maxcut":
        if problem.num_qubits <= BRUTE_FORCE_LIMIT:
            out = brute_force(problem)
            out["cut"] = -out["cost"]
            return out
        g = problem.meta["graph"]
        start = time.perf_counter()
        cut, _ = nx.algorithms.approximation.one_exchange(g, weight="weight", seed=seed)
        seconds = time.perf_counter() - start
        return {"method": "one-exchange local search (heuristic, not proven optimal)",
                "cost": -float(cut), "cut": float(cut), "seconds": seconds, "exact": False}
    if problem.num_qubits <= BRUTE_FORCE_LIMIT:
        return brute_force(problem)
    return {"method": "none run (too large for brute force)", "cost": None, "seconds": None,
            "exact": False}


def assignment_scaling(sizes=(10, 100, 1000), seed: int = 7) -> list[dict]:
    """Measured classical solve time for growing assignment problems, next to the qubits QAOA would need."""
    rows = []
    rng = np.random.default_rng(seed)
    for n in sizes:
        costs = rng.integers(1, 10, size=(n, n)).astype(float)
        start = time.perf_counter()
        linear_sum_assignment(costs)
        rows.append({"patients": int(n), "classical_seconds": time.perf_counter() - start,
                     "qubits_needed": int(n * n)})
    return rows
