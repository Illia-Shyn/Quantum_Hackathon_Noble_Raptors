"""Quantum Fit Check: is this problem worth running on today's quantum computers?"""
from .circuits import bind_random, mirror_circuit, qaoa_circuit
from .classical import assignment_scaling, brute_force, solve_classically
from .core import SHAPES, FitReport, fit_check, shape_only_report
from .device import PRICE_PER_MINUTE_USD, connect_ibm, connect_service, device_summary, local_backend
from .estimate import circuit_metrics, price, qpu_seconds, success_estimate, transpile_for
from .hardware import collect_experiment, run_experiment, submit_experiment
from .intake import parse_request, spec_to_problem
from .problems import (Problem, assignment_problem, maxcut_from_edges, maxcut_problem,
                       qubo_to_problem, random_graph, synthetic_costs)
from .solve import solve_qaoa
from .validate import load_json, plot_validation, save_json, simulator_sweep

__version__ = "0.1.0"


def check_request(text: str, backend=None, reps: int = 1, shots: int = 1000, seed: int = 7):
    """Plain sentence in, (parsed request, FitReport) out."""
    spec = parse_request(text)
    problem = spec_to_problem(spec, seed)
    if problem is None:
        return spec, shape_only_report(spec["problem_type"], spec["understood"])
    return spec, fit_check(problem, backend, reps, shots, seed)
