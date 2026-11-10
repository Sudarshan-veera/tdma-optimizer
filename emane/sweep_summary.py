#!/usr/bin/env python3
"""Summarise results/emane-sweep/sweep.csv: delivery vs offered load for the good and the bad schedule.
usage: python3 emane/sweep_summary.py results/emane-sweep/sweep.csv      (run on the host, needs numpy + matplotlib)"""
import csv
import os
import statistics as st
import sys
from collections import defaultdict

path = sys.argv[1]
rows = list(csv.DictReader(open(path)))
out_dir = os.path.dirname(path) or "."
by = defaultdict(lambda: defaultdict(list))      # (load, sched) -> metric -> [per-trial values]
trials = defaultdict(lambda: defaultdict(lambda: {"sent": 0, "got": 0, "links": [], "a": None, "b": None}))
for r in rows:
    t = trials[(float(r["load"]), r["sched"])][int(r["rep"])]
    s, g = int(r["sent"]), int(r["got"])
    t["sent"] += s
    t["got"] += g
    t["links"].append(g / s if s else 0.0)
    if r["role"] in ("a", "b"):
        t[r["role"]] = g / s if s else 0.0
for key, reps in trials.items():
    for t in reps.values():
        by[key]["overall"].append(100.0 * t["got"] / max(t["sent"], 1))
        by[key]["worst"].append(100.0 * min(t["links"]))
        if t["a"] is not None:
            by[key]["a"].append(100.0 * t["a"])
            by[key]["b"].append(100.0 * t["b"])


def ms(v):
    return (st.mean(v), st.pstdev(v) if len(v) > 1 else 0.0) if v else (float("nan"), 0.0)


loads = sorted({k[0] for k in by})
lines = ["# EMANE threshold sweep", "",
         f"{len(rows)} link measurements, {len(trials)} (load, schedule) cells. Mean +/- std over repetitions.", "",
         "| load | n | good: overall % | good: worst link % | bad: overall % | bad: worst link % | pair b good % | pair b bad % |",
         "|---|---|---|---|---|---|---|---|"]
for L in loads:
    g, b = by.get((L, "good"), {}), by.get((L, "bad"), {})
    n = len(g.get("overall", []))
    f = lambda d, k: "%.1f +/- %.1f" % ms(d.get(k, []))
    lines.append(f"| {L:.2f} | {n} | {f(g,'overall')} | {f(g,'worst')} | {f(b,'overall')} | {f(b,'worst')} | {f(g,'b')} | {f(b,'b')} |")
knee = next((L for L in loads if ms(by[(L, 'good')]['overall'])[0] < 95.0), None) if loads else None
lines += ["", f"**Capacity knee (first load where the GOOD schedule delivers under 95% overall): "
          f"{'not reached in this sweep' if knee is None else f'{knee:.2f} of slot capacity'}.**", ""]
sep = [(L, ms(by[(L, 'good')]['b'])[0] - ms(by[(L, 'bad')]['b'])[0]) for L in loads if by.get((L, 'bad'), {}).get('b')]
if sep:
    best = max(sep, key=lambda x: x[1])
    lines.append(f"Largest gap between good and bad for the collision-pair radio: {best[1]:.1f} percentage points at load {best[0]:.2f}.")
open(f"{out_dir}/summary.md", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    for sched, style in (("good", "-o"), ("bad", "--s")):
        xs = [L for L in loads if (L, sched) in by]
        ax[0].errorbar(xs, [ms(by[(L, sched)]["overall"])[0] for L in xs], [ms(by[(L, sched)]["overall"])[1] for L in xs],
                       fmt=style, color="k", mfc="w" if sched == "bad" else "k", capsize=3, label=f"{sched} schedule")
        xb = [L for L in xs if by[(L, sched)].get("b")]
        ax[1].errorbar(xb, [ms(by[(L, sched)]["b"])[0] for L in xb], [ms(by[(L, sched)]["b"])[1] for L in xb],
                       fmt=style, color="k", mfc="w" if sched == "bad" else "k", capsize=3, label=f"{sched} schedule")
    ax[0].set_title("Overall one-hop delivery"); ax[1].set_title("Collision-pair radio delivery")
    for a in ax:
        a.set_xlabel("offered load (fraction of slot capacity)"); a.set_ylabel("delivered (%)"); a.grid(alpha=.3); a.legend()
    fig.tight_layout(); fig.savefig(f"{out_dir}/sweep.png", dpi=200)
    print(f"\nwrote {out_dir}/sweep.png")
except ImportError:
    print("\n(matplotlib not found: skipped the plot; activate your .venv and run again)")
