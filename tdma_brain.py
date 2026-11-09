#!/usr/bin/env python3
"""
TDMA Schedule Optimizer ("Network Brain")
=========================================
Distance-2 graph colouring for collision-free TDMA scheduling with spatial reuse.

Model
-----
* Radios are nodes of a networkx Graph; an edge exists if two radios are within
  `radio_range` metres (inclusive).
* Two radios may NOT share a slot if they are 1 hop apart (direct interference)
  or share a common neighbour (hidden terminal / 2-hop interference).
* That is exactly ordinary graph colouring of G^2 (the "conflict graph").
  Colour = time slot. Radios > 2 hops apart may reuse a slot (spatial reuse).

Pipeline
--------
1. Heuristic : DSATUR + randomised restarts + local search (fast, near-optimal)
2. Bounds    : max clique of G^2 is a proven lower bound on the frame length
3. Exact     : time-limited branch & bound proves optimality (small networks)
4. Verify    : independent geometric re-check straight from the coordinates
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import random
import re
import sys
import time

import networkx as nx

DEFAULT_RANGE_M = 500.0


class InputError(ValueError):
    """Raised for malformed coordinate input."""


# --------------------------------------------------------------------------- #
# Input handling
# --------------------------------------------------------------------------- #
def parse_coords(text: str) -> dict[str, tuple[float, float]]:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(f"Invalid JSON: {exc}") from exc
    if not isinstance(raw, dict) or not raw:
        raise InputError('Expected a non-empty JSON object {"Node_01": [x, y], ...}')
    coords = {}
    for name, xy in raw.items():
        ok = (isinstance(xy, (list, tuple)) and len(xy) == 2 and
              all(isinstance(v, (int, float)) and not isinstance(v, bool)
                  and math.isfinite(v) for v in xy))
        if not ok:
            raise InputError(f"{name}: expected [x, y] with finite numbers, got {xy!r}")
        coords[str(name)] = (float(xy[0]), float(xy[1]))
    return coords


def demo_coords() -> dict[str, tuple[float, float]]:
    """4x4 grid, 300 m spacing: Node_01=(0,0) ... Node_16=(900,900)."""
    return {f"Node_{i * 4 + j + 1:02d}": (j * 300.0, i * 300.0)
            for i in range(4) for j in range(4)}


def node_key(name: str):
    nums = re.findall(r"\d+", name)
    return (int(nums[-1]) if nums else 0, name)


def label(name: str) -> str:
    nums = re.findall(r"\d+", name)
    return nums[-1] if nums else name


# --------------------------------------------------------------------------- #
# Graph model
# --------------------------------------------------------------------------- #
def build_graph(coords, radio_range=DEFAULT_RANGE_M) -> nx.Graph:
    """Radios = nodes, link = within radio_range metres."""
    G = nx.Graph()
    G.add_nodes_from(coords)
    for a, b in itertools.combinations(coords, 2):
        if math.dist(coords[a], coords[b]) <= radio_range:
            G.add_edge(a, b)
    return G


def conflict_graph(G: nx.Graph) -> nx.Graph:
    """G^2: connect every pair that is 1 hop (direct) or 2 hops (hidden terminal) apart."""
    C = nx.Graph()
    C.add_nodes_from(G)
    for u, dists in nx.all_pairs_shortest_path_length(G, cutoff=2):
        for v, d in dists.items():
            if d in (1, 2):
                C.add_edge(u, v)
    return C


# --------------------------------------------------------------------------- #
# Colouring: heuristics
# --------------------------------------------------------------------------- #
def _compact(colour: dict) -> dict:
    """Renumber colours to 0..k-1 without gaps."""
    remap = {c: i for i, c in enumerate(sorted(set(colour.values())))}
    return {n: remap[c] for n, c in colour.items()}


def dsatur(C: nx.Graph, rng: random.Random) -> dict:
    """DSATUR: colour next the node whose neighbours already use the most distinct
    colours (ties: higher degree, then random). Gives each node the lowest free slot."""
    colour, sat = {}, {n: set() for n in C}
    while len(colour) < len(C):
        n = max((x for x in C if x not in colour),
                key=lambda x: (len(sat[x]), C.degree(x), rng.random()))
        c = 0
        while c in sat[n]:
            c += 1
        colour[n] = c
        for m in C[n]:
            sat[m].add(c)
    return colour


def reduce_top_colour(C: nx.Graph, colour: dict, rng: random.Random, tries: int = 50) -> dict:
    """Local search: repeatedly try to eliminate the highest slot by recolouring its
    members into lower slots (random order, several attempts)."""
    colour = dict(colour)
    while max(colour.values()) > 0:
        top = max(colour.values())
        for _ in range(tries):
            trial = dict(colour)
            victims = [n for n in trial if trial[n] == top]
            rng.shuffle(victims)
            for n in victims:
                used = {trial[m] for m in C[n]}
                free = [c for c in range(top) if c not in used]
                if not free:
                    break
                trial[n] = rng.choice(free)
            else:
                colour = trial
                break
        else:
            break  # could not remove the top slot
    return colour


def heuristic_colouring(C: nx.Graph, restarts: int = 300, seed: int = 42) -> dict:
    rng = random.Random(seed)
    best = None
    for _ in range(max(1, restarts)):
        cand = reduce_top_colour(C, dsatur(C, rng), rng)
        if best is None or max(cand.values()) < max(best.values()):
            best = cand
    return _compact(best)


# --------------------------------------------------------------------------- #
# Colouring: bounds and exact search
# --------------------------------------------------------------------------- #
def lower_bound(C: nx.Graph) -> int:
    """Nodes of a clique in G^2 pairwise conflict -> need distinct slots.
    (In particular a node plus all its radio neighbours is always such a clique.)"""
    return max(len(c) for c in nx.find_cliques(C))


class _Timeout(Exception):
    pass


def _k_colouring(C: nx.Graph, k: int, deadline: float):
    """Backtracking DSATUR-ordered search for a proper k-colouring (None if impossible).
    Symmetry breaking: a node may only open the next unused colour index."""
    colour: dict = {}
    sat = {n: {} for n in C}  # colour -> multiplicity among coloured neighbours

    def rec(used: int) -> bool:
        if time.monotonic() > deadline:
            raise _Timeout
        if len(colour) == len(C):
            return True
        n = max((x for x in C if x not in colour),
                key=lambda x: (len(sat[x]), C.degree(x)))
        for c in range(min(used + 1, k)):
            if c in sat[n]:
                continue
            colour[n] = c
            for m in C[n]:
                sat[m][c] = sat[m].get(c, 0) + 1
            if rec(max(used, c + 1)):
                return True
            for m in C[n]:
                sat[m][c] -= 1
                if not sat[m][c]:
                    del sat[m][c]
            del colour[n]
        return False

    return dict(colour) if rec(0) else None


def exact_improve(C: nx.Graph, start: dict, lb: int, time_limit: float):
    """Try to go below `start` one slot at a time. Returns (colouring, proven_optimal)."""
    best = dict(start)
    deadline = time.monotonic() + time_limit
    try:
        while max(best.values()) + 1 > lb:
            found = _k_colouring(C, max(best.values()), deadline)  # one slot fewer
            if found is None:
                return best, True       # k slots impossible -> best is optimal
            best = _compact(found)
        return best, True               # reached the lower bound
    except _Timeout:
        return best, False


# --------------------------------------------------------------------------- #
# Independent verification
# --------------------------------------------------------------------------- #
def verify(coords, radio_range, slots) -> list:
    """Re-check the schedule straight from raw geometry (does not reuse the graph code).
    Returns a list of violations: (node_a, node_b, reason)."""
    names = list(coords)
    nbr = {a: [b for b in names if b != a and math.dist(coords[a], coords[b]) <= radio_range]
           for a in names}
    bad = set()
    for a in names:
        for b in nbr[a]:                                  # distance-1
            if slots[a] == slots[b]:
                bad.add((*sorted((a, b)), "1-hop direct link"))
        for b, c in itertools.combinations(nbr[a], 2):    # distance-2 (hidden terminal at a)
            if slots[b] == slots[c]:
                bad.add((*sorted((b, c)), f"2-hop hidden terminal at {a}"))
    return sorted(bad)


# --------------------------------------------------------------------------- #
# Benchmark of heuristics
# --------------------------------------------------------------------------- #
def benchmark(C, restarts, seed, exact_limit) -> str:
    rows = []

    def timed(name, fn):
        t0 = time.perf_counter()
        col = fn()
        rows.append((name, max(col.values()) + 1, (time.perf_counter() - t0) * 1000))
        return col

    timed("Greedy, largest-degree-first", lambda: nx.greedy_color(C, "largest_first"))
    timed("DSATUR (networkx)", lambda: nx.greedy_color(C, "DSATUR"))
    timed("DSATUR (custom, single run)", lambda: dsatur(C, random.Random(seed)))
    h = timed(f"DSATUR + {restarts} restarts + local search",
              lambda: heuristic_colouring(C, restarts, seed))
    timed("Exact branch & bound (time-limited)", lambda: exact_improve(C, h, lower_bound(C), exact_limit)[0])
    w = max(len(r[0]) for r in rows)
    lines = ["HEURISTIC BENCHMARK", f"{'Strategy'.ljust(w)} | Slots | Time (ms)", "-" * (w + 20)]
    lines += [f"{n.ljust(w)} | {s:5d} | {t:9.2f}" for n, s, t in rows]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Reporting / plotting
# --------------------------------------------------------------------------- #
def report(coords, slots, radio_range, lb, proven) -> str:
    names = sorted(coords, key=node_key)
    n_slots = max(slots.values()) + 1
    n = len(names)
    per_slot = [sum(1 for v in slots.values() if v == s) for s in range(n_slots)]
    if proven:
        status = "PROVEN OPTIMAL"
    else:
        status = f"best found (lower bound {lb})"
    bar = "=" * 64
    out = [bar, " TDMA TOPOLOGY OPTIMIZATION REPORT", bar,
           f"Total Nodes Processed : {n}",
           f"Configured Radio Range : {radio_range} meters",
           f"Optimized Frame Length : {n_slots} unique timeslots (Lower is better)",
           f"Optimality : {status}; theoretical lower bound = {lb}",
           f"Spatial Reuse : {n / n_slots:.2f} nodes/slot on average, up to {max(per_slot)} concurrent; "
           f"{n_slots} slots vs {n} for one-node-per-slot / token passing "
           f"({n / n_slots:.2f}x capacity gain)",
           "-" * 64, "NODE -> SLOT ASSIGNMENTS:"]
    out += [f" {nm}: Slot {slots[nm]}" for nm in names]
    out += ["", "STRUCTURAL TDMA SCHEDULE MATRIX (Slot x Node Boolean Matrix):",
            "Slot \\ Node | " + " | ".join(label(nm) for nm in names),
            "-" * 89]
    for s in range(n_slots):
        out.append(f"Slot {s:02d}     | " + " | ".join("1" if slots[nm] == s else "0" for nm in names))
    out.append("-" * 89)
    return "\n".join(out)


def plot(G, coords, slots, radio_range, path="schedule.png", show=False):
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    pos = {n: coords[n] for n in G}
    k = max(slots.values()) + 1
    cmap = plt.get_cmap("tab20")
    fig, ax = plt.subplots(figsize=(8, 7))
    nx.draw_networkx_edges(G, pos, ax=ax, alpha=0.35)
    nx.draw_networkx_nodes(G, pos, ax=ax, node_size=900,
                           node_color=[cmap(slots[n] % 20) for n in G])
    nx.draw_networkx_labels(G, pos, ax=ax, font_size=7,
                            labels={n: f"{label(n)}\nS{slots[n]}" for n in G})
    ax.set_title(f"TDMA schedule: {k} slots (same colour = same slot, S = slot index)\n"
                 f"edges = links within {radio_range:g} m")
    ax.set_aspect("equal"); ax.grid(alpha=0.2); ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)")
    ax.tick_params(left=True, bottom=True, labelleft=True, labelbottom=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    print(f"Saved plot: {path}")
    if show:
        plt.show()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def solve(coords, radio_range=DEFAULT_RANGE_M, restarts=300, seed=42, exact_limit=5.0):
    """Full pipeline. Returns (graph, conflict_graph, slots, lower_bound, proven_optimal)."""
    G = build_graph(coords, radio_range)
    C = conflict_graph(G)
    lb = lower_bound(C)
    col = heuristic_colouring(C, restarts, seed)
    proven = max(col.values()) + 1 == lb
    if not proven and exact_limit > 0:
        col, proven = exact_improve(C, col, lb, exact_limit)
    return G, C, {n: col[n] for n in coords}, lb, proven


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="TDMA distance-2 schedule optimizer")
    p.add_argument("coords", nargs="?",
                   help='JSON string {"Node_01":[0.0,0.0],...}; omit to use the 4x4 demo grid')
    p.add_argument("--file", help="read the coordinates JSON from a file instead")
    p.add_argument("--range", type=float, default=DEFAULT_RANGE_M, help="radio range in metres")
    p.add_argument("--restarts", type=int, default=300, help="heuristic random restarts")
    p.add_argument("--seed", type=int, default=42, help="RNG seed (reproducible output)")
    p.add_argument("--exact-time", type=float, default=5.0,
                   help="seconds for the exact optimality search (0 disables)")
    p.add_argument("--benchmark", action="store_true", help="compare colouring strategies")
    p.add_argument("--json-out", help="write schedule JSON (input for emane_bridge.py)")
    p.add_argument("--plot", metavar="PNG", nargs="?", const="schedule.png",
                   help="save a topology plot (default schedule.png)")
    p.add_argument("--show", action="store_true", help="also open the plot window (WSLg)")
    a = p.parse_args(argv)

    try:
        if a.file:
            text = open(a.file, encoding="utf-8").read()
            coords = parse_coords(text)
        elif a.coords:
            coords = parse_coords(a.coords)
        else:
            coords = demo_coords()
        if a.range <= 0:
            raise InputError("--range must be positive")
    except (InputError, OSError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2

    G, C, slots, lb, proven = solve(coords, a.range, a.restarts, a.seed, a.exact_time)
    print(report(coords, slots, a.range, lb, proven))

    violations = verify(coords, a.range, slots)
    if violations:
        print("CONFLICTS FOUND:")
        for v in violations:
            print("  ", v)
        return 1
    print("Execution finalized cleanly. Schedule verified conflict-free.")

    if a.benchmark:
        print("\n" + benchmark(C, a.restarts, a.seed, max(a.exact_time, 1.0)))
    if a.json_out:
        with open(a.json_out, "w", encoding="utf-8") as fh:
            json.dump({"frame_length": max(slots.values()) + 1, "range": a.range,
                       "optimal": proven, "coords": coords, "slots": slots}, fh, indent=2)
        print(f"Saved schedule: {a.json_out}")
    if a.plot or a.show:
        plot(G, coords, slots, a.range, a.plot or "schedule.png", show=a.show)
    return 0


if __name__ == "__main__":
    sys.exit(main())
