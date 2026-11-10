import itertools

import numpy as np
import pytest
from qiskit.quantum_info import Statevector

import fitcheck as fc
from fitcheck import hardware
from fitcheck.estimate import usable_target


@pytest.fixture(scope="module")
def backend():
    return fc.local_backend()


def test_maxcut_cost_equals_minus_cut():
    p = fc.maxcut_problem(fc.random_graph(8, 3, 1))
    rng = np.random.default_rng(0)
    for _ in range(30):
        bits = rng.integers(0, 2, 8)
        cut = sum(1 for u, v in p.meta["graph"].edges() if bits[u] != bits[v])
        assert p.cost(bits) == pytest.approx(-cut)


def test_assignment_qubo_matches_cost_table_and_hungarian():
    c = fc.synthetic_costs(3)
    p = fc.assignment_problem(c)
    for perm in itertools.permutations(range(3)):
        bits = np.zeros(9, int)
        for patient, bed in enumerate(perm):
            bits[patient * 3 + bed] = 1
        assert p.cost(bits) == pytest.approx(sum(c[i, b] for i, b in enumerate(perm)))
    assert fc.brute_force(p)["cost"] == pytest.approx(fc.solve_classically(p)["cost"])


def test_hamiltonian_matches_cost():
    p = fc.assignment_problem(fc.synthetic_costs(3))
    bits = [1, 0, 0, 0, 0, 1, 0, 1, 0]
    label = "".join(str(b) for b in reversed(bits))
    energy = Statevector.from_label(label).expectation_value(p.hamiltonian()).real + p.offset
    assert energy == pytest.approx(p.cost(bits))
    assert p.cost_of_bitstring(label) == pytest.approx(p.cost(bits))


def test_mirror_circuit_returns_zeros_without_noise():
    from qiskit.primitives import StatevectorSampler
    p = fc.maxcut_problem(fc.random_graph(6))
    m = fc.mirror_circuit(fc.bind_random(fc.qaoa_circuit(p, 2)))
    counts = StatevectorSampler(seed=1).run([m], shots=200).result()[0].data.meas.get_counts()
    assert counts == {"000000": 200}


def test_fit_check_verdicts(backend):
    small = fc.fit_check(fc.maxcut_problem(fc.random_graph(8)), backend)
    assert small.verdict == "worth a hardware test" and 0.5 < small.success < 1
    assert small.price["Pay-As-You-Go"] == pytest.approx(small.qpu_seconds / 60 * 96, abs=0.01)
    big = fc.fit_check(fc.maxcut_problem(fc.random_graph(100)), backend)
    assert big.verdict == "runs, but noise dominates"
    too_big = fc.fit_check(fc.assignment_problem(fc.synthetic_costs(13)), backend)
    assert too_big.verdict == "does not fit" and too_big.logical_qubits == 169
    assert "Verdict" in small.to_markdown() and "Verdict" in too_big.to_markdown()


def test_transpiler_avoids_dead_couplers(backend):
    target = usable_target(backend)
    assert all(p.error < 0.5 for p in target["cz"].values())
    isa = fc.transpile_for(backend, fc.bind_random(fc.qaoa_circuit(fc.maxcut_problem(fc.random_graph(30)), 1, True)))
    for inst in isa.data:
        if inst.operation.name == "cz":
            q = tuple(isa.find_bit(b).index for b in inst.qubits)
            assert backend.target["cz"][q].error < 0.5


def test_prediction_tracks_noisy_simulator(backend):
    rows = fc.simulator_sweep((4, 8), backend, shots=1000, seeds=(1,))
    for r in rows:
        assert abs(r["predicted_mean"] - r["simulated_mean"]) < 0.08


def test_qaoa_finds_maxcut_optimum():
    out = fc.solve_qaoa(fc.maxcut_problem(fc.random_graph(6)), reps=2)
    assert out["best_sampled_cost"] == pytest.approx(out["optimal_cost"])
    assert 0.6 < out["approximation_ratio"] <= 1.0


def test_hardware_flow_on_local_copy(backend):
    plan = hardware.run_experiment(backend, sizes=(4, 6), shots=200)
    assert set(plan["runs"]) == {"off", "on"} and set(plan["job_ids"]) == {"off", "on"}
    for row in plan["runs"]["off"]["rows"]:
        assert 0.4 < row["measured_success"] <= 1.0


def test_intake_without_key(monkeypatch, backend):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    spec, report = fc.check_request("Assign 3 nurses to 3 shifts", backend)
    assert spec["problem_type"] == "assignment" and report.logical_qubits == 9
    spec, report = fc.check_request("What is the ground state energy of this drug molecule?", backend)
    assert report.verdict == "not sized" and report.shape == "quantum-shaped"


def test_intake_survives_bad_key(backend):
    spec = fc.parse_request("split a network of 10 nodes", api_key="not-a-real-key")
    assert spec["problem_type"] == "maxcut" and spec["size"] == 10


def test_full_device_width_does_not_crash(backend):
    from fitcheck.estimate import usable_qubits
    usable = usable_qubits(backend)
    assert 100 < usable <= backend.num_qubits
    r = fc.fit_check(fc.maxcut_problem(fc.random_graph(backend.num_qubits)), backend)
    assert r.verdict in ("does not fit", "runs, but noise dominates")
    r = fc.fit_check(fc.maxcut_problem(fc.random_graph(usable)), backend)
    assert r.verdict == "runs, but noise dominates"
    r = fc.fit_check(fc.assignment_problem(fc.synthetic_costs(12)), backend)
    assert r.verdict in ("does not fit", "runs, but noise dominates")


def test_odd_and_tiny_sizes(backend):
    for n in (2, 3, 5, 7):
        assert fc.fit_check(fc.maxcut_problem(fc.random_graph(n)), backend).verdict
    assert fc.fit_check(fc.maxcut_from_edges([("a", "b"), ("b", "c", 2.5)]), backend).logical_qubits == 3


def test_what_would_need_to_improve(backend):
    ok = fc.fit_check(fc.maxcut_problem(fc.random_graph(8)), backend)
    assert ok.error_reduction_needed is None and ok.summary
    bad = fc.fit_check(fc.maxcut_problem(fc.random_graph(60)), backend)
    assert bad.error_reduction_needed > 1
    # scaling every error down by that factor should land on the threshold
    import math
    assert math.log(bad.success) / bad.error_reduction_needed == pytest.approx(math.log(0.10), rel=1e-6)
    assert "What would need to improve" in bad.to_markdown() and "plain words" in bad.to_markdown()
    huge = fc.fit_check(fc.assignment_problem(fc.synthetic_costs(12)), backend)
    assert huge.error_reduction_needed > 10 and "times" in huge.summary
