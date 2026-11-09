"""Rank every topology family for N radios of range R and analyse the best case.

    python3 -m tdmaopt.analyze --n 18 --range 100
    python3 -m tdmaopt.analyze --n 18 --range 100 --distance 800 --users 40

Writes results/analysis_n{N}_r{R}.md / .json / .png / _best.png
"""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .phy import PHY, max_range, phy_for_range
from .topology import random_connected
from .viz import (PATTERNS, anneal, draw_conflict, draw_timeline, draw_topology, evaluate, p_spider, p_tree)

RESULTS = Path(__file__).resolve().parent.parent / "results"


# --------------------------------------------------------------------------- extra topology families
def p_comb(n, phy):
    """Spine with teeth alternating up / down."""
    s = 0.9 * max_range(phy)
    spine = int(np.ceil((n + 1) / 2))
    pos = [[i * s, 0.0] for i in range(min(spine, n))]
    i = 0
    while len(pos) < n:
        pos.append([i * s, s if i % 2 == 0 else -s])
        i += 1
    return np.array(pos)


def p_ladder(n, phy):
    s = 0.9 * max_range(phy)
    cols = int(np.ceil(n / 2))
    return np.array([[(i % cols) * s, (i // cols) * s] for i in range(n)])


def all_topologies(n, phy):
    """name -> positions.  Deterministic families only."""
    fam = dict(PATTERNS)
    fam.pop("spider, 3 arms", None)
    fam.pop("spider, 6 arms", None)
    for arms in range(2, min(9, n)):
        fam[f"spider, {arms} arms"] = (lambda nn, pp, a=arms: p_spider(nn, pp, a))
    fam["ternary tree"] = lambda nn, pp: p_tree(nn, pp, branch=3)
    fam["comb"] = p_comb
    fam["ladder (2 rows)"] = p_ladder
    return fam


def random_family(n, phy, local, samples=40, seed=0):
    """Random geometric layouts: report the median and the best by frame length."""
    rng = np.random.default_rng(seed)
    evs = []
    for _ in range(samples):
        chan, _, _ = random_connected(n, phy, rng)
        ev = evaluate(chan.pos, phy, local=local)
        if ev:
            evs.append(ev)
    evs.sort(key=lambda e: e["F_conv"])
    return {"random geometric (median)": evs[len(evs) // 2], "random geometric (best of 40)": evs[0]}


def row_of(name, ev):
    return {"topology": name, "F_conv": ev["F_conv"], "LB": ev["LB"], "reach_m": ev["coverage_m"],
            "reach_Rc": ev["coverage_Rc"], "hops": ev["max_hops"], "latency_slots": ev["max_hops"] * ev["F_conv"],
            "colours": ev["F_unit"], "max_degree": ev["max_degree"], "diameter": ev["diameter"],
            "efficiency_m_per_slot": ev["coverage_m"] / ev["F_conv"], "ev": ev}


def evaluate_all(n, phy, local, exact=False):
    rows = []
    for name, fn in all_topologies(n, phy).items():
        ev = evaluate(fn(n, phy), phy, exact=exact, local=local)
        if ev is not None:
            rows.append(row_of(name, ev))
    for name, ev in random_family(n, phy, local).items():
        rows.append(row_of(name, ev))
    return rows


def pareto_flags(rows):
    for r in rows:
        r["pareto"] = not any((o["reach_m"] >= r["reach_m"] and o["F_conv"] <= r["F_conv"]) and
                              (o["reach_m"] > r["reach_m"] or o["F_conv"] < r["F_conv"]) for o in rows)


def winners(rows, need_m):
    feas = [r for r in rows if need_m is None or r["reach_m"] >= need_m]
    if not feas:
        return None
    return {
        "highest throughput (shortest frame)": min(feas, key=lambda r: (r["F_conv"], r["hops"], -r["reach_m"])),
        "lowest latency (hops x frame)": min(feas, key=lambda r: (r["latency_slots"], r["F_conv"])),
        "longest reach": max(feas, key=lambda r: (r["reach_m"], -r["F_conv"])),
        "best balance (metres of reach per slot)": max(feas, key=lambda r: (r["efficiency_m_per_slot"], -r["F_conv"])),
    }


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Rank all topologies for N radios of range R and analyse the best case.")
    ap.add_argument("--n", type=int, required=True, help="number of radios incl. the user's gateway (node 0)")
    ap.add_argument("--range", type=float, default=0.0, dest="rng_m", help="radio range in metres")
    ap.add_argument("--distance", type=float, default=0.0, help="required coverage distance from the user (m)")
    ap.add_argument("--users", type=int, default=0, help="end users attached to the radios (1 packet/frame each)")
    ap.add_argument("--steps", type=int, default=800, help="search steps for the optimised layout (0 = skip)")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    n = a.n
    phy = phy_for_range(a.rng_m) if a.rng_m > 0 else PHY()
    Rc = max_range(phy)
    need_m = a.distance if a.distance > 0 else None
    local = None
    if a.users > 0:
        counts = np.random.default_rng(a.seed + 99).multinomial(a.users, [1.0 / (n - 1)] * (n - 1))
        local = {i: 1 + int(counts[i - 1]) for i in range(1, n)}
    total = sum(local.values()) if local else n - 1
    tag = f"n{n}_r{int(round(Rc))}"
    RESULTS.mkdir(exist_ok=True)

    notes = []
    if need_m is not None:
        min_radios = int(np.ceil(need_m / (0.9 * Rc)))
        if n - 1 < min_radios:
            notes.append(f"**Not feasible with {n - 1} radios**: reaching {need_m:.0f} m needs at least {min_radios} radios "
                         f"at range {Rc:.0f} m (hops of 0.9 x Rc). Add {min_radios - (n - 1)} radios, raise the range, or lower the target. "
                         f"Rankings below ignore the distance requirement.")
            need_m = None

    rows = evaluate_all(n, phy, local, exact=(n <= 24))
    rng = np.random.default_rng(a.seed)
    if a.steps > 0:                                    # let the search try to beat the standard families
        need = need_m / Rc if need_m else None
        fm = int(np.ceil(1.25 * total))
        best = None
        for fn in list(all_topologies(n, phy).values())[:8]:
            pos, ev = anneal(n, phy, fm, rng, steps=a.steps, start=fn(n, phy), local=local, need=need)
            if ev is None:
                continue
            ok = (ev["coverage_Rc"] >= need) if need is not None else (ev["F_conv"] <= fm)
            key = (ev["F_conv"], -ev["coverage_Rc"]) if need is not None else (-ev["coverage_Rc"], ev["F_conv"])
            if ok and (best is None or key < best[0]):
                best = (key, ev)
        if best:
            rows.append(row_of("search-optimised layout", best[1]))
    pareto_flags(rows)
    feas = [r for r in rows if need_m is None or r["reach_m"] >= need_m]
    rank_key = (lambda r: (r["F_conv"], r["hops"], -r["reach_m"])) if need_m else (lambda r: (-r["efficiency_m_per_slot"], r["F_conv"]))
    ranked = sorted(feas, key=rank_key)
    infeas = [r for r in rows if r not in feas]
    win = winners(rows, need_m)

    # ------------------------------------------------------------------ console + markdown
    L = []
    L.append(f"# Topology analysis: {n} radios, range {Rc:.0f} m, {a.users} users"
             + (f", target {a.distance:.0f} m" if a.distance else "") + "\n")
    L.append(f"* Packets the user's gateway must receive per frame: **{total}** -> no topology can use a frame shorter than {total} slots "
             f"(the gateway takes one packet per slot).")
    L += [f"* {x}" for x in notes]
    L.append("\n## Ranking" + (f" (only topologies reaching >= {need_m:.0f} m, shortest frame first)" if need_m else
                               " (best balance first: metres of reach per frame slot)") + "\n")
    L.append("| # | topology | frame (slots) | reach (m) | hops | latency bound (slots) | m per slot | Pareto-optimal |")
    L.append("|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(ranked, 1):
        L.append(f"| {i} | {r['topology']} | {r['F_conv']} | {r['reach_m']:.0f} | {r['hops']} | {r['latency_slots']} | "
                 f"{r['efficiency_m_per_slot']:.1f} | {'yes' if r['pareto'] else ''} |")
    if infeas:
        L.append(f"\nExcluded (reach below the target): " + ", ".join(f"{r['topology']} ({r['reach_m']:.0f} m)" for r in infeas))
    if win:
        L.append("\n## Best case per goal\n")
        for goal, r in win.items():
            L.append(f"* **{goal}:** {r['topology']} - frame {r['F_conv']} slots, reach {r['reach_m']:.0f} m, {r['hops']} hops")
        top = ranked[0]
        L.append(f"\n## Why **{top['topology']}** wins\n")
        at_floor = top["F_conv"] == total
        L.append(f"* Its frame is **{top['F_conv']}** slots against a floor of {total}: "
                 + ("it sits exactly on the gateway limit, so spatial reuse loses nothing."
                    if at_floor else f"{top['F_conv'] - total} extra slots are lost to conflicts between radios near the gateway."))
        L.append(f"* Conflict-graph colouring needs {top['colours']} slot groups for unit traffic; max radio degree {top['max_degree']}, "
                 f"graph diameter {top['diameter']} hops.")
        L.append(f"* It reaches {top['reach_m']:.0f} m ({top['reach_Rc']:.1f} x Rc) over {top['hops']} hops; worst-case latency "
                 f"{top['latency_slots']} slots.")
        floorers = [r for r in rows if r["F_conv"] == total]
        if floorers:
            far = max(floorers, key=lambda r: r["reach_m"])
            L.append(f"* Among layouts at the frame floor, the longest reach is **{far['topology']}** ({far['reach_m']:.0f} m). "
                     f"Going further needs more slots: that is the reach-versus-throughput trade-off in the Pareto column.")
    # sensitivity to N
    L.append("\n## How the best case changes with the number of radios\n")
    L.append("| radios | shortest frame | longest reach | best balance |")
    L.append("|---|---|---|---|")
    sens = {}
    for mult in (0.5, 0.75, 1.0, 1.5, 2.0):
        nn = max(5, int(round(n * mult)))
        loc = None
        if a.users > 0:
            c = np.random.default_rng(a.seed + 99).multinomial(a.users, [1.0 / (nn - 1)] * (nn - 1))
            loc = {i: 1 + int(c[i - 1]) for i in range(1, nn)}
        rr = []
        for name, fn in all_topologies(nn, phy).items():
            ev = evaluate(fn(nn, phy), phy, local=loc)
            if ev is not None:
                rr.append(row_of(name, ev))
        w = winners(rr, None)
        sens[nn] = {k: (v["topology"], v["F_conv"], round(v["reach_m"])) for k, v in w.items()}
        f = lambda v: f"{v['topology']} ({v['F_conv']} slots, {v['reach_m']:.0f} m)"
        L.append(f"| {nn} | {f(w['highest throughput (shortest frame)'])} | {f(w['longest reach'])} | "
                 f"{f(w['best balance (metres of reach per slot)'])} |")
    L.append("\nAssumptions: disk interference model (interference range 1.5 x Rc), neighbouring radios 0.9 x Rc apart, "
             "convergecast traffic (every radio and user reports once per frame), greedy slot assignment (optimal on random trees, "
             "within 1 slot on grids; see results). Latency bound = hops x frame, conservative.")
    md = "\n".join(L)
    (RESULTS / f"analysis_{tag}.md").write_text(md)
    print(md)

    # ------------------------------------------------------------------ figures
    fig, ax = plt.subplots(1, 2, figsize=(14, max(4.5, 0.32 * len(ranked) + 1.5)))
    names = [r["topology"] for r in ranked][::-1]
    ax[0].barh(names, [r["F_conv"] for r in ranked][::-1],
               color=["tab:green" if r["pareto"] else "tab:blue" for r in ranked][::-1])
    ax[0].axvline(total, color="k", ls=":", label=f"floor = {total} slots")
    ax[0].set_xlabel("frame length (slots)  [green = Pareto-optimal]"); ax[0].legend(fontsize=8)
    ax[0].set_title("ranking" + (f" (reach >= {need_m:.0f} m)" if need_m else ""))
    ax[1].scatter([r["reach_m"] for r in rows], [r["F_conv"] for r in rows],
                  c=["tab:green" if r["pareto"] else "0.6" for r in rows], s=45)
    for r in rows:
        ax[1].annotate(r["topology"], (r["reach_m"], r["F_conv"]), fontsize=6, xytext=(3, 3), textcoords="offset points")
    if need_m:
        ax[1].axvline(need_m, color="purple", ls="--", label=f"target {need_m:.0f} m"); ax[1].legend(fontsize=8)
    ax[1].axhline(total, color="k", ls=":")
    ax[1].set_xlabel(f"reach from the user (m), Rc = {Rc:.0f} m"); ax[1].set_ylabel("frame length (slots)")
    ax[1].set_title("reach vs frame length")
    fig.tight_layout(); fig.savefig(RESULTS / f"analysis_{tag}.png", dpi=130); plt.close(fig)

    if ranked:
        ev = ranked[0]["ev"]
        fig = plt.figure(figsize=(15, 5.2))
        a1, a2, a3 = (fig.add_subplot(1, 3, i) for i in (1, 2, 3))
        sc = draw_topology(a1, ev, f"best: {ranked[0]['topology']}  ({ev['F_conv']} slots, reach {ev['coverage_m']:.0f} m)\n"
                                   f"green = chosen parent, orange dashed = other candidate parents")
        plt.colorbar(sc, ax=a1, fraction=0.035, label="hops to gateway")
        draw_conflict(a2, ev); draw_timeline(a3, ev)
        fig.tight_layout(); fig.savefig(RESULTS / f"analysis_{tag}_best.png", dpi=130); plt.close(fig)

    out = {"inputs": {"n": n, "range_m": Rc, "users": a.users, "distance_m": a.distance},
           "packets_per_frame": total,
           "ranking": [{k: v for k, v in r.items() if k != "ev"} for r in ranked],
           "excluded": [r["topology"] for r in infeas],
           "winners": {k: v["topology"] for k, v in (win or {}).items()}, "sensitivity": sens}
    (RESULTS / f"analysis_{tag}.json").write_text(json.dumps(out, indent=2, default=float))
    print(f"\nwrote results/analysis_{tag}.md  .json  .png  _best.png")


if __name__ == "__main__":
    main()
