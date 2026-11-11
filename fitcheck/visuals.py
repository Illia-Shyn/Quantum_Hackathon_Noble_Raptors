"""Interactive Plotly figures for the app (and any notebook). Import as `from fitcheck import visuals`.

Kept out of `fitcheck/__init__.py` so the core library does not need Plotly.
"""
from __future__ import annotations

import math

import networkx as nx
import numpy as np
import plotly.graph_objects as go
from qiskit import QuantumCircuit

from .device import OPEN_PLAN_SECONDS
from .estimate import BROKEN_GATE_ERROR

BLUE, ORANGE, GREEN, PURPLE = "#2a78d6", "#eb6834", "#1a9e75", "#7a5cd6"
GOOD, FAIR, POOR, IDLE = "#2e9e5b", "#e0b020", "#d64545", "#c9ced6"


def _base(fig: go.Figure, height: int = 420) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40, b=10), hovermode="closest",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    return fig


# ---------------------------------------------------------------- the problem

def problem_graph(problem, classical: dict | None = None) -> go.Figure:
    """Max-Cut network as dots and lines, coloured by the classical solver's best split."""
    g = problem.meta["graph"]
    pos = nx.spring_layout(g, seed=3)
    bits = (classical or {}).get("bits")
    ex, ey, cut_x, cut_y = [], [], [], []
    for u, v in g.edges():
        same = bits is None or bits[u] == bits[v]
        xs, ys = (ex, ey) if same else (cut_x, cut_y)
        xs += [pos[u][0], pos[v][0], None]
        ys += [pos[u][1], pos[v][1], None]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ex, y=ey, mode="lines", line=dict(color="#9aa3ad", width=1),
                             hoverinfo="skip", name="Link inside a group" if bits else "Link"))
    if cut_x:
        fig.add_trace(go.Scatter(x=cut_x, y=cut_y, mode="lines", line=dict(color=ORANGE, width=2, dash="dot"),
                                 hoverinfo="skip", name="Link that is cut"))
    nodes = sorted(g.nodes())
    colors = [BLUE if bits is None or bits[n] == 0 else ORANGE for n in nodes]
    fig.add_trace(go.Scatter(
        x=[pos[n][0] for n in nodes], y=[pos[n][1] for n in nodes], mode="markers+text" if len(nodes) <= 30 else "markers",
        text=[str(n) for n in nodes], textfont=dict(color="white", size=10),
        marker=dict(size=20 if len(nodes) <= 30 else 9, color=colors, line=dict(width=1, color="white")),
        hovertext=[f"Node {n}, {g.degree(n)} links" + ("" if bits is None else f", group {'A' if bits[n] == 0 else 'B'}")
                   for n in nodes], hoverinfo="text", name="Node", showlegend=False))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, scaleanchor="x")
    return _base(fig)


