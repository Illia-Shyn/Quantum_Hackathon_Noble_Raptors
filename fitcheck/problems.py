"""Problem definitions. Every problem is reduced to one Ising cost function:

    cost(z) = offset + sum_i h[i] * z_i + sum_{i<j} J[i, j] * z_i * z_j,   z_i in {+1, -1}

which we want to MINIMISE. Bit x_i = 0 means z_i = +1 and x_i = 1 means z_i = -1.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx
import numpy as np
from qiskit.quantum_info import SparsePauliOp


@dataclass
class Problem:
    kind: str                      # "maxcut", "assignment" or "qubo"
    name: str
    description: str
    num_qubits: int
    linear: np.ndarray             # h[i]
    quadratic: dict                # {(i, j): J_ij} with i < j
    offset: float = 0.0
    meta: dict = field(default_factory=dict)

    def hamiltonian(self) -> SparsePauliOp:
        """Cost Hamiltonian as a SparsePauliOp (the offset is left out)."""
        terms = [("ZZ", [i, j], float(w)) for (i, j), w in self.quadratic.items() if w != 0]
        terms += [("Z", [i], float(w)) for i, w in enumerate(self.linear) if w != 0]
        if not terms:
            terms = [("I", [0], 0.0)]
        return SparsePauliOp.from_sparse_list(terms, num_qubits=self.num_qubits)

    def cost(self, bits) -> float:
        """Cost of one assignment. bits[i] is the value (0 or 1) of qubit i."""
        z = 1 - 2 * np.asarray(bits, dtype=float)
        total = self.offset + float(self.linear @ z)
        for (i, j), w in self.quadratic.items():
            total += w * z[i] * z[j]
        return float(total)

    def cost_of_bitstring(self, bitstring: str) -> float:
        """Cost of a Qiskit bitstring (qubit 0 is the rightmost character)."""
        return self.cost([int(c) for c in reversed(bitstring)])


def qubo_to_problem(Q: np.ndarray, kind="qubo", name="QUBO", description="", meta=None) -> Problem:
    """Minimise x^T Q x for binary x. Q may be any square matrix; it is symmetrised."""
    Q = np.asarray(Q, dtype=float)
    n = Q.shape[0]
    if Q.shape != (n, n):
        raise ValueError("Q must be a square matrix")
    upper = np.triu(Q) + np.triu(Q.T, 1)          # fold everything into the upper triangle
    h = np.zeros(n)
    J = {}
    offset = 0.0
    for i in range(n):
        offset += upper[i, i] / 2
        h[i] -= upper[i, i] / 2
        for j in range(i + 1, n):
            q = upper[i, j]
            if q == 0:
                continue
            offset += q / 4
            h[i] -= q / 4
            h[j] -= q / 4
            J[(i, j)] = q / 4
    return Problem(kind, name, description, n, h, J, offset, meta or {})


def random_graph(num_nodes: int, degree: int = 3, seed: int = 7) -> nx.Graph:
    """Random regular graph with unit weights; falls back to a smaller degree when needed."""
    if num_nodes < 2:
        raise ValueError("A graph needs at least 2 nodes")
    degree = min(degree, num_nodes - 1)
    if (num_nodes * degree) % 2:
        degree -= 1
    if degree < 1:
        degree = 1 if num_nodes % 2 == 0 else 2
    return nx.random_regular_graph(degree, num_nodes, seed=seed)


def maxcut_problem(graph: nx.Graph, name: str | None = None) -> Problem:
    """Max-Cut: split the nodes into two groups so the total weight of cut edges is largest."""
    nodes = sorted(graph.nodes())
    index = {node: k for k, node in enumerate(nodes)}
    n = len(nodes)
    J = {}
    offset = 0.0
    for u, v, data in graph.edges(data=True):
        if u == v:
            continue
        w = float(data.get("weight", 1.0))
        i, j = sorted((index[u], index[v]))
        J[(i, j)] = J.get((i, j), 0.0) + w / 2
        offset -= w / 2
    relabelled = nx.relabel_nodes(graph, index)
    return Problem(
        "maxcut",
        name or f"Max-Cut on {n} nodes",
        f"Split a network of {n} nodes and {graph.number_of_edges()} links into two groups, "
        "cutting as many links as possible.",
        n, np.zeros(n), J, offset, {"graph": relabelled},
    )


def maxcut_from_edges(edges) -> Problem:
    """Max-Cut from an edge list: [(u, v)] or [(u, v, weight)]."""
    g = nx.Graph()
    for e in edges:
        g.add_edge(e[0], e[1], weight=float(e[2]) if len(e) > 2 else 1.0)
    return maxcut_problem(g)


def synthetic_costs(n: int, seed: int = 7) -> np.ndarray:
    """SYNTHETIC patient-to-bed cost table (integers 1..9). Not real hospital data."""
    return np.random.default_rng(seed).integers(1, 10, size=(n, n)).astype(float)


def assignment_problem(costs: np.ndarray, penalty: float | None = None) -> Problem:
    """Assign n patients to n beds at the lowest total cost, one bed per patient.

    One qubit per (patient, bed) pair, so n*n qubits. Qubit index = patient * n + bed.
    """
    costs = np.asarray(costs, dtype=float)
    n = costs.shape[0]
    if costs.shape != (n, n):
        raise ValueError("costs must be a square matrix (patients x beds)")
    P = float(penalty) if penalty is not None else 2.0 * float(costs.max())
    N = n * n
    Q = np.zeros((N, N))
    for p in range(n):
        for b in range(n):
            Q[p * n + b, p * n + b] = costs[p, b] - 2 * P     # each variable sits in two rules
    for p in range(n):                                        # one bed per patient
        for b1 in range(n):
            for b2 in range(b1 + 1, n):
                Q[p * n + b1, p * n + b2] += 2 * P
    for b in range(n):                                        # one patient per bed
        for p1 in range(n):
            for p2 in range(p1 + 1, n):
                Q[p1 * n + b, p2 * n + b] += 2 * P
    prob = qubo_to_problem(
        Q, "assignment", f"Assign {n} patients to {n} beds",
        f"Give each of {n} patients one of {n} beds at the lowest total cost.",
        {"costs": costs, "n": n, "penalty": P},
    )
    prob.offset += 2 * n * P
    return prob
