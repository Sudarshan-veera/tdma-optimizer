"""TDMA planner vs random slot choice vs slotted ALOHA vs slotted CSMA (N=20, convergecast)."""
import numpy as np

from experiments.common import plt, save, savefig
from tdmaopt import *

N, SEEDS, T = 20, 5, 8000
LOADS = [0.004, 0.008, 0.012, 0.016, 0.020, 0.030]      # packets / node / slot
ALOHA_P = [0.03, 0.08, 0.2]


def main():
    phy = PHY()
    agg = {k: {l: [] for l in LOADS} for k in ("tdma", "aloha", "csma")}
    static = []
    for seed in range(SEEDS):
        rng = np.random.default_rng(seed)
        chan, parent, _ = random_connected(N, phy, rng)
        adj = conflict_graph(chan, parent)
        d = subtree_loads(parent)
        slots, F = greedy_schedule(adj, d)
        rbad, rtot = count_violations(adj, random_schedule(adj, d, F, rng))
        static.append({"seed": seed, "F": F, "lower_bound": lower_bound(adj, d),
                       "random_collision_pct": 100 * rbad / rtot,
                       "greedy_collision_pct": 100 * count_violations(adj, slots)[0] / rtot})
        for lam in LOADS:
            agg["tdma"][lam].append(simulate(chan, parent, "tdma", lam, T, rng, slots=slots))
            best = max((simulate(chan, parent, "aloha", lam, T, rng, p=p) for p in ALOHA_P),
                       key=lambda r: r["throughput"])
            agg["aloha"][lam].append(best)
            agg["csma"][lam].append(simulate(chan, parent, "csma", lam, T, rng))
        print("seed", seed, "done", flush=True)

    def m(proto, lam, key):
        return float(np.nanmean([r[key] for r in agg[proto][lam]]))

    summary = {proto: {str(lam): {k: m(proto, lam, k) for k in
               ("throughput", "delivery_ratio", "mean_latency", "collision_rate", "tx_per_delivery")}
               for lam in LOADS} for proto in agg}
    save("baselines", {"N": N, "seeds": SEEDS, "slots_simulated": T, "static": static, "summary": summary,
                       "loads": LOADS})

    fig, ax = plt.subplots(1, 4, figsize=(15, 3.4))
    for proto, c in (("tdma", "tab:green"), ("aloha", "tab:red"), ("csma", "tab:blue")):
        for a, key, yl in zip(ax, ("throughput", "delivery_ratio", "mean_latency", "collision_rate"),
                              ("gateway throughput (pkt/slot)", "delivery ratio", "mean latency (slots)", "collision rate")):
            a.plot(LOADS, [m(proto, l, key) for l in LOADS], "o-", color=c, label=proto.upper())
            a.set_xlabel("offered load (pkt/node/slot)")
            a.set_ylabel(yl)
    ax[0].legend()
    ax[2].set_yscale("log")
    savefig(fig, "baselines")


if __name__ == "__main__":
    main()