def assignment_table(problem, classical: dict | None = None) -> go.Figure:
    """Patient-by-bed cost table, with the classical best assignment outlined."""
    costs = np.asarray(problem.meta["costs"])
    n = costs.shape[0]
    patients = [f"Patient {i + 1}" for i in range(n)]
    beds = [f"Bed {j + 1}" for j in range(n)]
    fig = go.Figure(go.Heatmap(z=costs, x=beds, y=patients, colorscale="Blues", text=costs.astype(int),
                               texttemplate="%{text}", hovertemplate="%{y} to %{x}: cost %{z}<extra></extra>",
                               colorbar=dict(title="Cost")))
    chosen = (classical or {}).get("assignment")
    if chosen:
        fig.add_trace(go.Scatter(x=[beds[b] for b in chosen], y=patients, mode="markers",
                                 marker=dict(symbol="square-open", size=max(14, 260 // max(n, 1)), color=ORANGE,
                                             line=dict(width=3)),
                                 name="Best assignment (classical, exact)", hoverinfo="skip"))
    fig.update_yaxes(autorange="reversed")
    return _base(fig, height=max(320, 40 * n + 120))


def coupling_matrix(problem) -> go.Figure:
    """The Ising couplings J[i, j] as a heatmap: one row and column per qubit."""
    n = problem.num_qubits
    J = np.zeros((n, n))
    for (i, j), w in problem.quadratic.items():
        J[i, j] = J[j, i] = w
    np.fill_diagonal(J, problem.linear)
    lim = float(np.abs(J).max()) or 1.0
    fig = go.Figure(go.Heatmap(z=J, colorscale="RdBu", zmid=0, zmin=-lim, zmax=lim,
                               hovertemplate="qubit %{y}, qubit %{x}: %{z:.3g}<extra></extra>",
                               colorbar=dict(title="Weight")))
    fig.update_yaxes(autorange="reversed", title="Qubit")
    fig.update_xaxes(title="Qubit")
    fig.update_layout(title="Cost function: couplings off the diagonal, single-qubit weights on it")
    return _base(fig, height=460)


# ---------------------------------------------------------------- the circuit

def circuit_blocks(problem, reps: int) -> list[dict]:
    """The QAOA circuit in four plain-language blocks, with gate counts."""
    n = problem.num_qubits
    links = sum(1 for w in problem.quadratic.values() if w != 0)
    singles = sum(1 for w in problem.linear if w != 0)
    layers = f" per layer, {reps} layers" if reps > 1 else ""
    return [
        {"name": "1. Prepare", "gates": n,
         "text": f"{n} gates put every qubit into all its possible values at once."},
        {"name": "2. Problem", "gates": (links + singles) * reps,
         "text": f"{links} two-qubit links and {singles} single-qubit weights{layers} write the costs into the circuit."},
        {"name": "3. Mixer", "gates": n * reps,
         "text": f"{n} gates{layers} let the circuit move between candidate answers."},
        {"name": "4. Measure", "gates": n,
         "text": f"{n} readouts turn the qubits into one candidate answer per shot."},
    ]


def gate_durations(backend, isa: QuantumCircuit) -> go.Figure:
    """Total time spent in each gate type, from the device's published gate durations."""
    target = backend.target
    total: dict[str, float] = {}
    for inst in isa.data:
        name = inst.operation.name
        if name in ("barrier", "delay"):
            continue
        qargs = tuple(isa.find_bit(q).index for q in inst.qubits)
        try:
            d = target[name][qargs].duration or 0.0
        except Exception:
            d = 0.0
        total[name] = total.get(name, 0.0) + d
    names = sorted(total, key=total.get, reverse=True)
    fig = go.Figure(go.Bar(x=[total[k] * 1e6 for k in names], y=names, orientation="h", marker_color=BLUE,
                           hovertemplate="%{y}: %{x:.2f} microseconds in total<extra></extra>"))
    fig.update_layout(title="Time spent in each gate type, summed over all qubits (microseconds)")
    fig.update_yaxes(autorange="reversed")
    return _base(fig, height=280)


# ---------------------------------------------------------------- the chip

def chip_layout(backend) -> dict[int, tuple[float, float]]:
    """x, y for every qubit. Heron r2 (156 qubits): 8 rows of 16 joined by 4 bridge qubits;
    other devices fall back to a layout computed from the connection list."""
    n = int(backend.num_qubits)
    edges = {tuple(sorted(e)) for e in backend.coupling_map.get_edges()}
    nbrs: dict[int, set] = {q: set() for q in range(n)}
    for a, b in edges:
        nbrs[a].add(b)
        nbrs[b].add(a)
    if n == 156:
        pos = {}
        for q in range(n):
            row, k = divmod(q, 20)
            if k < 16:
                pos[q] = (float(k), -2.0 * row)
        for q in range(n):
            if q not in pos:
                above = min(nbrs[q])
                pos[q] = (pos[above][0], pos[above][1] - 1.0)
        return pos
    g = nx.Graph(list(edges))
    g.add_nodes_from(range(n))
    return {q: (float(x), float(y)) for q, (x, y) in nx.kamada_kawai_layout(g).items()}


def qubit_quality(backend) -> dict[int, dict]:
    """Readout error, T1 and T2 per qubit, from the device's published calibration."""
    target = backend.target
    out = {}
    for q in range(int(backend.num_qubits)):
        try:
            readout = target["measure"][(q,)].error
        except Exception:
            readout = None
        props = target.qubit_properties[q] if target.qubit_properties else None
        out[q] = {"readout": readout, "t1": getattr(props, "t1", None), "t2": getattr(props, "t2", None)}
    return out


def coupler_errors(backend) -> dict[tuple, float]:
    target = backend.target
    gate = next((g for g in ("cz", "ecr", "cx") if g in target.operation_names), None)
    out: dict[tuple, float] = {}
    if gate is None:
        return out
    for qargs, p in target[gate].items():
        if p is not None and p.error is not None:
            key = tuple(sorted(qargs))
            out[key] = min(out.get(key, 1.0), float(p.error))
    return out


def chip_map(backend, used: set[int] | None = None, layout: dict[int, int] | None = None,
             expert: bool = False) -> go.Figure:
    """The device as a map of dots. Qubits the circuit uses are lit and coloured by readout
    quality relative to the device's median. Expert view also colours every link by its
    two-qubit error, marks dead couplers, and shows which problem qubit sits where."""
    pos = chip_layout(backend)
    quality = qubit_quality(backend)
    links = coupler_errors(backend)
    used = used or set()
    physical_to_logical = {p: v for v, p in (layout or {}).items()}
    readouts = [v["readout"] for v in quality.values() if v["readout"] is not None]
    median = float(np.median(readouts)) if readouts else 0.0

    fig = go.Figure()
    # links: bucketed so a few traces carry all 176 lines
    buckets = {"ok": ([], []), "dead": ([], [])}
    if expert:
        good = sorted(e for e in links.values() if e < BROKEN_GATE_ERROR)
        cuts = np.quantile(good, [0.5, 0.9]) if good else [0, 0]
        buckets = {"low": ([], []), "mid": ([], []), "high": ([], []), "dead": ([], [])}
    mid_x, mid_y, mid_text = [], [], []
    for (a, b), err in links.items():
        if expert:
            key = ("dead" if err >= BROKEN_GATE_ERROR else "low" if err <= cuts[0]
                   else "mid" if err <= cuts[1] else "high")
        else:
            key = "dead" if err >= BROKEN_GATE_ERROR else "ok"
        xs, ys = buckets[key]
        xs += [pos[a][0], pos[b][0], None]
        ys += [pos[a][1], pos[b][1], None]
        mid_x.append((pos[a][0] + pos[b][0]) / 2)
        mid_y.append((pos[a][1] + pos[b][1]) / 2)
        mid_text.append(f"Link {a}-{b}: two-qubit error {err:.2%}" + (" (dead coupler)" if err >= BROKEN_GATE_ERROR else ""))
    styles = {"ok": ("#b8bfc8", 2, "solid", "Link"), "low": (GOOD, 3, "solid", "Link, error in best half"),
              "mid": (FAIR, 3, "solid", "Link, error in worse half"), "high": (POOR, 3, "solid", "Link, worst 10%"),
              "dead": (POOR, 2, "dot", "Dead coupler (never used)")}
    for key, (xs, ys) in buckets.items():
        if xs:
            color, width, dash, name = styles[key]
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=color, width=width, dash=dash),
                                     hoverinfo="skip", name=name))
    if expert:
        fig.add_trace(go.Scatter(x=mid_x, y=mid_y, mode="markers", marker=dict(size=6, opacity=0),
                                 hovertext=mid_text, hoverinfo="text", showlegend=False))

    def label(q):
        v = quality[q]
        parts = [f"Qubit {q}"]
        if q in physical_to_logical:
            parts.append(f"holds problem qubit {physical_to_logical[q]}")
        elif q in used:
            parts.append("used for routing")
        if v["readout"] is not None:
            parts.append(f"readout error {v['readout']:.2%}")
        if expert and v["t1"]:
            parts.append(f"T1 {v['t1'] * 1e6:.0f} us, T2 {v['t2'] * 1e6:.0f} us" if v["t2"] else f"T1 {v['t1'] * 1e6:.0f} us")
        return "<br>".join(parts)

    def grade(q):
        r = quality[q]["readout"]
        if r is None or median == 0:
            return FAIR
        return GOOD if r <= median else FAIR if r <= 2 * median else POOR

    idle = [q for q in pos if q not in used]
    fig.add_trace(go.Scatter(x=[pos[q][0] for q in idle], y=[pos[q][1] for q in idle], mode="markers",
                             marker=dict(size=9, color=IDLE), hovertext=[label(q) for q in idle], hoverinfo="text",
                             name="Not used"))
    for color, name in ((GOOD, "Used, readout at or better than typical"), (FAIR, "Used, up to 2x typical error"),
                        (POOR, "Used, over 2x typical error")):
        qs = [q for q in sorted(used) if grade(q) == color]
        if qs:
            text = [str(physical_to_logical[q]) if expert and q in physical_to_logical else "" for q in qs]
            fig.add_trace(go.Scatter(x=[pos[q][0] for q in qs], y=[pos[q][1] for q in qs],
                                     mode="markers+text" if expert else "markers", text=text,
                                     textfont=dict(size=8, color="white"),
                                     marker=dict(size=16, color=color, line=dict(width=1, color="#333")),
                                     hovertext=[label(q) for q in qs], hoverinfo="text", name=name))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, scaleanchor="x")
    return _base(fig, height=560)


