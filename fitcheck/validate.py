"""Test our own estimates: predicted success against success measured with mirror circuits."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from .circuits import bind_random, mirror_circuit, qaoa_circuit
from .device import local_backend
from .estimate import circuit_metrics, success_estimate, transpile_for
from .problems import maxcut_problem, random_graph


def mirror_case(backend, num_nodes: int, reps: int = 1, seed: int = 7):
    """One transpiled mirror circuit (Max-Cut QAOA on a random 3-regular graph) and its prediction."""
    problem = maxcut_problem(random_graph(num_nodes, 3, seed))
    isa = transpile_for(backend, mirror_circuit(bind_random(qaoa_circuit(problem, reps), seed)), seed)
    metrics = circuit_metrics(backend, isa)
    row = {
        "num_nodes": int(num_nodes), "reps": int(reps), "seed": int(seed),
        "depth": metrics["depth"], "two_qubit_gates": metrics["two_qubit_gates"],
        "duration_seconds": metrics["duration_seconds"],
        "predicted_success": success_estimate(backend, isa)["success"],
    }
    return isa, row


def zero_rate(counts: dict, num_bits: int | None = None) -> tuple[float, float]:
    """Share of shots that returned all zeros, with its binomial standard error."""
    shots = sum(counts.values())
    zeros = sum(v for k, v in counts.items() if set(k.replace(" ", "")) <= {"0"})
    p = zeros / shots
    return p, math.sqrt(max(p * (1 - p), 0.0) / shots)


def simulator_sweep(sizes=(4, 6, 8, 10, 12), backend=None, reps: int = 1, shots: int = 2000,
                    seeds=(1, 2, 3)) -> list[dict]:
    """Predicted vs simulated success on a noisy simulator built from the device's error rates.
    Each size is repeated over several random graphs; mean and standard deviation are reported."""
    from qiskit_aer import AerSimulator

    backend = backend or local_backend()
    sim = AerSimulator.from_backend(backend)
    rows = []
    for n in sizes:
        predicted, measured = [], []
        info = {}
        for seed in seeds:
            isa, info = mirror_case(backend, n, reps, seed)
            counts = sim.run(isa, shots=shots, seed_simulator=seed).result().get_counts()
            predicted.append(info["predicted_success"])
            measured.append(zero_rate(counts)[0])
        rows.append({
            "num_nodes": int(n), "reps": int(reps), "shots": int(shots), "repeats": len(seeds),
            "two_qubit_gates": info["two_qubit_gates"],
            "predicted_mean": float(np.mean(predicted)), "predicted_std": float(np.std(predicted)),
            "simulated_mean": float(np.mean(measured)), "simulated_std": float(np.std(measured)),
        })
    return rows


def save_json(data, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))
    return path


def load_json(path):
    return json.loads(Path(path).read_text())


def plot_validation(sim_rows: list[dict], hardware: dict | None = None, ax=None):
    """Headline chart: predicted against measured success as the problem grows."""
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=(7.5, 4.5))
    x = [r["num_nodes"] for r in sim_rows]
    ax.errorbar(x, [r["predicted_mean"] for r in sim_rows], yerr=[r["predicted_std"] for r in sim_rows],
                marker="o", capsize=3, color="#2a78d6", label="Predicted (our formula)")
    ax.errorbar(x, [r["simulated_mean"] for r in sim_rows], yerr=[r["simulated_std"] for r in sim_rows],
                marker="s", capsize=3, color="#eb6834", label="Noisy simulator")
    if hardware:
        styles = {"off": ("^", "#1a9e75", "Real device, mitigation off"),
                  "on": ("D", "#7a5cd6", "Real device, mitigation on")}
        for key, (marker, color, label) in styles.items():
            rows = hardware.get("runs", {}).get(key, {}).get("rows")
            if rows:
                ax.errorbar([r["num_nodes"] for r in rows], [r["measured_success"] for r in rows],
                            yerr=[r["measured_stderr"] for r in rows], marker=marker, capsize=3,
                            color=color, linestyle="--", label=label)
    ax.set_xlabel("Problem size (graph nodes = qubits)")
    ax.set_ylabel("Success rate (all-zeros share of a mirror circuit)")
    ax.set_title("Predicted vs measured success")
    ax.set_ylim(0, 1.02)
    ax.grid(alpha=0.3)
    ax.legend()
    return ax
