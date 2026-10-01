#!/usr/bin/env python3
"""Compare colouring strategies over many random topologies (numbers for the documentation).
Usage: python3 benchmark_random.py [--trials 200] [--nodes 16] [--area 1500]"""
import argparse, random, statistics, time
import networkx as nx
import tdma_brain as t


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--trials", type=int, default=200)
    p.add_argument("--nodes", type=int, default=16)
    p.add_argument("--area", type=float, default=1500.0, help="side of the square, metres")
    p.add_argument("--seed", type=int, default=1)
    a = p.parse_args()
    rng = random.Random(a.seed)
    names = ["Greedy largest-first", "DSATUR (networkx)", "DSATUR custom x1",
             "DSATUR + restarts + local search"]
    slots = {n: [] for n in names}
    ms = {n: 0.0 for n in names}
    opt, lbs, reuse = [], [], []
    for _ in range(a.trials):
        c = {f"Node_{i+1:02d}": (rng.uniform(0, a.area), rng.uniform(0, a.area)) for i in range(a.nodes)}
        C = t.conflict_graph(t.build_graph(c))
        runs = {
            names[0]: lambda: nx.greedy_color(C, "largest_first"),
            names[1]: lambda: nx.greedy_color(C, "DSATUR"),
            names[2]: lambda: t.dsatur(C, random.Random(0)),
            names[3]: lambda: t.heuristic_colouring(C, 100, 0),
        }
        for n, fn in runs.items():
            t0 = time.perf_counter(); col = fn(); ms[n] += (time.perf_counter() - t0) * 1000
            slots[n].append(max(col.values()) + 1)
        best, proven = t.exact_improve(C, t.heuristic_colouring(C, 100, 0), t.lower_bound(C), 2.0)
        opt.append((max(best.values()) + 1) if proven else None)
        lbs.append(t.lower_bound(C)); reuse.append(a.nodes / (max(best.values()) + 1))
    ok = [i for i, o in enumerate(opt) if o is not None]
    print(f"{a.trials} random topologies, {a.nodes} nodes in {a.area:g} m x {a.area:g} m, range 500 m")
    print(f"Optimum proven in {len(ok)}/{a.trials} cases; mean optimum = {statistics.mean(opt[i] for i in ok):.2f} slots\n")
    print(f"{'Strategy':36s} | mean slots | within optimum | ms/run")
    print("-" * 74)
    for n in names:
        hit = sum(slots[n][i] == opt[i] for i in ok)
        print(f"{n:36s} | {statistics.mean(slots[n]):10.2f} | {hit:4d}/{len(ok):<4d} ({100*hit/len(ok):4.0f}%) | {ms[n]/a.trials:6.2f}")
    print(f"\nMean spatial-reuse capacity gain vs one-node-per-slot: {statistics.mean(reuse):.2f}x")


if __name__ == "__main__":
    main()
