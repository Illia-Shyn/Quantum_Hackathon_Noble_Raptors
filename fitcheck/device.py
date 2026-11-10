"""Device access. The local copy costs no QPU time; the real device needs an IBM key."""
from __future__ import annotations

import os
import warnings

import numpy as np

# IBM's published figures, read from https://www.ibm.com/quantum/pricing on 2026-11-10.
PRICE_PER_MINUTE_USD = {"Pay-As-You-Go": 96.0, "Flex": 72.0, "Premium": 48.0}
OPEN_PLAN_SECONDS = 600.0            # Open Plan: up to 10 free minutes
PER_JOB_OVERHEAD_SECONDS = 2.0       # IBM "Workload usage" guide: about 2 s per sub-job


def local_backend(name: str = "fez"):
    """A local copy of an IBM device (default: ibm_fez, 156-qubit Heron r2). Uses no QPU time."""
    from qiskit_ibm_runtime import fake_provider

    cls = getattr(fake_provider, "Fake" + name.strip().replace("ibm_", "").capitalize(), None)
    if cls is None:
        raise ValueError(f"No local copy called {name!r}")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return cls()


def _secret(name: str):
    value = os.environ.get(name)
    if value:
        return value
    try:                                   # Google Colab Secrets (the key icon in the sidebar)
        from google.colab import userdata
        return userdata.get(name)
    except Exception:
        return None


def connect_service():
    """QiskitRuntimeService from QISKIT_IBM_TOKEN / QISKIT_IBM_INSTANCE (env vars or Colab
    Secrets). Falls back to an account saved on this machine if no token is set."""
    from qiskit_ibm_runtime import QiskitRuntimeService

    token, instance = _secret("QISKIT_IBM_TOKEN"), _secret("QISKIT_IBM_INSTANCE")
    if token:
        return QiskitRuntimeService(channel="ibm_quantum_platform", token=token, instance=instance)
    return QiskitRuntimeService()


def connect_ibm(min_qubits: int = 127, service=None):
    """The least busy real IBM device."""
    service = service or connect_service()
    return service.least_busy(operational=True, simulator=False, min_num_qubits=min_qubits)


def device_summary(backend) -> dict:
    """Median error rates and qubit count of a device, from its published calibration data."""
    target = backend.target
    two_q = next((g for g in ("cz", "ecr", "cx") if g in target.operation_names), None)

    def errors(gate):
        if gate is None or gate not in target.operation_names:
            return []
        return [p.error for p in target[gate].values() if p is not None and p.error is not None]

    def med(values):
        return float(np.median(values)) if len(values) else None

    return {
        "backend": backend.name,
        "num_qubits": int(backend.num_qubits),
        "two_qubit_gate": two_q,
        "median_two_qubit_error": med(errors(two_q)),
        "median_sx_error": med(errors("sx")),
        "median_readout_error": med(errors("measure")),
    }
