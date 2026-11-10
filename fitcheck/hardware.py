"""Hardware run: mirror circuits on a real IBM device, error mitigation off and on.

The same functions run against the local device copy, so the whole flow can be rehearsed for free.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .estimate import qpu_seconds
from .validate import mirror_case, zero_rate


def prepare_batch(backend, sizes=(4, 6, 8, 10, 12, 14), reps: int = 1, seed: int = 7, shots: int = 1000):
    """Transpile the mirror circuits and record predictions BEFORE anything is submitted."""
    circuits, rows = [], []
    for n in sizes:
        isa, row = mirror_case(backend, n, reps, seed)
        circuits.append(isa)
        rows.append(row)
    longest = max((r["duration_seconds"] or 0.0) for r in rows)
    plan = {
        "backend": backend.name, "shots": int(shots), "sizes": [int(n) for n in sizes],
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "predicted_qpu_seconds_per_job": qpu_seconds(backend, longest, shots, len(circuits)),
        "predictions": rows,
    }
    return circuits, plan


def submit(backend, circuits, shots: int = 1000, mitigation: bool = False):
    """Submit one Sampler job. mitigation=True turns on dynamical decoupling and gate twirling."""
    from qiskit_ibm_runtime import SamplerV2

    sampler = SamplerV2(mode=backend)
    sampler.options.default_shots = shots
    if mitigation:
        sampler.options.dynamical_decoupling.enable = True
        sampler.options.dynamical_decoupling.sequence_type = "XpXm"
        sampler.options.twirling.enable_gates = True
    return sampler.run(circuits)


def collect(job, plan: dict) -> dict:
    """Wait for a job and turn its counts into measured success rates."""
    result = job.result()
    rows = []
    for k, prediction in enumerate(plan["predictions"]):
        counts = result[k].data.meas.get_counts()
        p, err = zero_rate(counts)
        rows.append({**prediction, "measured_success": p, "measured_stderr": err,
                     "shots": int(sum(counts.values()))})
    try:
        job_id = job.job_id()
    except Exception:
        job_id = None
    try:
        usage = float(job.usage())
    except Exception:
        usage = None
    return {"job_id": job_id, "qpu_seconds_used": usage,
            "collected_at": datetime.now(timezone.utc).isoformat(), "rows": rows}


def submit_experiment(backend, sizes=(4, 6, 8, 10, 12, 14), reps: int = 1, shots: int = 1000, seed: int = 7):
    """Submit both jobs back to back on the same device: mitigation off, then on.
    Returns (plan, jobs). Save the plan straight away: it holds the predictions and the job IDs."""
    circuits, plan = prepare_batch(backend, sizes, reps, seed, shots)
    jobs = {"off": submit(backend, circuits, shots, False), "on": submit(backend, circuits, shots, True)}
    plan["job_ids"] = {key: job.job_id() for key, job in jobs.items()}
    return plan, jobs


def collect_experiment(plan: dict, jobs: dict | None = None, service=None) -> dict:
    """Fetch results, from the job objects or later by job ID through `service`."""
    if jobs is None:
        if service is None:
            raise ValueError("Pass the jobs, or a QiskitRuntimeService to fetch them by ID")
        jobs = {key: service.job(job_id) for key, job_id in plan["job_ids"].items()}
    plan["runs"] = {key: collect(job, plan) for key, job in jobs.items()}
    return plan


def run_experiment(backend, sizes=(4, 6, 8, 10, 12, 14), reps: int = 1, shots: int = 1000, seed: int = 7) -> dict:
    """Submit and wait. Fine for the local device copy; on real hardware prefer the two steps above."""
    plan, jobs = submit_experiment(backend, sizes, reps, shots, seed)
    return collect_experiment(plan, jobs)
