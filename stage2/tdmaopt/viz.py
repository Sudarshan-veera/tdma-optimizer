"""Graph-theory view of an N-radio network:
     python3 -m tdmaopt.viz --n 18
Writes (in results/):  graph_nN_patterns.png, graph_nN_best.png, graph_nN_pareto.png, graph_nN.json
"""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .phy import PHY, Channel, max_range, phy_for_range
from .schedule import (conflict_graph, exact_min_frame, greedy_schedule, lower_bound, subtree_loads,
                       unit_demand)
from .topology import build_tree

RESULTS = Path(__file__).resolve().parent.parent / "results"


# ----------------------------------------------------------------------------- arrangement patterns
def _s(phy, k=0.9):
    return k * max_range(phy)


def p_chain(n, phy):
    return np.array([[i * _s(phy), 0.0] for i in range(n)])


def p_star(n, phy):
    a = np.linspace(0, 2 * np.pi, n - 1, endpoint=False)
    return np.vstack([[0, 0]] + [[_s(phy) * np.cos(t), _s(phy) * np.sin(t)] for t in a])


def p_grid(n, phy):
    cols = int(np.ceil(np.sqrt(n * 2)))            # 3 x 6 for n = 18
    pos = [[(i % cols) * _s(phy), (i // cols) * _s(phy)] for i in range(n)]
    return np.array(pos)


def p_ring(n, phy):
    R = _s(phy) / (2 * np.sin(np.pi / n))
    a = np.arange(n) * 2 * np.pi / n
    return np.array([[R * np.cos(t) - R, R * np.sin(t)] for t in a])


def p_spider(n, phy, arms=4):
    pos, k = [[0.0, 0.0]], 0
    per = [(n - 1) // arms + (1 if i < (n - 1) % arms else 0) for i in range(arms)]
    for a, cnt in enumerate(per):
        th = 2 * np.pi * a / arms
        for j in range(1, cnt + 1):
            pos.append([j * _s(phy) * np.cos(th), j * _s(phy) * np.sin(th)])
    return np.array(pos)


def p_tree(n, phy, branch=2):
    """Binary tree grown outward: every child sits 0.85 Rc from its parent, +-40 deg off the parent's heading."""
    pos, head = [np.zeros(2)], [0.0]
    spread = np.radians(40)
    i = 0
    while len(pos) < n:
        for c in range(branch):
            if len(pos) >= n:
                break
            h = head[i] + spread * (c - (branch - 1) / 2) * 2 / max(branch - 1, 1) if branch > 1 else head[i]
            pos.append(pos[i] + 0.85 * max_range(phy) * np.array([np.cos(h), np.sin(h)]))
            head.append(h)
        i += 1
    return np.array(pos)


def p_clusters(n, phy):
    """Three relay hubs 0.9 Rc from the gateway, each with a fan of leaves."""
    Rc = max_range(phy)
    pos = [np.zeros(2)]
    dirs = [np.pi / 2, np.pi / 2 + 2 * np.pi / 3, np.pi / 2 - 2 * np.pi / 3]
    hubs = [0.9 * Rc * np.array([np.cos(t), np.sin(t)]) for t in dirs]
    pos += hubs
    leaves = n - 4
    for i in range(leaves):
        h, t = i % 3, dirs[i % 3]
        k = i // 3
        m = int(np.ceil(leaves / 3))
        ang = t + np.radians(-60 + 120 * k / max(m - 1, 1))
        pos.append(hubs[h] + 0.8 * Rc * np.array([np.cos(ang), np.sin(ang)]))
    return np.array(pos)


def p_spider3(n, phy):
    return p_spider(n, phy, 3)


def p_spider6(n, phy):
    return p_spider(n, phy, 6)


PATTERNS = {"chain (path graph)": p_chain, "star": p_star, "grid (2:1 rows:cols)": p_grid, "ring (cycle graph)": p_ring,
            "spider, 3 arms": p_spider3, "spider, 6 arms": p_spider6, "binary tree": p_tree,
            "3 hubs + leaves": p_clusters}


# ----------------------------------------------------------------------------- evaluation
def evaluate(pos, phy, exact=False, local=None):
    chan = Channel(pos, phy, model="disk")
    parent, hops = build_tree(chan)
    if (parent == -2).any():
        return None
    adj = conflict_graph(chan, parent)
    dem = subtree_loads(parent, local)
    slots, F = greedy_schedule(adj, dem)
    uslots, Fu = greedy_schedule(adj, unit_demand(parent))
    if exact:
        Fu, _ = exact_min_frame(adj, Fu, time_limit=5)
    # graph-theory descriptors
    comm = chan.comm.astype(int)
    N = chan.N
    d = np.where(comm > 0, 1.0, np.inf)
    np.fill_diagonal(d, 0)
    for k in range(N):                               # Floyd-Warshall, N is small
        d = np.minimum(d, d[:, [k]] + d[[k], :])
    ud = {v: len(a) for v, a in adj.items()}
    return {"chan": chan, "parent": parent, "hops": hops, "adj": adj, "slots": slots, "uslots": uslots,
            "F_conv": F, "F_unit": Fu, "LB": lower_bound(adj, dem),
            "coverage_m": float(chan.D[0].max()), "coverage_Rc": float(chan.D[0].max() / chan.Rc),
            "max_hops": int(hops.max()), "comm_edges": int(comm.sum() // 2),
            "max_degree": int(comm.sum(1).max()), "diameter": int(d.max()),
            "conflict_edges": sum(ud.values()) // 2, "max_conflict_deg": max(ud.values()),
            "clique_LB_unit": lower_bound(adj, unit_demand(parent))}


# ----------------------------------------------------------------------------- drawing
def draw_topology(ax, ev, title, show_alt=True, labels=True):
    chan, parent, hops = ev["chan"], ev["parent"], ev["hops"]
    P, N = chan.pos, chan.N
    for i in range(N):
        for j in range(i + 1, N):
            if chan.comm[i, j]:
                ax.plot(*P[[i, j]].T, color="0.8", lw=0.8, zorder=1)
    if show_alt:                                       # non-chosen candidate parents (dashed)
        for v in range(1, N):
            for u in np.flatnonzero(chan.comm[v]):
                if hops[u] == hops[v] - 1 and u != parent[v]:
                    ax.plot(*P[[v, u]].T, color="tab:orange", lw=1.0, ls="--", zorder=2)
    for v in range(1, N):
        p = parent[v]
        ax.annotate("", xy=P[p], xytext=P[v], arrowprops=dict(arrowstyle="-|>", color="tab:green", lw=1.8,
                                                              shrinkA=7, shrinkB=7), zorder=3)
    sc = ax.scatter(P[:, 0], P[:, 1], c=hops, cmap="viridis", s=170, zorder=4, edgecolors="k")
    ax.scatter(*P[0], marker="*", s=420, c="gold", edgecolors="k", zorder=5)
    if labels:
        for v in range(N):
            ax.text(P[v, 0], P[v, 1], str(v), ha="center", va="center", fontsize=7, zorder=6,
                    color="white" if v and hops[v] < 3 else "black")
    ax.add_patch(plt.Circle(P[0], chan.Rc, fill=False, ls=":", color="gold"))
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=9)
    ax.set_xticks([]); ax.set_yticks([])
    ax.grid(False)
    return sc


def draw_conflict(ax, ev):
    adj, uslots = ev["adj"], ev["uslots"]
    nodes = sorted(adj, key=lambda v: (uslots[v][0], v))
    ang = {v: 2 * np.pi * i / len(nodes) for i, v in enumerate(nodes)}
    xy = {v: (np.cos(ang[v]), np.sin(ang[v])) for v in nodes}
    cmap = plt.get_cmap("tab10")
    for v in nodes:
        for u in adj[v]:
            if u > v:
                ax.plot(*zip(xy[v], xy[u]), color="0.75", lw=0.5, zorder=1)
    for v in nodes:
        ax.scatter(*xy[v], s=230, color=cmap(uslots[v][0] % 10), edgecolors="k", zorder=3)
        ax.text(*xy[v], str(v), ha="center", va="center", fontsize=7, zorder=4)
    ax.set_aspect("equal"); ax.axis("off")
    ax.set_title(f"conflict graph, greedy vertex colouring\n{len(set(s[0] for s in uslots.values()))} colours "
                 f"(clique bound {ev['clique_LB_unit']}), {ev['conflict_edges']} edges", fontsize=9)


def draw_timeline(ax, ev):
    slots, F = ev["slots"], ev["F_conv"]
    for r, v in enumerate(sorted(slots)):
        for s in slots[v]:
            ax.barh(r, 1, left=s, color="tab:green", edgecolor="white", height=0.85)
    ax.set_yticks(range(len(slots))); ax.set_yticklabels([str(v) for v in sorted(slots)], fontsize=6)
    ax.set_xlim(0, F); ax.invert_yaxis(); ax.set_xlabel("slot in frame"); ax.set_ylabel("radio")
    ax.set_title(f"TDMA frame: {F} slots (lower bound {ev['LB']})", fontsize=9)


# ----------------------------------------------------------------------------- search
def _energy(ev, fmax, need=None):
    """fmax mode : maximise reach while keeping the frame within fmax slots (soft penalty).
    need mode  : minimise the frame while reaching at least `need` x Rc from the user."""
    if need is not None:
        return ev["F_conv"] + 8.0 * max(0.0, need - ev["coverage_Rc"])
    return -ev["coverage_Rc"] + 1.0 * max(0, ev["F_conv"] - fmax)


def anneal(n, phy, fmax, rng, steps=2500, start=None, trace=None, local=None, need=None):
    """Simulated annealing over radio positions: maximise coverage radius subject to frame <= fmax."""
    Rc = max_range(phy)
    pos = start.copy() if start is not None else p_spider(n, phy, 4)
    pos[0] = (0, 0)
    ev = evaluate(pos, phy, local=local)
    if ev is None:
        return None, None
    e0 = _energy(ev, fmax, need)
    best, best_e = (pos.copy(), ev), e0
    for k in range(steps):
        T = 1.5 * (1 - k / steps) + 0.02
        cand = pos.copy()
        i = int(rng.integers(1, n))
        if rng.random() < 0.25:                         # jump next to another radio
            j = int(rng.integers(0, n))
            ang = rng.uniform(0, 2 * np.pi)
            cand[i] = cand[j] + 0.85 * Rc * np.array([np.cos(ang), np.sin(ang)])
        else:
            cand[i] += rng.normal(0, 0.3 * Rc, 2)
        e2 = evaluate(cand, phy, local=local)
        if e2 is None:
            continue
        en = _energy(e2, fmax, need)
        if trace is not None:
            trace.append((e2["coverage_Rc"], e2["F_conv"]))
        if en <= e0 or rng.random() < np.exp((e0 - en) / T):
            pos, ev, e0 = cand, e2, en
            ok = (ev["coverage_Rc"] >= need) if need is not None else (ev["F_conv"] <= fmax)
            if e0 < best_e and ok:
                best, best_e = (pos.copy(), ev), e0
    return best


def best_single_move(pos, phy, fmax, local=None, need=None):
    """Best neighbouring arrangement: move ONE radio by 0.3 Rc in one of 8 directions."""
    Rc = max_range(phy)
    base = evaluate(pos, phy, local=local)
    c0 = _energy(base, fmax, need)
    best = None
    for v in range(1, len(pos)):
        for a in np.arange(8) * np.pi / 4:
            cand = pos.copy()
            cand[v] += 0.3 * Rc * np.array([np.cos(a), np.sin(a)])
            e = evaluate(cand, phy, local=local)
            if e is None:
                continue
            c = _energy(e, fmax, need)
            if c < c0 - 1e-9 and (best is None or c < best["cost"]):
                best = {"node": v, "direction_deg": int(np.degrees(a)), "cost": c,
                        "F_before": base["F_conv"], "F_after": e["F_conv"],
                        "coverage_before_Rc": base["coverage_Rc"], "coverage_after_Rc": e["coverage_Rc"]}
    return best


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Graph-theory planner for an N-radio network.")
    ap.add_argument("--n", type=int, default=18, help="number of radios (excluding the user's gateway is n-1; node 0 is the gateway)")
    ap.add_argument("--range", type=float, default=0.0, help="radio range in metres (default: from the link budget, ~166 m)")
    ap.add_argument("--distance", type=float, default=0.0, help="required coverage distance from the user in metres")
    ap.add_argument("--users", type=int, default=0, help="end users attached to the radios (each sends 1 packet per frame)")
    ap.add_argument("--fmax", type=int, default=0, help="frame-length budget (slots) for the featured design (default 1.25 x lower bound)")
    ap.add_argument("--steps", type=int, default=2500)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    n, rng = a.n, np.random.default_rng(a.seed)
    phy = phy_for_range(a.range) if a.range > 0 else PHY()
    Rc = max_range(phy)
    RESULTS.mkdir(exist_ok=True)

    local = None
    if a.users > 0:
        counts = np.random.default_rng(a.seed + 99).multinomial(a.users, [1.0 / (n - 1)] * (n - 1))
        local = {i: 1 + int(counts[i - 1]) for i in range(1, n)}
    total = sum(local.values()) if local else n - 1          # packets the gateway must receive per frame
    print(f"radios {n} (node 0 = user gateway) | radio range Rc = {Rc:.0f} m | users {a.users} | "
          f"packets per frame {total} -> frame length can never be below {total} slots")
    need = None
    if a.distance > 0:
        need = a.distance / Rc
        min_radios = int(np.ceil(a.distance / (0.9 * Rc)))
        print(f"target distance {a.distance:.0f} m = {need:.1f} x Rc -> at least {min_radios} radios needed "
              f"(hops of 0.9 x Rc); you have {n - 1}")
        if n - 1 < min_radios:
            print(f"NOT FEASIBLE with {n - 1} radios: add {min_radios - (n - 1)} more, raise the radio range, "
                  f"or lower the target. Showing the best reach possible instead "
                  f"({(n - 1) * 0.9 * Rc:.0f} m as a straight chain).")
            need = None

    # 1. every standard pattern
    rows, evs = [], {}
    for name, fn in PATTERNS.items():
        ev = evaluate(fn(n, phy), phy, exact=True, local=local)
        if ev is None:
            print(f"skip {name}: disconnected")
            continue
        evs[name] = ev
        rows.append({"pattern": name, "coverage_m": ev["coverage_m"],
                     **{k: ev[k] for k in ("F_conv", "LB", "F_unit", "coverage_Rc", "max_hops",
                        "diameter", "max_degree", "comm_edges", "conflict_edges", "clique_LB_unit")}})
    k = len(evs)
    cols = 4
    fig, axs = plt.subplots(int(np.ceil(k / cols)), cols, figsize=(4 * cols, 3.9 * int(np.ceil(k / cols))))
    for ax in np.ravel(axs):
        ax.axis("off")
    for ax, (name, ev) in zip(np.ravel(axs), evs.items()):
        ax.axis("on")
        draw_topology(ax, ev, f"{name}\nframe {ev['F_conv']} slots | reach {ev['coverage_m']:.0f} m | "
                              f"{ev['max_hops']} hops", show_alt=False, labels=False)
    fig.suptitle(f"{n} radios, range {Rc:.0f} m, {a.users} users: arrangement patterns "
                 f"(green = routing tree to the user's gateway star)", y=1.0)
    fig.tight_layout()
    fig.savefig(RESULTS / f"graph_n{n}_patterns.png", dpi=130)
    plt.close(fig)

    # 2. search
    cloud = [(r["coverage_Rc"], r["F_conv"], r["pattern"]) for r in rows]
    starts = [fn(n, phy) for fn in (p_spider3, p_spider, p_spider6, p_grid, p_ring, p_chain, p_tree)]
    starts += [p_spider(n, phy, k_) for k_ in (1, 2, 5)]
    fdefault = int(np.ceil(1.25 * total))
    budgets = sorted({total, fdefault, int(np.ceil(1.6 * total)), 2 * total, 3 * total, a.fmax or fdefault})
    designs = {}
    for fm in budgets:
        top = None
        for st in starts[:7]:
            tr = []
            pos, ev = anneal(n, phy, fm, rng, steps=a.steps, start=st, trace=tr, local=local)
            cloud += [(c, f, "search") for c, f in tr]
            if ev is not None and ev["F_conv"] <= fm and (top is None or ev["coverage_Rc"] > top[1]["coverage_Rc"]):
                top = (pos, ev)
        if top is not None:
            designs[fm] = top
            print(f"frame budget {fm:>3}: best reach {top[1]['coverage_m']:.0f} m  (frame {top[1]['F_conv']}, "
                  f"{top[1]['max_hops']} hops)", flush=True)
    fmain = a.fmax or fdefault
    if need is not None:                                  # shortest frame that still reaches the target distance
        top = None
        for st in starts:
            pos, ev = anneal(n, phy, 0, rng, steps=a.steps, start=st, local=local, need=need)
            if ev is not None and ev["coverage_Rc"] >= need and (
                    top is None or (ev["F_conv"], -ev["coverage_Rc"]) < (top[1]["F_conv"], -top[1]["coverage_Rc"])):
                top = (pos, ev)
        if top is None:
            print("search found no arrangement reaching the target; showing best-budget design instead")
            need = None
        else:
            pos, best = top
            print(f"\nBEST for {a.distance:.0f} m: frame {best['F_conv']} slots, reach {best['coverage_m']:.0f} m, "
                  f"{best['max_hops']} hops")
    if need is None:
        pos, best = designs[fmain] if fmain in designs else list(designs.values())[0]
    move = best_single_move(pos, phy, fmain, local=local, need=need)
    spider_rows = []
    for arms in range(1, 9):
        ev = evaluate(p_spider(n, phy, arms), phy, local=local)
        if ev:
            spider_rows.append({"arms": arms, "F_conv": ev["F_conv"], "coverage_m": ev["coverage_m"],
                                "max_hops": ev["max_hops"],
                                "reaches_target": (ev["coverage_Rc"] >= need) if need else None})

    fig, ax = plt.subplots(figsize=(7, 4.8))
    srch = [(c, f) for c, f, t in cloud if t == "search"]
    ax.scatter([c * Rc for c, f in srch], [f for c, f in srch], s=3, alpha=0.2, color="tab:blue", label="arrangements tried")
    allpts = sorted({(round(c, 3), f) for c, f, _ in cloud})
    front, bestF = [], 1e9
    for c, f in sorted(allpts, key=lambda q: (-q[0], q[1])):
        if f < bestF:
            front.append((c, f)); bestF = f
    ax.plot([c * Rc for c, f in front], [f for c, f in front], "o-", color="tab:red", ms=3, label="Pareto front (best trade-off)")
    for r in rows:
        ax.scatter(r["coverage_m"], r["F_conv"], s=60, marker="s", color="k", zorder=5)
        ax.annotate(r["pattern"], (r["coverage_m"], r["F_conv"]), fontsize=7, xytext=(4, 4), textcoords="offset points")
    ax.axhline(total, color="g", ls=":", label=f"gateway limit: frame >= {total} packets/frame")
    if a.distance > 0:
        ax.axvline(a.distance, color="purple", ls="--", label=f"target {a.distance:.0f} m")
    ax.scatter(best["coverage_m"], best["F_conv"], s=160, marker="*", color="gold", edgecolors="k", zorder=6, label="featured design")
    ax.set_xlabel(f"coverage distance from the user (m), Rc = {Rc:.0f} m"); ax.set_ylabel("frame length when all radios report (slots)")
    ax.set_title(f"{n} radios, {a.users} users: reach vs schedule length"); ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(RESULTS / f"graph_n{n}_pareto.png", dpi=130); plt.close(fig)

    # 3. the chosen design in detail
    fig = plt.figure(figsize=(15, 5.2))
    ax1, ax2, ax3 = fig.add_subplot(1, 3, 1), fig.add_subplot(1, 3, 2), fig.add_subplot(1, 3, 3)
    what = (f"shortest frame reaching {a.distance:.0f} m" if need is not None else f"frame <= {fmain} slots, longest reach")
    sc = draw_topology(ax1, best, f"best arrangement ({what}): {best['F_conv']} slots, reach {best['coverage_m']:.0f} m\n"
                                  f"green = chosen parent, orange dashed = other candidate parents")
    plt.colorbar(sc, ax=ax1, fraction=0.035, label="hops to gateway")
    draw_conflict(ax2, best)
    draw_timeline(ax3, best)
    fig.tight_layout(); fig.savefig(RESULTS / f"graph_n{n}_best.png", dpi=130); plt.close(fig)

    out = {"inputs": {"radios": n, "range_m": Rc, "users": a.users, "distance_m": a.distance},
           "packets_per_frame": total, "patterns": rows, "spider_family": spider_rows,
           "best": {"F_conv": best["F_conv"], "coverage_m": best["coverage_m"], "max_hops": best["max_hops"],
                    "positions_m": pos.round(1).tolist(), "parent": best["parent"].tolist(),
                    "best_single_move": move},
           "best_by_frame_budget": {str(f): {"F_conv": e["F_conv"], "coverage_m": e["coverage_m"], "max_hops": e["max_hops"]}
                                    for f, (p, e) in designs.items()}}
    (RESULTS / f"graph_n{n}.json").write_text(json.dumps(out, indent=2, default=float))
    print(f"\n{'pattern':26} {'frame':>5} {'LB':>4} {'colours':>7} {'reach(m)':>8} {'hops':>4} {'diam':>4} {'maxdeg':>6}")
    for r in rows:
        print(f"{r['pattern']:26} {r['F_conv']:>5} {r['LB']:>4} {r['F_unit']:>7} {r['coverage_m']:>8.0f} "
              f"{r['max_hops']:>4} {r['diameter']:>4} {r['max_degree']:>6}")
    print("\nspider family (arms: frame, reach m):", [(r["arms"], r["F_conv"], round(r["coverage_m"])) for r in spider_rows])
    print("best single-radio move from the featured design:",
          move or "none - no one-radio move improves it (local optimum)")
    print(f"wrote results/graph_n{n}_patterns.png, _best.png, _pareto.png, graph_n{n}.json")


if __name__ == "__main__":
    main()
