#!/usr/bin/env python3
"""
TDMA topology optimizer and analyzer  (non-interactive)
=======================================================

Given N radios of coverage radius R, build many candidate topologies (chain, ring,
spider with k arms, star, binary / ternary trees, plus a searched free-form layout),
discard those that break the physical rules, schedule every survivor with a TDMA
slot assignment, and rank them.

Run it and answer the two questions it asks (nothing about n or r is hardcoded):

    python3 tdma_topology_optimizer.py
    Enter the total number of radios to configure: 85
    Enter the effective coverage radius of each radio (in meters): 800

Optional flags (model settings, search effort, ranking) are listed with --help; n and r are
always typed at the prompt.

Model (same as the Stage-2 planner)
-----------------------------------
* Radio 0 is the user's radio = gateway, placed at the origin.  Every other radio sends
  its own packet(s) once per frame towards the gateway along a routing tree (convergecast);
  relays also forward everything below them.
* Minimum spacing : no two radios closer than  MIN_SEP * min(range_i, range_j).
* Link length     : LINK_FRAC * min(range_i, range_j)   (the weaker radio sets the length).
* Interference    : radio k jams any receiver closer than  INTERF_MULT * range_k.
* Conflict graph  : the uplinks (i -> parent_i) of two radios cannot share a slot if they share
  an endpoint (half duplex / same receiver) or if either transmitter jams the other's receiver.
* Slots           : weighted greedy colouring, a radio needs one slot per packet it sends
  (its own plus everything it relays).  Frame length F = number of slots used.
* Latency         : lower bound = max_hops slots (perfectly pipelined),
                    upper bound = max_hops * F slots (conservative, as in the Stage-2 planner).
                    The schedule-aware figure is a single packet from the deepest radio, no queueing.
* Covered area    : area of the UNION of the disks of radius range_i around every radio (km^2).
* "total hops"    : sum over all radios of their hop count to the gateway (= transmissions per frame).

Outputs (in ./results/n<N>_r<R>/ by default)
---------------------------------
    <tag>_summary.md / .json      ranked table + best-per-goal
    <tag>_best.png / _layout.csv / .json      best layout under --rank (picture, coordinates, slot table)
    <tag>_best_<goal>.*           same, for every other goal whose winner is a different topology
    <tag>_comparison.png          small multiples of all feasible topologies
"""
import argparse
import csv
import json
import math
import sys
import time
from bisect import bisect_left
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle  # noqa: E402

# =============================================================================================
# Top-level inputs (override with command-line flags)
# =============================================================================================
# n (number of radios) and r (coverage radius) are NOT set here: they are asked at runtime.
MIN_SEP = 0.5           # min spacing, as a fraction of the smaller range of the two radios
LINK_FRAC = 0.9         # link length, as a fraction of the weaker radio's range
INTERF_MULT = 1.5       # interference range, as a multiple of the transmitter's own range
LOAD = 1                # packets each radio generates per frame
MIN_REACH = 0.0         # only topologies reaching at least this far (m) count as feasible
RANK_BY = "area_per_slot"   # area_per_slot | frame | latency | reach | area
SEARCH_STEPS = 2000     # free-form layout search proposals (0 = presets only)
SEED = 1
MAX_SPIDER_ARMS = 12    # try spiders with 2..this many arms (star is always tried)
OUTDIR = "results"

GOALS = ("area_per_slot", "frame", "latency", "reach", "area")
GOAL_LABEL = {
    "area_per_slot": "best area per slot",
    "frame": "shortest frame",
    "latency": "lowest latency (hops x frame)",
    "reach": "farthest reach",
    "area": "largest covered area",
}


# =============================================================================================
# Data classes
# =============================================================================================
@dataclass
class Cfg:
    R: np.ndarray
    sep: float
    link_frac: float
    interf: float
    load: int
    min_reach: float
    rank: str

    @property
    def n(self):
        return len(self.R)

    def link(self, i, j):
        return self.link_frac * min(self.R[i], self.R[j])


@dataclass
class Layout:
    name: str
    family: str
    pos: np.ndarray            # (n, 2) metres, radio 0 at origin
    parent: np.ndarray         # (n,) routing-tree parent, -1 for the gateway
    extra: list = field(default_factory=list)   # physical links not used for routing (drawn dashed)
    note: str = ""


