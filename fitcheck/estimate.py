"""Transpile for a device and estimate success chance, QPU seconds and price. No QPU time is used."""
from __future__ import annotations

import inspect
import math

from qiskit import QuantumCircuit
from qiskit.transpiler import Target, generate_preset_pass_manager

from .device import OPEN_PLAN_SECONDS, PER_JOB_OVERHEAD_SECONDS, PRICE_PER_MINUTE_USD

_SKIP = {"barrier", "delay"}


BROKEN_GATE_ERROR = 0.5    # calibration data marks dead couplers with an error near 1.0
_TARGET_CACHE: dict = {}


def usable_target(backend) -> Target:
    """The device's target without gates whose reported error is 0.5 or more (dead couplers),
    so the transpiler never routes through them."""
    key = id(backend)
    if key not in _TARGET_CACHE:
        src = backend.target
        new = Target(num_qubits=src.num_qubits, dt=src.dt, qubit_properties=src.qubit_properties)
        for name in src.operation_names:
            op = src.operation_from_name(name)
            if inspect.isclass(op):                      # control-flow instructions
                new.add_instruction(op, name=name)
                continue
            props = {q: p for q, p in src[name].items()
                     if not (p is not None and p.error is not None and p.error >= BROKEN_GATE_ERROR)}
            new.add_instruction(op, props, name=name)
        _TARGET_CACHE[key] = new
    return _TARGET_CACHE[key]


def usable_qubits(backend) -> int:
    """Size of the largest group of qubits connected by working couplers."""
    cmap = usable_target(backend).build_coupling_map()
    if cmap is None:
        return int(backend.num_qubits)
    return max(len(component.physical_qubits) for component in cmap.connected_components())


def transpile_for(backend, circuit: QuantumCircuit, seed: int = 7, optimization_level: int | None = None,
                  tries: int | None = None):
    """Compile a circuit to the device's own gates and wiring. Several transpiler seeds are
    tried and the layout with the best estimated success is kept."""
    if optimization_level is None:
        optimization_level = 3 if circuit.num_qubits <= 40 else 1
    if tries is None:
        tries = 3 if circuit.num_qubits <= 40 else 1
    target = usable_target(backend)
    best, best_score = None, -1.0
    for k in range(max(1, tries)):
        pm = generate_preset_pass_manager(optimization_level=optimization_level, target=target,
                                          seed_transpiler=seed + k)
        isa = pm.run(circuit)
        score = success_estimate(backend, isa)["log_success"]
        if best is None or score > best_score:
            best, best_score = isa, score
    return best


def circuit_metrics(backend, isa: QuantumCircuit) -> dict:
    """Size of a transpiled circuit."""
    ops = {k: int(v) for k, v in isa.count_ops().items()}
    two_q = sum(1 for inst in isa.data if inst.operation.num_qubits == 2 and inst.operation.name not in _SKIP)
    active = {isa.find_bit(q).index for inst in isa.data if inst.operation.name not in _SKIP for q in inst.qubits}
    try:
        duration = float(isa.estimate_duration(backend.target, unit="s"))
    except Exception:
        duration = None
    return {
        "qubits_used": len(active),
        "depth": int(isa.depth(lambda inst: inst.operation.name not in _SKIP)),
        "two_qubit_depth": int(isa.depth(lambda inst: inst.operation.num_qubits == 2)),
        "two_qubit_gates": int(two_q),
        "gate_counts": ops,
        "duration_seconds": duration,
    }


def success_estimate(backend, isa: QuantumCircuit) -> dict:
    """Chance that no gate or readout error happens: the product of (1 - error) over every
    gate and measurement, using the device's published error rates. Idle decoherence and
    crosstalk are NOT included, so this is an optimistic estimate."""
    target = backend.target
    log_by_gate: dict[str, float] = {}
    missing = 0
    for inst in isa.data:
        name = inst.operation.name
        if name in _SKIP:
            continue
        qargs = tuple(isa.find_bit(q).index for q in inst.qubits)
        try:
            err = target[name][qargs].error
        except Exception:
            err = None
        if err is None:
            missing += 1
            continue
        err = min(max(float(err), 0.0), 0.999999)
        log_by_gate[name] = log_by_gate.get(name, 0.0) + math.log1p(-err)
    total = sum(log_by_gate.values())
    return {
        "success": math.exp(total),
        "log_success": total,
        "success_by_gate": {k: math.exp(v) for k, v in sorted(log_by_gate.items())},
        "gates_without_error_data": missing,
    }


def qpu_seconds(backend, duration_seconds: float | None, shots: int, num_circuits: int = 1) -> float:
    """IBM's own estimate: overhead + (rep_delay + circuit length) * executions."""
    rep_delay = getattr(backend, "default_rep_delay", None) or 250e-6
    return PER_JOB_OVERHEAD_SECONDS + (rep_delay + (duration_seconds or 0.0)) * shots * num_circuits


def price(seconds: float) -> dict:
    """What those QPU seconds cost on each IBM plan."""
    out = {plan: round(seconds / 60.0 * rate, 2) for plan, rate in PRICE_PER_MINUTE_USD.items()}
    out["Open (free)"] = 0.0 if seconds <= OPEN_PLAN_SECONDS else None
    out["share_of_free_minutes"] = seconds / OPEN_PLAN_SECONDS
    return out
