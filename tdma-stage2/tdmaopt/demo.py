"""Quick end-to-end demo:  python3 -m tdmaopt.demo"""
import numpy as np

from . import *
from .coverage import max_coverage_distance


def main():
    phy = PHY()
    print(f"Link budget -> communication range Rc = {max_range(phy):.0f} m "
          f"(Pt {phy.pt_dbm} dBm, sensitivity {phy.sens_dbm} dBm, {phy.f_hz/1e9:.1f} GHz, n={phy.n})")
    rng = np.random.default_rng(7)
    chan, parent, hops = random_connected(12, phy, rng)
    adj = conflict_graph(chan, parent)
    demand = subtree_loads(parent)
    slots, F = greedy_schedule(adj, demand)
    print(f"\n12 radios, gateway = node 0, coverage radius {coverage_radius(chan, parent):.0f} m, "
          f"max {hops.max()} hops")
    print(f"Frame length {F} slots (lower bound {lower_bound(adj, demand)}), "
          f"conflicting transmissions: {count_violations(adj, slots)[0]}")
    print("\nnode -> parent  hops  load  slots")
    for v in sorted(slots):
        print(f"{v:>4} -> {parent[v]:<4}  {hops[v]:>3}  {demand[v]:>4}  {slots[v]}")
    print("\nframe timeline (rows = nodes, '#' = transmits)")
    for v in sorted(slots):
        print(f"{v:>3} " + "".join("#" if s in slots[v] else "." for s in range(F)))
    print("\nOffered load 0.02 pkt/node/slot, 6000 slots:")
    for proto in ("tdma", "aloha", "csma"):
        r = simulate(chan, parent, proto, 0.02, 6000, rng, slots=slots, p=0.08)
        print(f"  {proto:5} throughput {r['throughput']:.3f} pkt/slot | delivered {100*r['delivery_ratio']:.0f}% | "
              f"collisions {100*r['collision_rate']:.0f}% | mean latency {r['mean_latency']:.0f} slots")
    best = max_coverage_distance(phy, slot_ms=10, latency_ms=20000, rate_pps=0.2)
    print(f"\nChain coverage, 10 ms slots, 20 s latency budget, 0.2 pkt/s per node: "
          f"{best['hops']} hops = {best['distance_m']:.0f} m (frame {best['F_conv']} slots)")


if __name__ == "__main__":
    main()