def used_qubits(isa: QuantumCircuit) -> tuple[set[int], dict[int, int]]:
    """Physical qubits the compiled circuit touches, and problem qubit -> physical qubit."""
    used = {isa.find_bit(q).index for inst in isa.data if inst.operation.name not in ("barrier", "delay")
            for q in inst.qubits}
    layout = {}
    if isa.layout is not None:
        layout = dict(enumerate(isa.layout.initial_index_layout(filter_ancillas=True)))
    return used, layout


# ---------------------------------------------------------------- the estimates

def qpu_meter(seconds: float, title: str = "QPU seconds out of the 600 free") -> go.Figure:
    shown = min(seconds, OPEN_PLAN_SECONDS)
    fig = go.Figure(go.Indicator(
        mode="gauge", value=shown,
        gauge=dict(axis=dict(range=[0, OPEN_PLAN_SECONDS]), bar=dict(color=BLUE if seconds <= OPEN_PLAN_SECONDS else POOR),
                   steps=[dict(range=[0, shown], color="#dbe8f7")],
                   threshold=dict(line=dict(color=POOR, width=3), value=OPEN_PLAN_SECONDS)),
        domain=dict(x=[0, 1], y=[0.18, 1]),
        title=dict(text=title, font=dict(size=14))))
    over = "  (over the free budget)" if seconds > OPEN_PLAN_SECONDS else ""
    fig.add_annotation(x=0.5, y=0.02, xref="paper", yref="paper", showarrow=False,
                       text=f"<b>{seconds:,.1f} s</b>{over}", font=dict(size=22))
    fig = _base(fig, height=260)
    fig.update_layout(margin=dict(l=30, r=30, t=60, b=10))
    return fig


