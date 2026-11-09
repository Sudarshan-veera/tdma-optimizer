"""Realistic interference: pairwise-conflict schedules vs aggregate SINR with log-normal shadowing."""
import numpy as np

from experiments.common import plt, save, savefig
from tdmaopt import *

N, SEEDS, SIGMAS = 30, 12, [0.0, 4.0, 8.0]


def main():
    rows = []
    for sg in SIGMAS:
        rec = {"fail_before_pct": [], "F_before": [], "F_after": [], "iters": [], "fail_after": []}
        for seed in range(SEEDS):
            phy = PHY(sigma_db=sg)
            rng = np.random.default_rng(77 * seed + int(sg))
            chan, parent, _ = random_connected(N, phy, rng, model="sinr")
            adj = conflict_graph(chan, parent)
            slots, F = greedy_schedule(adj, subtree_loads(parent))
            tot = sum(len(s) for s in slots.values())
            rec["fail_before_pct"].append(100 * len(failing_transmissions(chan, parent, slots)) / tot)
            fixed, it = repair_sinr(chan, parent, slots)
            rec["F_before"].append(F); rec["F_after"].append(frame_length(fixed)); rec["iters"].append(it)
            rec["fail_after"].append(len(failing_transmissions(chan, parent, fixed)))
        rows.append({"sigma_db": sg, **{k: float(np.mean(v)) for k, v in rec.items()},
                     "max_fail_after": int(max(rec["fail_after"]))})
        print(rows[-1], flush=True)
    save("sinr", rows)
    fig, ax = plt.subplots(1, 2, figsize=(8, 3.2))
    xs = [str(r["sigma_db"]) for r in rows]
    ax[0].bar(xs, [r["fail_before_pct"] for r in rows]); ax[0].set_xlabel("shadowing sigma (dB)"); ax[0].set_ylabel("% tx failing before repair")
    w = 0.38; xi = np.arange(len(rows))
    ax[1].bar(xi - w / 2, [r["F_before"] for r in rows], w, label="before"); ax[1].bar(xi + w / 2, [r["F_after"] for r in rows], w, label="after repair")
    ax[1].set_xticks(xi); ax[1].set_xticklabels(xs); ax[1].set_xlabel("shadowing sigma (dB)"); ax[1].set_ylabel("frame length"); ax[1].legend()
    savefig(fig, "sinr")


if __name__ == "__main__":
    main()
