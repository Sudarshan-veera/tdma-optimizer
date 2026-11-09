"""How close is greedy to the true optimum?  Exact DSATUR branch-and-bound on three families:
random trees (unit demand), random trees (weighted convergecast demand), and square grids."""
import numpy as np

from experiments.common import plt, save, savefig
from tdmaopt import *
from tdmaopt.topology import grid

SIZES_UNIT, SIZES_W, SEEDS = [6, 8, 10, 12, 14, 16, 20], [6, 8, 10, 12], 30


def row(label, size, results):
    ok = [r for r in results if r["proven"]]
    return {"family": label, "size": size, "instances": len(results), "proven_optimal": len(ok),
            "greedy_equals_optimum_pct": 100 * np.mean([r["F"] == r["best"] for r in ok]) if ok else None,
            "greedy_equals_clique_bound_pct": 100 * np.mean([r["F"] == r["lb"] for r in ok]) if ok else None,
            "max_gap_slots": int(max((r["F"] - r["best"] for r in ok), default=0))}


def one(adj, demand, weighted):
    _, F = greedy_schedule(adj, demand)
    g = expand_demand(adj, demand) if weighted else adj
    best, proven = exact_min_frame(g, F, time_limit=10)
    return {"F": F, "best": best, "proven": proven, "lb": lower_bound(adj, demand)}


def main():
    phy, Rc, rows = PHY(), None, []
    for n in SIZES_UNIT:
        res = []
        for seed in range(SEEDS):
            rng = np.random.default_rng(500 * n + seed)
            chan, parent, _ = random_connected(n, phy, rng)
            res.append(one(conflict_graph(chan, parent), unit_demand(parent), False))
        rows.append(row("random, unit demand", n, res)); print(rows[-1], flush=True)
    for n in SIZES_W:
        res = []
        for seed in range(SEEDS):
            rng = np.random.default_rng(900 * n + seed)
            chan, parent, _ = random_connected(n, phy, rng)
            res.append(one(conflict_graph(chan, parent), subtree_loads(parent), True))
        rows.append(row("random, weighted demand", n, res)); print(rows[-1], flush=True)
    Rc = max_range(phy)
    for r in (3, 4, 5, 6):
        chan = Channel(grid(r, r, 0.9 * Rc), phy)
        parent, _ = build_tree(chan)
        rows.append(row("grid, unit demand", r * r, [one(conflict_graph(chan, parent), unit_demand(parent), False)]))
        print(rows[-1], flush=True)
    save("exact", rows)
    fig, ax = plt.subplots(figsize=(6, 3.2))
    labels = [f"{r['family'].split(',')[0]}-{r['family'].split(', ')[1][:1]}\nN={r['size']}" for r in rows]
    ax.bar(range(len(rows)), [r["greedy_equals_optimum_pct"] or 0 for r in rows])
    ax.set_xticks(range(len(rows))); ax.set_xticklabels(labels, rotation=90, fontsize=6)
    ax.set_ylabel("% instances: greedy = optimum"); ax.set_ylim(0, 105)
    savefig(fig, "exact")


if __name__ == "__main__":
    main()