def error_by_gate(success_by_gate: dict) -> go.Figure:
    """Which gate types cost the most success: the chance that at least one of them fails."""
    items = sorted(((g, 1 - s) for g, s in success_by_gate.items()), key=lambda t: t[1], reverse=True)
    fig = go.Figure(go.Bar(x=[v for _, v in items], y=[g for g, _ in items], orientation="h", marker_color=ORANGE,
                           hovertemplate="%{y}: %{x:.1%} chance at least one fails<extra></extra>"))
    fig.update_xaxes(tickformat=".0%", title="Chance at least one gate of this type fails")
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(title="Where the errors come from")
    return _base(fig, height=280)


def seed_spread(rows: list[dict]) -> go.Figure:
    fig = go.Figure(go.Scatter(x=[r["seed"] for r in rows], y=[r["success"] for r in rows], mode="markers+lines",
                               marker=dict(size=10, color=BLUE),
                               customdata=[r["two_qubit_gates"] for r in rows],
                               hovertemplate="seed %{x}: success %{y:.2%}, %{customdata} two-qubit gates<extra></extra>"))
    fig.update_yaxes(tickformat=".1%", title="Estimated success")
    fig.update_xaxes(title="Transpiler seed", dtick=1)
    fig.update_layout(title="How the estimate moves across transpiler seeds")
    return _base(fig, height=300)


# ---------------------------------------------------------------- validation

def validation_chart(sim_rows: list[dict], hardware: dict | None = None) -> go.Figure:
    """Headline chart: predicted against measured success as the problem grows."""
    fig = go.Figure()
    x = [r["num_nodes"] for r in sim_rows]
    fig.add_trace(go.Scatter(x=x, y=[r["predicted_mean"] for r in sim_rows], name="Predicted (our formula)",
                             error_y=dict(array=[r["predicted_std"] for r in sim_rows]), mode="lines+markers",
                             marker=dict(color=BLUE, size=9), line=dict(color=BLUE),
                             hovertemplate="%{x} qubits: predicted %{y:.1%}<extra></extra>"))
    fig.add_trace(go.Scatter(x=x, y=[r["simulated_mean"] for r in sim_rows], name="Noisy simulator",
                             error_y=dict(array=[r["simulated_std"] for r in sim_rows]), mode="lines+markers",
                             marker=dict(color=ORANGE, size=9, symbol="square"), line=dict(color=ORANGE),
                             hovertemplate="%{x} qubits: simulated %{y:.1%}<extra></extra>"))
    if hardware and hardware.get("runs"):
        styles = {"off": ("triangle-up", GREEN, "Real device, mitigation off"),
                  "on": ("diamond", PURPLE, "Real device, mitigation on")}
        for key, (symbol, color, name) in styles.items():
            rows = hardware["runs"].get(key, {}).get("rows")
            if rows:
                fig.add_trace(go.Scatter(
                    x=[r["num_nodes"] for r in rows], y=[r["measured_success"] for r in rows], name=name,
                    error_y=dict(array=[r["measured_stderr"] for r in rows]), mode="lines+markers",
                    marker=dict(color=color, size=10, symbol=symbol), line=dict(color=color, dash="dash"),
                    customdata=[r["predicted_success"] for r in rows],
                    hovertemplate="%{x} qubits: measured %{y:.1%} (predicted that day %{customdata:.1%})<extra></extra>"))
    fig.update_xaxes(title="Problem size (graph nodes = qubits)", dtick=2)
    fig.update_yaxes(title="Success rate (all-zeros share of a mirror circuit)", range=[0, 1.02], tickformat=".0%")
    fig.update_layout(title="Predicted vs measured success")
    return _base(fig, height=460)


def fmt_seconds(s: float | None) -> str:
    if s is None:
        return "-"
    return f"{s * 1000:.3f} ms" if s < 1 else f"{s:.2f} s"


def fmt_money(v: float | None) -> str:
    return "-" if v is None or (isinstance(v, float) and math.isnan(v)) else f"${v:,.2f}"
