"""Does the planner scale?  N = 10..200 random topologies."""
import time

import numpy as np

from experiments.common import plt, save, savefig
from tdmaopt import *

SIZES, SEEDS = [10, 20, 50, 100, 200], 8


def main():
    phy, rows = PHY(), []
    for n in SIZES:
        rec = {"conflict_ms": [], "greedy_ms": [], "F": [], "LB": [], "F_unit": [], "reuse": [],
               "dist_rounds": [], "ok": []}
        for seed in range(SEEDS):
            rng = np.random.default_rng(1000 * n + seed)
            chan, parent, _ = random_connected(n, phy, rng)
            t0 = time.perf_counter(); adj = conflict_graph(chan, parent); t1 = time.perf_counter()
            d = subtree_loads(parent)
            slots, F = greedy_schedule(adj, d); t2 = time.perf_counter()
            rec["conflict_ms"].append(1e3 * (t1 - t0)); rec["greedy_ms"].append(1e3 * (t2 - t1))
            rec["F"].append(F); rec["LB"].append(lower_bound(adj, d))
            rec["reuse"].append(sum(len(s) for s in slots.values()) / F)   # avg simultaneous tx per slot
            u, Fu = greedy_schedule(adj, unit_demand(parent)); rec["F_unit"].append(Fu)
            rec["dist_rounds"].append(distributed_schedule(adj, rng)[1])
            rec["ok"].append(count_violations(adj, slots)[0] == 0)
        rows.append({"N": n, **{k: float(np.mean(v)) for k, v in rec.items()},
                     "all_conflict_free": bool(all(rec["ok"])),
                     "F_over_LB": float(np.mean(np.array(rec["F"]) / np.array(rec["LB"])))})
        print("N", n, "done", flush=True)
    save("scaling", rows)
    fig, ax = plt.subplots(1, 3, figsize=(11, 3.2))
    ns = [r["N"] for r in rows]
    ax[0].plot(ns, [r["F"] for r in rows], "o-", label="greedy F"); ax[0].plot(ns, [r["LB"] for r in rows], "s--", label="lower bound")
    ax[0].set_xlabel("radios N"); ax[0].set_ylabel("frame length (slots)"); ax[0].legend()
    ax[1].plot(ns, [r["conflict_ms"] + r["greedy_ms"] for r in rows], "o-"); ax[1].set_xlabel("radios N"); ax[1].set_ylabel("planning time (ms)")
    ax[1].set_xscale("log"); ax[1].set_yscale("log")
    ax[2].plot(ns, [r["dist_rounds"] for r in rows], "o-"); ax[2].set_xlabel("radios N"); ax[2].set_ylabel("distributed rounds to converge")
    savefig(fig, "scaling")


if __name__ == "__main__":
    main()
