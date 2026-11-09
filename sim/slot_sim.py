#!/usr/bin/env python3
"""
slot_sim.py - slot-level TDMA collision simulation (Python twin of tdma_sim.m and tdma-schedule-sim.cc).

Reception rule, per slot, for every transmission t -> receiver r that is within range of t:
  * r is transmitting in this slot                 -> lost (half duplex)
  * another transmitter is also within range of r  -> lost (collision at r)
        hidden terminal: the interferer is NOT within range of t
        direct:          the interferer is within range of t
  * otherwise                                      -> delivered

Usage (from the repo root):
    python tdma_brain.py --json-out schedule.json
    python sim/export_for_sims.py schedule.json sim/schedule_sim.csv
    python sim/slot_sim.py --input sim/schedule_sim.csv --out sim/py_results.csv
"""
import argparse
import csv
import math
import random
import sys


def load_csv(path):
    names, pos, slots = [], [], []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or line.lower().startswith("name"):
                continue
            f = line.split(",")
            names.append(f[0])
            pos.append((float(f[1]), float(f[2])))
            slots.append(int(f[3]))
    if not names:
        raise SystemExit(f"no radios found in {path}")
    return names, pos, slots


def neighbour_matrix(pos, rng_m):
    n = len(pos)
    return [[i != j and math.hypot(pos[i][0] - pos[j][0], pos[i][1] - pos[j][1]) <= rng_m + 1e-9
             for j in range(n)] for i in range(n)]


def conflicting_pairs(slots, neigh):
    """Independent check: pairs sharing a slot while 1 or 2 hops apart."""
    n = len(slots)
    bad = 0
    for i in range(n):
        for j in range(i + 1, n):
            if slots[i] == slots[j] and (neigh[i][j] or any(neigh[i][k] and neigh[j][k] for k in range(n))):
                bad += 1
    return bad


def one_frame(slots, neigh):
    """Counters for one frame: attempted, success, collided, hidden, direct, half_duplex."""
    n = len(slots)
    c = dict(attempted=0, success=0, collided=0, hidden=0, direct=0, half_duplex=0)
    for s in sorted(set(slots)):
        tx = [i for i in range(n) if slots[i] == s]
        for t in tx:
            for r in range(n):
                if not neigh[t][r]:
                    continue
                c["attempted"] += 1
                if slots[r] == s:
                    c["half_duplex"] += 1
                    continue
                others = [u for u in tx if u != t and neigh[u][r]]
                if not others:
                    c["success"] += 1
                else:
                    c["collided"] += 1
                    if any(not neigh[t][u] for u in others):
                        c["hidden"] += 1
                    else:
                        c["direct"] += 1
    return c


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default="sim/schedule_sim.csv")
    ap.add_argument("--out", default="py_results.csv")
    ap.add_argument("--range", type=float, default=500.0)
    ap.add_argument("--slot-ms", type=float, default=1.0)
    ap.add_argument("--random-runs", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    names, pos, brain = load_csv(a.input)
    n = len(names)
    S = max(brain) + 1
    neigh = neighbour_matrix(pos, a.range)
    links = sum(map(sum, neigh)) // 2
    print("Python slot-level TDMA simulation")
    print(f"  radios: {n}, range: {a.range:g} m, links: {links}, Brain frame length: {S} slots, slot: {a.slot_ms:g} ms")
    print(f"  Independent conflict check on the Brain schedule: {conflicting_pairs(brain, neigh)} conflicting pairs\n")

    scen = [("Brain schedule", brain, S)]
    if "Node_01" in names and "Node_03" in names:
        bad = list(brain)
        bad[names.index("Node_03")] = bad[names.index("Node_01")]
        scen.append(("Bad: Node_03 in Node_01's slot", bad, S))
    scen.append(("Token passing (1 node per slot)", list(range(n)), n))
    scen.append(("All nodes in one slot", [0] * n, 1))

    rows = []
    for name, sl, s_per in scen:
        rows.append((name, s_per, one_frame(sl, neigh)))
    rnd = random.Random(a.seed)
    tot = dict(attempted=0, success=0, collided=0, hidden=0, direct=0, half_duplex=0)
    for _ in range(a.random_runs):
        r = one_frame([rnd.randrange(S) for _ in range(n)], neigh)
        for k in tot:
            tot[k] += r[k]
    rows.append((f"Random schedule (mean of {a.random_runs})", S, {k: v / a.random_runs for k, v in tot.items()}))

    hdr = f"{'Scenario':<36}{'Slots':>6}{'Delivered':>11}{'Collided':>10}{'Hidden':>8}{'Direct':>8}{'Delivery':>10}{'Deliv./sec':>12}"
    print(hdr)
    print("-" * len(hdr))
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["scenario", "slots_per_frame", "frames", "attempted_per_frame", "delivered_per_frame",
                    "collisions_per_frame", "hidden_terminal_per_frame", "direct_per_frame",
                    "half_duplex_per_frame", "delivery_ratio", "delivered_per_second"])
        for name, s_per, c in rows:
            ratio = c["success"] / c["attempted"] if c["attempted"] else 0.0
            per_sec = c["success"] / (s_per * a.slot_ms / 1000.0)
            print(f"{name:<36}{s_per:>6}{c['success']:>11.2f}{c['collided']:>10.2f}{c['hidden']:>8.2f}"
                  f"{c['direct']:>8.2f}{ratio * 100:>9.2f}%{per_sec:>12.0f}")
            w.writerow([name, s_per, 1, c["attempted"], c["success"], c["collided"], c["hidden"],
                        c["direct"], c["half_duplex"], f"{ratio:.6f}", f"{per_sec:.2f}"])
    print("\n(per-frame figures; 'Delivered' counts transmitter-to-neighbour receptions)")
    ok = rows[0][2]["collided"] == 0 and rows[0][2]["half_duplex"] == 0
    print(f"Brain schedule check: {'PASS - zero collisions' if ok else 'FAIL - collisions found'}")
    print(f"Results written to {a.out}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
