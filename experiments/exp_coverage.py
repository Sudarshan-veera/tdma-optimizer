"""Max coverage distance from the user (gateway) versus throughput and latency."""
from experiments.common import plt, save, savefig
from tdmaopt import PHY
from tdmaopt.coverage import chain_study, max_coverage_distance


def main():
    phy = PHY()
    rows = chain_study(phy, n_max=30)
    # per-node rate (pkt/s) the convergecast frame can carry, for a 10 ms slot
    slot_ms = 10.0
    for r in rows:
        r["max_rate_per_node_pps"] = 1000.0 / (r["F_conv"] * slot_ms)
        r["worst_latency_ms"] = r["hops"] * r["F_conv"] * slot_ms
    cases = []
    for lat_ms, rate in [(5000, 1.0), (10000, 0.5), (20000, 0.2), (60000, 0.1)]:
        b = max_coverage_distance(phy, slot_ms, lat_ms, rate)
        cases.append({"latency_budget_ms": lat_ms, "rate_per_node_pps": rate, "best": b})
    save("coverage", {"slot_ms": slot_ms, "chain": rows, "constrained": cases})
    fig, ax = plt.subplots(1, 3, figsize=(11, 3.2))
    d = [r["distance_m"] for r in rows]
    ax[0].plot(d, [r["F_unit"] for r in rows], "o-", label="single flow (1 slot/node)")
    ax[0].plot(d, [r["F_conv"] for r in rows], "s-", label="all nodes report (convergecast)")
    ax[0].set_xlabel("coverage distance (m)"); ax[0].set_ylabel("frame length (slots)"); ax[0].legend()
    ax[1].plot(d, [r["max_rate_per_node_pps"] for r in rows], "o-"); ax[1].set_yscale("log")
    ax[1].set_xlabel("coverage distance (m)"); ax[1].set_ylabel("max rate per node (pkt/s)")
    ax[2].plot(d, [r["worst_latency_ms"] / 1000 for r in rows], "o-"); ax[2].set_yscale("log")
    ax[2].set_xlabel("coverage distance (m)"); ax[2].set_ylabel("worst-case latency (s)")
    savefig(fig, "coverage")


if __name__ == "__main__":
    main()