@dataclass
class Result:
    layout: Layout
    m: dict                    # metrics
    masks: list                # per radio (index 0 = gateway, mask 0) slot bitmask
    best_for: list = field(default_factory=list)


# =============================================================================================
# Geometry builders
# =============================================================================================
def build_spider(cfg, arms, name, family):
    """arms=1 is the chain; arms=n-1 is the star.  Radios are dealt round-robin to the arms."""
    n = cfg.n
    pos = np.zeros((n, 2))
    parent = np.full(n, -1)
    for k in range(1, n):
        arm, depth = (k - 1) % arms, (k - 1) // arms
        p = 0 if depth == 0 else k - arms
        th = 2 * math.pi * arm / arms
        pos[k] = pos[p] + cfg.link(k, p) * np.array([math.cos(th), math.sin(th)])
        parent[k] = p
    return Layout(name, family, pos, parent)


def build_ring(cfg):
    """Cycle of n radios on a circle; every chord = link length (circle radius solved so it closes)."""
    n = cfg.n
    if n < 3:
        return None
    c = np.array([cfg.link(j, (j + 1) % n) for j in range(n)])

    def total(rho):
        return float(np.sum(2 * np.arcsin(np.minimum(1.0, c / (2 * rho)))))

    lo = c.max() / 2
    if total(lo) < 2 * math.pi - 1e-9:
        return None
    hi = lo * 4
    while total(hi) > 2 * math.pi:
        hi *= 2
    for _ in range(200):
        mid = (lo + hi) / 2
        if total(mid) > 2 * math.pi:
            lo = mid
        else:
            hi = mid
    rho = (lo + hi) / 2
    ang = np.concatenate([[0.0], np.cumsum(2 * np.arcsin(c / (2 * rho)))[:-1]])
    pos = rho * np.stack([np.cos(ang), np.sin(ang)], axis=1)
    pos -= pos[0]
    parent = np.full(n, -1)
    for k in range(1, n):
        parent[k] = k - 1 if k <= n // 2 else (k + 1) % n      # shortest way round
    return Layout("ring (cycle)", "ring", pos, parent, extra=ring_unused_edges(parent, n))


def ring_unused_edges(parent, n):
    out = []
    for j in range(n):
        k = (j + 1) % n
        if parent[k] != j and parent[j] != k:
            out.append((j, k))
    return out


