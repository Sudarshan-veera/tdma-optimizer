"""Node joins / leaves: incremental update vs recomputing everything."""
import numpy as np

from experiments.common import plt, save, savefig
from tdmaopt import PHY, random_connected
from tdmaopt.dynamic import DynamicNet

N, SEEDS, EVENTS = 40, 6, 20


def main():
    phy = PHY()
    moved_all, n_all, valid_all, Fs = [], [], [], []
    for seed in range(SEEDS):
        rng = np.random.default_rng(seed)
        chan, _, _ = random_connected(N, phy, rng)
        dn = DynamicNet(phy, {i: chan.pos[i] for i in range(chan.N)})
        nxt = 1000
        for ev in range(EVENTS):
            if ev % 2 == 0:
                anchor = int(rng.choice([v for v in dn.pos if v != 0]))
                xy = np.array(dn.pos[anchor]) + rng.normal(0, 70, 2)
                moved, F = dn.join(nxt, xy); nxt += 1
            else:
                moved, F = dn.leave(int(rng.choice([v for v in dn.parent if v != 0])))
            moved_all.append(moved); n_all.append(len(dn.demand)); valid_all.append(dn.valid()); Fs.append(F)
    res = {"events": len(moved_all), "all_valid": bool(all(valid_all)),
           "mean_reassigned": float(np.mean(moved_all)), "max_reassigned": int(max(moved_all)),
           "mean_network_size": float(np.mean(n_all)),
           "mean_reassigned_pct": float(100 * np.mean(np.array(moved_all) / np.array(n_all)))}
    print(res)
    save("dynamic", res)
    fig, ax = plt.subplots(figsize=(4.8, 3.2))
    ax.hist(moved_all, bins=range(0, max(moved_all) + 2), color="tab:green")
    ax.axvline(np.mean(n_all), color="k", ls="--", label="full recompute = all nodes")
    ax.set_xlabel("nodes re-assigned per join/leave"); ax.set_ylabel("events"); ax.legend()
    savefig(fig, "dynamic")


if __name__ == "__main__":
    main()
