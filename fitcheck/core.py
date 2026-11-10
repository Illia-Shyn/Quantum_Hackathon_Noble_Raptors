"""The fit check itself: problem in, verdict out."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .circuits import bind_random, qaoa_circuit
from .classical import solve_classically
from .device import OPEN_PLAN_SECONDS, device_summary, local_backend
from .estimate import (circuit_metrics, price, qpu_seconds, success_estimate, transpile_for,
                       usable_qubits)
from .problems import Problem

OPTIMISATION_RUNS = 100   # circuit evaluations assumed for one full QAOA angle search
SUCCESS_THRESHOLD = 0.10   # our judgement: below 1 clean shot in 10, noise dominates

# Our documented judgement, one line per problem type. The tool does not compute this.
SHAPES = {
    "maxcut": ("open question",
               "Graph partitioning is hard for classical computers in the worst case, but no quantum "
               "advantage has been proven for QAOA on it, and good classical heuristics exist."),
    "assignment": ("classical-shaped",
                   "The assignment problem is solved exactly in polynomial time by the Hungarian "
                   "algorithm. Quantum cannot beat an already-efficient exact method here."),
    "qubo": ("open question",
             "General binary optimisation is hard in the worst case, but no proven quantum advantage "
             "exists for it; strong classical solvers are the baseline to beat."),
    "molecule_energy": ("quantum-shaped",
                        "Exact classical simulation of electrons doubles in cost with every orbital "
                        "added. This is the kind of problem quantum computers were proposed for, "
                        "strongest for strongly correlated molecules, but useful sizes need far more "
                        "qubits and far lower error rates than exist today."),
    "factoring": ("quantum-shaped",
                  "Shor's algorithm gives a proven speed-up, but breaking real keys needs millions "
                  "of error-corrected qubits. Today's devices cannot do it."),
    "search": ("classical-shaped",
               "Grover's algorithm gives only a square-root speed-up, which error-correction "
               "overhead is expected to cancel for practical sizes."),
    "other": ("classical-shaped",
              "No known quantum algorithm targets this kind of task. Data processing, web apps, "
              "machine-learning training and arithmetic belong on classical computers."),
}
SIZABLE = {"maxcut", "assignment", "qubo"}


def pct(x: float) -> str:
    return "under 0.01%" if x < 1e-4 else f"{x:.2%}"


@dataclass
class FitReport:
    problem_name: str
    problem_kind: str
    description: str
    shape: str
    shape_reason: str
    verdict: str
    reasons: list
    backend: str
    logical_qubits: int
    device_qubits: int
    reps: int
    shots: int
    metrics: dict = field(default_factory=dict)
    success: float | None = None
    success_by_gate: dict = field(default_factory=dict)
    qpu_seconds: float | None = None
    price: dict = field(default_factory=dict)
    full_run_seconds: float | None = None
    full_run_price: dict = field(default_factory=dict)
    error_reduction_needed: float | None = None   # how many times lower errors must be to pass
    summary: str = ""
    classical: dict = field(default_factory=dict)
    device: dict = field(default_factory=dict)
    compiled: object = field(default=None, repr=False, compare=False)   # the transpiled circuit, for visuals

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d.pop("compiled", None)
        d["classical"] = {k: v for k, v in self.classical.items() if k not in ("bits", "assignment")}
        return d

    def to_markdown(self) -> str:
        m, c = self.metrics, self.classical
        lines = [
            f"## Quantum Fit Check: {self.problem_name}",
            "",
            self.description,
            "",
            f"**Verdict: {self.verdict}**",
            "",
            *([f"**In plain words:** {self.summary}", ""] if self.summary else []),
            *[f"- {r}" for r in self.reasons],
            "",
            f"**Problem shape: {self.shape}.** {self.shape_reason}",
            "",
            "| Measure | Value |",
            "| --- | --- |",
            f"| Device | {self.backend} ({self.device_qubits} qubits) |",
            f"| Qubits needed | {self.logical_qubits} |",
        ]
        if m:
            lines += [
                f"| QAOA layers | {self.reps} |",
                f"| Circuit depth after transpiling | {m['depth']} |",
                f"| Two-qubit gates | {m['two_qubit_gates']} |",
                f"| Circuit duration | {m['duration_seconds'] * 1e6:.1f} microseconds |"
                if m.get("duration_seconds") is not None else "| Circuit duration | unknown |",
                f"| Estimated success chance per shot | {pct(self.success)} |",
                *([f"| What would need to improve | device errors about {self.error_reduction_needed:,.1f}x lower |"]
                  if self.error_reduction_needed else []),
                f"| Estimated QPU time ({self.shots} shots) | {self.qpu_seconds:.2f} s |",
                f"| Share of the 10 free minutes | {self.price['share_of_free_minutes']:.2%} |",
                f"| Price, Pay-As-You-Go | ${self.price['Pay-As-You-Go']:.2f} |",
                f"| Price, Flex | ${self.price['Flex']:.2f} |",
                f"| Price, Premium | ${self.price['Premium']:.2f} |",
                f"| Full QAOA search ({OPTIMISATION_RUNS} such jobs), QPU time | {self.full_run_seconds:.0f} s |",
                f"| Full QAOA search, Pay-As-You-Go | ${self.full_run_price['Pay-As-You-Go']:.2f} |",
                "| Full QAOA search, fits in the 10 free minutes? | "
                + ("yes" if self.full_run_seconds <= OPEN_PLAN_SECONDS else "no") + " |",
            ]
        if c.get("seconds") is not None:
            lines.append(f"| Classical solver | {c['method']} |")
            lines.append(f"| Classical solve time (measured) | {c['seconds'] * 1000:.3f} ms |")
        return "\n".join(lines)

    def _repr_markdown_(self) -> str:
        return self.to_markdown()


def shape_only_report(kind: str, description: str = "") -> FitReport:
    """For task types the tool cannot size into a circuit: the shape label and its reasoning."""
    kind = kind if kind in SHAPES else "other"
    shape, reason = SHAPES[kind]
    return FitReport(
        problem_name=kind.replace("_", " "), problem_kind=kind, description=description,
        shape=shape, shape_reason=reason, verdict="not sized",
        reasons=["This tool only builds circuits for graph and assignment problems, so it gives "
                 "the shape label without a circuit estimate."],
        backend="-", logical_qubits=0, device_qubits=0, reps=0, shots=0,
        summary=f"This kind of task is {shape}. {reason}",
    )


def fit_check(problem: Problem, backend=None, reps: int = 1, shots: int = 1000, seed: int = 7,
              run_classical: bool = True) -> FitReport:
    """Is this problem worth running on this device today? Uses no QPU time."""
    backend = backend or local_backend()
    shape, shape_reason = SHAPES.get(problem.kind, SHAPES["qubo"])
    classical = solve_classically(problem, seed) if run_classical else {}
    report = FitReport(
        problem_name=problem.name, problem_kind=problem.kind, description=problem.description,
        shape=shape, shape_reason=shape_reason, verdict="", reasons=[], backend=backend.name,
        logical_qubits=problem.num_qubits, device_qubits=int(backend.num_qubits), reps=reps,
        shots=shots, classical=classical, device=device_summary(backend),
    )
    usable = usable_qubits(backend)
    report.device["usable_connected_qubits"] = usable
    if problem.num_qubits > backend.num_qubits:
        report.verdict = "does not fit"
        report.reasons.append(f"Needs {problem.num_qubits} qubits; the device has {backend.num_qubits}.")
    elif problem.num_qubits > usable:
        report.verdict = "does not fit"
        report.reasons.append(f"Needs {problem.num_qubits} qubits; only {usable} of the device's "
                              f"{backend.num_qubits} are connected by working couplers in this calibration.")
    else:
        isa = transpile_for(backend, bind_random(qaoa_circuit(problem, reps, measure=True), seed), seed)
        report.compiled = isa
        report.metrics = circuit_metrics(backend, isa)
        est = success_estimate(backend, isa)
        report.success, report.success_by_gate = est["success"], est["success_by_gate"]
        if report.success < SUCCESS_THRESHOLD:
            # log(success) is close to -(sum of errors), so it scales with the error rates
            report.error_reduction_needed = est["log_success"] / math.log(SUCCESS_THRESHOLD)
        report.qpu_seconds = qpu_seconds(backend, report.metrics["duration_seconds"], shots)
        report.price = price(report.qpu_seconds)
        report.full_run_seconds = report.qpu_seconds * OPTIMISATION_RUNS
        report.full_run_price = price(report.full_run_seconds)
        if report.qpu_seconds > OPEN_PLAN_SECONDS:
            report.verdict = "does not fit"
            report.reasons.append(f"One run needs {report.qpu_seconds:.0f} s of QPU time, more than "
                                  f"the {OPEN_PLAN_SECONDS:.0f} s free budget.")
        elif report.success < SUCCESS_THRESHOLD:
            report.verdict = "runs, but noise dominates"
            report.reasons.append(f"Only {pct(report.success)} of shots are expected to finish "
                                  f"without an error (our threshold is {SUCCESS_THRESHOLD:.0%}).")
            report.reasons.append(f"What would need to improve: gate and readout errors about "
                                  f"{report.error_reduction_needed:,.1f} times lower than this device's, "
                                  "for this same circuit to pass the threshold.")
        else:
            report.verdict = "worth a hardware test"
            report.reasons.append(f"About {report.success:.0%} of shots are expected to finish without "
                                  "an error, so a hardware run would return a usable signal.")
        report.reasons.append(f"Fits on the device: {problem.num_qubits} of {backend.num_qubits} qubits, "
                              f"{report.metrics['two_qubit_gates']} two-qubit gates.")
    if classical.get("seconds") is not None:
        report.reasons.append(f"A classical computer solved this same problem in "
                              f"{classical['seconds'] * 1000:.3f} ms ({classical['method']}).")
    report.reasons.append("A 'worth a hardware test' verdict means the circuit can run cleanly enough "
                          "to measure. It never means quantum beats the classical solver."
                          if report.verdict == "worth a hardware test" else
                          "Nothing here suggests quantum beats the classical solver today.")
    report.summary = _plain_summary(report)
    return report


def _plain_summary(r: FitReport) -> str:
    classical = (f" A classical computer solves it in {r.classical['seconds'] * 1000:.3f} ms."
                 if r.classical.get("seconds") is not None else "")
    if r.verdict == "does not fit":
        text = "This problem is too big for the device, so it cannot be run at all today."
    elif r.verdict == "runs, but noise dominates":
        text = (f"The problem fits on the device, but the circuit is so long that errors would drown "
                f"the answer; the device would need to be about {r.error_reduction_needed:,.1f} times "
                "more accurate.")
    else:
        text = (f"The circuit is small enough that roughly {r.success:.0%} of runs would finish without "
                f"an error, for about ${r.price['Pay-As-You-Go']:.2f} per job, so it is a fair "
                "experiment, not a faster way to get the answer.")
    return text + classical