def build_tree(cfg, b, kind, param, name, family):
    """Complete b-ary tree (heap order), laid out in the plane.
       kind='heading': each child turns by +-param radians off its parent's heading.
       kind='sector' : the root owns an angular span `param`, split between subtrees by size."""
    n = cfg.n
    if n < 3:
        return None
    parent = np.array([-1] + [(k - 1) // b for k in range(1, n)])
    kids = [[] for _ in range(n)]
    for k in range(1, n):
        kids[parent[k]].append(k)
    pos = np.zeros((n, 2))
    if kind == "heading":
        head = np.zeros(n)
        for k in range(1, n):
            p = parent[k]
            j = kids[p].index(k)
            if p == 0:
                head[k] = 2 * math.pi * j / len(kids[0])
            else:
                head[k] = head[p] + (j - (len(kids[p]) - 1) / 2) * param
            pos[k] = pos[p] + cfg.link(k, p) * np.array([math.cos(head[k]), math.sin(head[k])])
    else:
        size = np.ones(n)
        for k in range(n - 1, 0, -1):
            size[parent[k]] += size[k]
        lo, hi, rad = np.zeros(n), np.zeros(n), np.zeros(n)
        lo[0], hi[0] = -param / 2, param / 2
        for p in range(n):
            if not kids[p]:
                continue
            tot = sum(size[c] for c in kids[p])
            a = lo[p]
            for c in kids[p]:
                w = (hi[p] - lo[p]) * size[c] / tot
                lo[c], hi[c] = a, a + w
                a += w
                mid = (lo[c] + hi[c]) / 2
                L = cfg.link(c, p)
                rad[c] = rad[p] + L
                ideal = rad[c] * np.array([math.cos(mid), math.sin(mid)])   # ideal radial spot
                d = ideal - pos[p]                                           # step towards it, exact link length
                d = d / np.linalg.norm(d) if np.linalg.norm(d) > 1e-9 else np.array([math.cos(mid), math.sin(mid)])
                pos[c] = pos[p] + L * d
    return Layout(name, family, pos, parent, note=f"{kind} {math.degrees(param):.0f} deg")


def preset_layouts(cfg, max_arms):
    n = cfg.n
    out = [build_spider(cfg, 1, "chain (path)", "chain")]
    r = build_ring(cfg)
    if r is not None:
        out.append(r)
    for a in range(2, min(max_arms, n - 2) + 1):
        out.append(build_spider(cfg, a, f"spider, {a} arms", f"spider{a}"))
    if n >= 3:
        out.append(build_spider(cfg, n - 1, "star", "star"))
    for b, nm in ((2, "binary tree"), (3, "ternary tree")):
        for deg in (30, 45, 60, 90):
            out.append(build_tree(cfg, b, "heading", math.radians(deg), nm, nm))
        for span in (360, 270, 180, 120):
            out.append(build_tree(cfg, b, "sector", math.radians(span), nm, nm))
    return [x for x in out if x is not None]


# =============================================================================================
# Feasibility rules
# =============================================================================================
def pairwise(pos):
    return np.linalg.norm(pos[:, None] - pos[None], axis=2)


def validate(layout, cfg):
    """Return (ok, reason).  Checks the minimum-spacing rule and that every link is within range."""
    n = cfg.n
    D = pairwise(layout.pos)
    minR = np.minimum.outer(cfg.R, cfg.R)
    need = cfg.sep * minR
    bad = (D < need - 1e-6) & ~np.eye(n, dtype=bool)
    if bad.any():
        i, j = np.unravel_index(np.argmax(np.where(bad, need - D, -1)), D.shape)
        return False, f"min-spacing violated (radios {min(i, j)}-{max(i, j)}: {D[i, j]:.0f} m < {need[i, j]:.0f} m)"
    for k in range(1, n):
        p = layout.parent[k]
        if D[k, p] > minR[k, p] * (1 + 1e-9):
            return False, f"link {k}-{p} longer than the weaker radio's range"
    return True, ""


# =============================================================================================
# Scheduling
# =============================================================================================
def tree_stats(parent):
    n = len(parent)
    kids = [[] for _ in range(n)]
    for k in range(1, n):
        kids[parent[k]].append(k)
    order, depth = [0], np.zeros(n, int)
    for u in order:
        for c in kids[u]:
            depth[c] = depth[u] + 1
            order.append(c)
    size = np.ones(n, int)
    for u in reversed(order):
        if parent[u] >= 0:
            size[parent[u]] += size[u]
    return kids, depth, size


def conflict_matrix(D, parent, ri):
    """Conflicts between uplinks of radios 1..n-1 (row a  <->  radio a+1)."""
    idx = np.arange(1, len(parent))
    p = parent[idx]
    jam = D[np.ix_(idx, p)] <= ri[idx][:, None]       # jam[b, a]: tx b hits the receiver of link a
    C = jam | jam.T
    C |= (p[:, None] == p[None, :]) | (p[:, None] == idx[None, :]) | (idx[:, None] == p[None, :])
    np.fill_diagonal(C, False)
    return C


def greedy_schedule(C, demand):
    """Heaviest radio first; each takes its `demand` lowest slots that no conflicting radio uses."""
    m = len(demand)
    order = sorted(range(m), key=lambda a: (-demand[a], a))
    nbr = [np.flatnonzero(C[a]) for a in range(m)]
    masks = [0] * m
    for a in order:
        used = 0
        for b in nbr[a]:
            used |= masks[b]
        tmp, mm = used, 0
        for _ in range(int(demand[a])):
            low = ~tmp & (tmp + 1)
            mm |= low
            tmp |= low
        masks[a] = mm
    for a in range(m):                                # safety net: schedule must be conflict-free
        for b in nbr[a]:
            assert not (masks[a] & masks[b]), "internal error: conflicting slots"
    return masks, max(x.bit_length() for x in masks)


def mask_to_list(mm):
    out = []
    while mm:
        low = mm & -mm
        out.append(low.bit_length() - 1)
        mm ^= low
    return out


def ranges_str(lst):
    if not lst:
        return ""
    parts, s, prev = [], lst[0], lst[0]
    for x in lst[1:] + [None]:
        if x is not None and x == prev + 1:
            prev = x
            continue
        parts.append(str(s) if s == prev else f"{s}-{prev}")
        if x is not None:
            s = prev = x
    return ";".join(parts)


def schedule_latency(parent, masks, F, depth, dist):
    """Worst case (over packet arrival time) for ONE packet from the deepest radio, no queueing."""
    cand = np.flatnonzero(depth == depth.max())
    v = int(cand[np.argmax(dist[cand])])
    path = []
    while v != 0:
        path.append(mask_to_list(masks[v]))
        v = parent[v]
    worst = 0
    for t0 in range(F):
        cur = t0
        for lst in path:
            base = (cur // F) * F
            k = bisect_left(lst, cur - base)
            cur = (base + lst[k] if k < len(lst) else base + F + lst[0]) + 1
        worst = max(worst, cur - t0)
    return worst


# =============================================================================================
# Covered area (union of disks, raster)
# =============================================================================================
def covered_area_km2(pos, R, div=30, cap=3e6):
    xmin, xmax = (pos[:, 0] - R).min(), (pos[:, 0] + R).max()
    ymin, ymax = (pos[:, 1] - R).min(), (pos[:, 1] + R).max()
    w, hgt = xmax - xmin, ymax - ymin
    h = max(R.min() / div, math.sqrt(w * hgt / cap))
    nx, ny = int(math.ceil(w / h)) + 1, int(math.ceil(hgt / h)) + 1
    xs = xmin + (np.arange(nx) + 0.5) * h
    ys = ymin + (np.arange(ny) + 0.5) * h
    grid = np.zeros((ny, nx), bool)
    for (cx, cy), rad in zip(pos, R):
        i0, i1 = max(0, int((cx - rad - xmin) / h)), min(nx, int((cx + rad - xmin) / h) + 2)
        j0, j1 = max(0, int((cy - rad - ymin) / h)), min(ny, int((cy + rad - ymin) / h) + 2)
        X, Y = xs[i0:i1][None, :], ys[j0:j1][:, None]
        grid[j0:j1, i0:i1] |= (X - cx) ** 2 + (Y - cy) ** 2 <= rad * rad
    return grid.sum() * h * h / 1e6


# =============================================================================================
# Evaluation
# =============================================================================================
def evaluate(pos, parent, cfg, full=True):
    n = cfg.n
    D = pairwise(pos)
    _, depth, size = tree_stats(parent)
    demand = cfg.load * size[1:]
    C = conflict_matrix(D, parent, cfg.interf * cfg.R)
    masks_i, F = greedy_schedule(C, demand)
    masks = [0] + masks_i
    reach = float(D[0].max())
    max_hops = int(depth.max())
    area = covered_area_km2(pos, cfg.R, *((30, 3e6) if full else (8, 3e5)))
    m = dict(
        frame=int(F), reach=reach, max_hops=max_hops, total_hops=int(depth.sum()),
        lat_min=max_hops, lat_max=max_hops * int(F),
        area=area, area_per_slot=area / F,
        reach_with_range=float((D[0] + cfg.R).max()),
        frame_floor=int(cfg.load * (n - 1)),
    )
    if full:
        m["lat_sched"] = schedule_latency(parent, masks, F, depth, D[0])
    return m, masks


def goal_value(m, goal):
    return {"area_per_slot": m["area_per_slot"], "frame": -m["frame"], "latency": -m["lat_max"],
            "reach": m["reach"], "area": m["area"]}[goal]


def sort_key(res, goal):
    return (-round(goal_value(res.m, goal), 9), res.m["frame"], -res.m["reach"],
            res.layout.family == "custom", res.layout.name)


# =============================================================================================
# Free-form layout search (simulated annealing on tree + positions)
# =============================================================================================
def search_layout(start, cfg, goal, steps, rng):
    n = cfg.n
    pos, parent = start.pos.copy(), start.parent.copy()
    m0, _ = evaluate(pos, parent, cfg, full=False)
    cur = goal_value(m0, goal)
    best_pos, best_par, best_val = pos.copy(), parent.copy(), cur
    minR = np.minimum.outer(cfg.R, cfg.R)
    T0, T1 = 0.02, 0.0005
    done = tries = 0
    while done < steps and tries < steps * 40:
        tries += 1
        v = int(rng.integers(1, n))
        kids, _, _ = tree_stats(parent)
        sub, stack = [], [v]
        while stack:
            u = stack.pop()
            sub.append(u)
            stack.extend(kids[u])
        insub = np.zeros(n, bool)
        insub[sub] = True
        rest = np.flatnonzero(~insub)
        p = int(rng.choice(rest))
        phi, delta = rng.uniform(0, 2 * math.pi), (rng.uniform(0, 2 * math.pi) if len(sub) > 1 else 0.0)
        target = pos[p] + cfg.link(v, p) * np.array([math.cos(phi), math.sin(phi)])
        rot = np.array([[math.cos(delta), -math.sin(delta)], [math.sin(delta), math.cos(delta)]])
        new_sub = target + (pos[sub] - pos[v]) @ rot.T
        dd = np.linalg.norm(new_sub[:, None] - pos[rest][None], axis=2)
        if (dd < cfg.sep * minR[np.ix_(sub, rest)] - 1e-6).any():
            continue                                   # breaks the minimum-spacing rule
        npos, npar = pos.copy(), parent.copy()
        npos[sub] = new_sub
        npar[v] = p
        m, _ = evaluate(npos, npar, cfg, full=False)
        val = goal_value(m, goal)
        T = T0 * (T1 / T0) ** (done / max(1, steps))
        rel = (val - cur) / max(abs(cur), 1e-9)
        if rel >= 0 or rng.random() < math.exp(rel / T):
            pos, parent, cur = npos, npar, val
            if cur > best_val:
                best_pos, best_par, best_val = pos.copy(), parent.copy(), cur
        done += 1
    return Layout("custom (searched layout)", "custom", best_pos - best_pos[0], best_par,
                  note=f"annealed from '{start.name}', {done} proposals")


# =============================================================================================
# Reporting
# =============================================================================================
def fmt_table(rows, cfg):
    hdr = ("#", "topology", "frame", "reach (m)", "hops max/total", "latency bound (slots)",
           "area (km2)", "km2/slot", "best at")
    body = []
    for i, r in enumerate(rows, 1):
        m = r.m
        body.append((str(i), r.layout.name, str(m["frame"]), f"{m['reach']:.0f}",
                     f"{m['max_hops']}/{m['total_hops']}", f"{m['lat_min']} - {m['lat_max']}",
                     f"{m['area']:.2f}", f"{m['area_per_slot']:.4f}", ", ".join(r.best_for)))
    w = [max(len(h), *(len(b[k]) for b in body)) for k, h in enumerate(hdr)]
    line = lambda cells: " | ".join(c.ljust(w[k]) if k in (1, 8) else c.rjust(w[k]) for k, c in enumerate(cells))
    sep = "-+-".join("-" * x for x in w)
    return "\n".join([line(hdr), sep] + [line(b) for b in body])


def save_csv(res, cfg, path):
    n = cfg.n
    D = pairwise(res.layout.pos)
    _, depth, size = tree_stats(res.layout.parent)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["radio", "range_m", "x_m", "y_m", "parent", "hops", "link_len_m", "demand_slots", "slots"])
        for i in range(n):
            p = int(res.layout.parent[i])
            w.writerow([i, f"{cfg.R[i]:.1f}", f"{res.layout.pos[i, 0]:.2f}", f"{res.layout.pos[i, 1]:.2f}",
                        p, int(depth[i]), f"{D[i, p]:.2f}" if p >= 0 else "",
                        cfg.load * int(size[i]) if i else "", ranges_str(mask_to_list(res.masks[i]))])


def result_dict(res, cfg):
    return dict(name=res.layout.name, family=res.layout.family, note=res.layout.note,
                metrics=res.m, best_for=res.best_for,
                radios=[dict(radio=i, range_m=float(cfg.R[i]), x=float(res.layout.pos[i, 0]),
                             y=float(res.layout.pos[i, 1]), parent=int(res.layout.parent[i]),
                             slots=ranges_str(mask_to_list(res.masks[i]))) for i in range(cfg.n)])


def plot_best(res, cfg, path, title_extra=""):
    lay, m, n = res.layout, res.m, cfg.n
    pos, parent = lay.pos, lay.parent
    _, depth, size = tree_stats(parent)
    fig = plt.figure(figsize=(12, 9))
    gs = fig.add_gridspec(2, 1, height_ratios=[3, 2])
    ax = fig.add_subplot(gs[0])
    if n <= 200:
        for (x, y), rad in zip(pos, cfg.R):
            ax.add_patch(Circle((x, y), rad, color="tab:blue", alpha=0.05, lw=0))
    for i, j in lay.extra:
        ax.plot(pos[[i, j], 0], pos[[i, j], 1], "--", color="grey", lw=0.8)
    smax = size[1:].max()
    for k in range(1, n):
        p = parent[k]
        ax.plot(pos[[k, p], 0], pos[[k, p], 1], "-", color="0.25", lw=0.6 + 2.4 * size[k] / smax)
    sc = ax.scatter(pos[1:, 0], pos[1:, 1], c=depth[1:], cmap="viridis", s=28, zorder=3)
    ax.scatter(*pos[0], marker="*", s=260, c="red", zorder=4, label="gateway (user radio)")
    if n <= 40:
        for i in range(n):
            ax.annotate(str(i), pos[i], fontsize=7, xytext=(3, 3), textcoords="offset points")
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    fig.colorbar(sc, ax=ax, label="hops to gateway", fraction=0.03, pad=0.01)
    ax.legend(loc="upper right")
    ax.set_title(f"{lay.name}{title_extra}  -  frame {m['frame']} slots, reach {m['reach']:.0f} m, "
                 f"max {m['max_hops']} hops, area {m['area']:.2f} km2 ({m['area_per_slot']:.4f} km2/slot)\n"
                 f"latency bound {m['lat_min']} - {m['lat_max']} slots; link width ~ traffic carried",
                 fontsize=10)
    ax2 = fig.add_subplot(gs[1])
    F = m["frame"]
    M = np.zeros((n - 1, F))
    for i in range(1, n):
        for s in mask_to_list(res.masks[i]):
            M[i - 1, s] = 1
    ax2.imshow(M, aspect="auto", cmap="Blues", interpolation="nearest", origin="lower")
    ax2.set_xlabel("slot in frame")
    ax2.set_ylabel("transmitting radio")
    ax2.set_yticks(np.linspace(0, n - 2, min(n - 1, 8)).astype(int))
    ax2.set_yticklabels((np.linspace(0, n - 2, min(n - 1, 8)).astype(int) + 1).astype(str))
    ax2.set_title("TDMA frame: dark cell = radio transmits in that slot (spatial reuse = several per column)",
                  fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_comparison(rows, cfg, path):
    k = len(rows)
    cols = min(4, k)
    nr = math.ceil(k / cols)
    fig, axs = plt.subplots(nr, cols, figsize=(4.2 * cols, 3.6 * nr), squeeze=False)
    for ax in axs.ravel():
        ax.axis("off")
    for ax, r in zip(axs.ravel(), rows):
        ax.axis("on")
        pos, par = r.layout.pos, r.layout.parent
        for a, b in r.layout.extra:
            ax.plot(pos[[a, b], 0], pos[[a, b], 1], "--", color="grey", lw=0.5)
        for q in range(1, cfg.n):
            ax.plot(pos[[q, par[q]], 0], pos[[q, par[q]], 1], "-", color="0.3", lw=0.6)
        ax.scatter(pos[:, 0], pos[:, 1], s=5, c="tab:blue", zorder=3)
        ax.scatter(*pos[0], marker="*", s=70, c="red", zorder=4)
        ax.set_aspect("equal", adjustable="datalim")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(f"{r.layout.name}\nF={r.m['frame']}  reach={r.m['reach']:.0f} m  "
                     f"{r.m['area_per_slot']:.3f} km2/slot", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


# =============================================================================================
# Main pipeline
# =============================================================================================
def run(cfg, steps, seed, max_arms, outdir, plots=True, log=print):
    t0 = time.time()
    n = cfg.n
    rng = np.random.default_rng(seed)
    results, rejected = [], []

    # ---- 1. presets ------------------------------------------------------------------------
    fam_fail = {}                                          # family -> (display name, [reasons])
    for lay in preset_layouts(cfg, max_arms):
        ok, why = validate(lay, cfg)
        m = masks = None
        if ok:
            m, masks = evaluate(lay.pos, lay.parent, cfg)
            if m["reach"] < cfg.min_reach - 1e-9:
                ok, why = False, f"reach {m['reach']:.0f} m < required {cfg.min_reach:.0f} m"
        if ok:
            results.append(Result(lay, m, masks))
        else:
            fam_fail.setdefault(lay.family, (lay.name, []))[1].append(why)

    # keep only the best layout variant per family (e.g. best of the 8 binary-tree drawings)
    keep = {}
    for r in results:
        f = r.layout.family
        if f not in keep or sort_key(r, cfg.rank) < sort_key(keep[f], cfg.rank):
            keep[f] = r
    results = list(keep.values())
    for fam, (name, reasons) in fam_fail.items():
        if fam in keep:
            continue
        why = (f"all {len(reasons)} layout variants fail, e.g. {reasons[0]}" if len(reasons) > 1 else reasons[0])
        rejected.append((name, why))
    tree_fail = any(a in ("binary tree", "ternary tree") for a, _ in rejected)

    # ---- 2. searched layout ----------------------------------------------------------------
    if steps > 0 and results:
        start = min(results, key=lambda r: sort_key(r, cfg.rank)).layout
        lay = search_layout(start, cfg, cfg.rank, steps, rng)
        ok, why = validate(lay, cfg)
        if ok:
            m, masks = evaluate(lay.pos, lay.parent, cfg)
            if m["reach"] >= cfg.min_reach - 1e-9:
                results.append(Result(lay, m, masks))
            else:
                rejected.append((lay.name, "searched layout fell below the required reach"))
        else:
            rejected.append((lay.name, why))

    if not results:
        log("No feasible topology for these inputs.")
        for a, b in rejected:
            log(f"  - {a}: {b}")
        return None

    # ---- 3. ranking and per-goal winners ---------------------------------------------------
    results.sort(key=lambda r: sort_key(r, cfg.rank))
    winners = {g: min(results, key=lambda r: sort_key(r, g)) for g in GOALS}
    for g, w in winners.items():
        w.best_for.append(g.replace("_", " "))

    # ---- 4. print --------------------------------------------------------------------------
    tag = f"tdma_n{n}_r{cfg.R.max():g}" + ("_mixed" if len(set(cfg.R)) > 1 else "")
    lines = []
    P = lines.append
    P(f"TDMA topology analysis: {n} radios, range "
      + (f"{cfg.R[0]:g} m" if len(set(cfg.R)) == 1 else f"mixed ({cfg.R.min():g}-{cfg.R.max():g} m)"))
    P(f"rules: min spacing {cfg.sep:g} x smaller range | link {cfg.link_frac:g} x weaker range | "
      f"interference {cfg.interf:g} x own range | load {cfg.load} pkt/radio/frame"
      + (f" | required reach >= {cfg.min_reach:g} m" if cfg.min_reach else ""))
    P(f"frame floor: gateway must receive {results[0].m['frame_floor']} packets per frame -> no topology can use fewer slots")
    P(f"ranked by: {GOAL_LABEL[cfg.rank]}  ({len(results)} feasible topologies)")
    P("")
    P(fmt_table(results, cfg))
    P("")
    P("Rejected / infeasible:")
    for a, b in rejected:
        P(f"  - {a}: {b}")
    if not rejected:
        P("  (none)")
    if tree_fail:
        P("  note: a complete tree needs sibling radios >= 2*asin(min_sep/(2*link_frac)) apart as seen from their "
          "parent;\n        deep trees cannot be drawn in the plane under the spacing rule.")
    P("")
    P("Best case per goal:")
    for g in ("frame", "latency", "reach", "area", "area_per_slot"):
        w = winners[g]
        P(f"  * {GOAL_LABEL[g]:<32}: {w.layout.name}  (frame {w.m['frame']}, reach {w.m['reach']:.0f} m, "
          f"{w.m['max_hops']} hops, latency {w.m['lat_min']}-{w.m['lat_max']} slots, "
          f"area {w.m['area']:.2f} km2, {w.m['area_per_slot']:.4f} km2/slot)")
    best = results[0]
    P("")
    P(f"Top-ranked: {best.layout.name}. Schedule-aware worst-case latency of the deepest radio "
      f"(single packet, no queueing): {best.m['lat_sched']} slots; frame overhead above the floor: "
      f"{best.m['frame'] - best.m['frame_floor']} slots.")
    cust = [r for r in results if r.layout.family == "custom"]
    if cust:
        c = cust[0]
        base = [r for r in results if r.layout.name == c.layout.note.split("'")[1]]
        gain = base and goal_value(c.m, cfg.rank) <= goal_value(base[0].m, cfg.rank) + 1e-9
        P(f"Custom layout: {c.layout.note}" + (" -> no improvement over its starting layout." if gain else "."))
    P(f"(elapsed {time.time() - t0:.1f} s)")
    text = "\n".join(lines)
    log(text)

    # ---- 5. save ---------------------------------------------------------------------------
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{tag}_summary.md").write_text("```\n" + text + "\n```\n")
    (out / f"{tag}_summary.json").write_text(json.dumps(dict(
        params=dict(n=n, ranges=cfg.R.tolist(), min_sep=cfg.sep, link_frac=cfg.link_frac,
                    interference_mult=cfg.interf, load=cfg.load, min_reach=cfg.min_reach, rank=cfg.rank),
        ranking=[dict(name=r.layout.name, **r.m, best_for=r.best_for) for r in results],
        rejected=[dict(name=a, reason=b) for a, b in rejected],
        best_per_goal={g: winners[g].layout.name for g in GOALS}), indent=2))
    saved = [f"{tag}_summary.md", f"{tag}_summary.json"]
    todo = [("best", best)]
    done_ids = {id(best)}
    for g in GOALS:
        if id(winners[g]) not in done_ids:
            todo.append((f"best_{g}", winners[g]))
            done_ids.add(id(winners[g]))
    for suffix, r in todo:
        save_csv(r, cfg, out / f"{tag}_{suffix}_layout.csv")
        (out / f"{tag}_{suffix}.json").write_text(json.dumps(result_dict(r, cfg), indent=2))
        saved += [f"{tag}_{suffix}_layout.csv", f"{tag}_{suffix}.json"]
        if plots:
            extra = "" if suffix == "best" else f"  [{GOAL_LABEL[suffix[5:]]}]"
            plot_best(r, cfg, out / f"{tag}_{suffix}.png", extra)
            saved.append(f"{tag}_{suffix}.png")
    if plots:
        plot_comparison(results, cfg, out / f"{tag}_comparison.png")
        saved.append(f"{tag}_comparison.png")
    log(f"\nSaved to {out.resolve()}/ :\n  " + "\n  ".join(saved))
    return results


def ask_number(prompt, kind, minimum):
    """Keep asking until the user types a valid number."""
    while True:
        try:
            raw = input(prompt)
        except EOFError:
            sys.exit("\nNo input received (stdin closed). Run the script in a terminal and type your answers.")
        try:
            v = kind(raw.strip())
        except ValueError:
            print(f"  Please type a {'whole number' if kind is int else 'number'}.")
            continue
        if v < minimum:
            print(f"  Value must be at least {minimum}.")
            continue
        return v


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="TDMA topology optimizer. n and r are asked interactively.",
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--min-sep", type=float, default=MIN_SEP, help="min spacing, fraction of smaller range")
    ap.add_argument("--link-frac", type=float, default=LINK_FRAC, help="link length, fraction of weaker range")
    ap.add_argument("--interference", type=float, default=INTERF_MULT, help="interference range, x own range")
    ap.add_argument("--load", type=int, default=LOAD, help="packets per radio per frame")
    ap.add_argument("--min-reach", type=float, default=MIN_REACH, help="required reach in metres (0 = none)")
    ap.add_argument("--rank", choices=GOALS, default=RANK_BY, help="primary ranking metric")
    ap.add_argument("--search-steps", type=int, default=SEARCH_STEPS, help="custom-layout search proposals (0=off)")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--max-arms", type=int, default=MAX_SPIDER_ARMS, help="largest spider arm count to try")
    ap.add_argument("--outdir", default=OUTDIR, help="parent results directory (a n<N>_r<R> subfolder is created)")
    ap.add_argument("--no-plots", action="store_true")
    a = ap.parse_args(argv)
    if not (0 < a.min_sep < a.link_frac <= 1):
        ap.error("need 0 < --min-sep < --link-frac <= 1")
    if a.interference <= 0 or a.load < 1:
        ap.error("--interference must be > 0 and --load >= 1")
    # ---- the two mandatory interactive questions ----
    n = ask_number("Enter the total number of radios to configure: ", int, 2)
    r = ask_number("Enter the effective coverage radius of each radio (in meters): ", float, 1.0)
    cfg = Cfg(R=np.full(n, float(r)), sep=a.min_sep, link_frac=a.link_frac, interf=a.interference,
              load=a.load, min_reach=a.min_reach, rank=a.rank)
    return cfg, a


def main(argv=None):
    cfg, a = parse_args(argv)
    outdir = Path(a.outdir) / f"n{cfg.n}_r{cfg.R[0]:g}"
    print(f"\nRunning with n = {cfg.n} radios, r = {cfg.R[0]:g} m ...\n")
    res = run(cfg, a.search_steps, a.seed, a.max_arms, outdir, plots=not a.no_plots)
    return 0 if res else 1


if __name__ == "__main__":
    sys.exit(main())
