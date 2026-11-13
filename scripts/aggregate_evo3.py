#!/usr/bin/env python3
"""Combine several results/evo3-full-* runs into one table (mean, min, max over runs).
Usage: python3 scripts/aggregate_evo3.py results/evo3-full-A results/evo3-full-B ... > docs/EVO3_REPEATS.md
Runs whose live stage failed (no multi-hop delivery) are skipped and listed."""
import json, re, sys, pathlib, statistics as st

def link_total(run, fn):
    got = sent = 0
    for line in open(run / "baseline-evidence" / fn):
        m = re.match(r"\s*(\d+)\s+(\d+)\s+\[.*?\]\s+[\d.]+\s+(\d+)\s+(\d+)\s", line)
        if m: got += int(m.group(3)); sent += int(m.group(4))
    return 100.0 * got / sent

rows, skipped = [], []
for arg in sys.argv[1:]:
    run = pathlib.Path(arg)
    try:
        adv = json.load(open(run / "evo3_full_report.json"))["advancements"]
        mh = adv["multi_hop"]["pdr_pct_mean_sd"][0]
        if not mh: raise ValueError("zero delivery")
        ad = adv["adaptive_scheduling"]["surge_node_pdr_pct"]
        hp = adv["self_healing_live"]["pdr_pct_of_surviving_nodes"]
        rows.append({"run": run.name,
            "Multi-hop delivery (%)": mh,
            "Optimized schedule, before collision (%)": link_total(run, "good_delivery.txt"),
            "Forced slot collision (%)": link_total(run, "bad_delivery.txt"),
            "Optimized schedule restored (%)": link_total(run, "good_again_delivery.txt"),
            "Surged radio, static (%)": ad["static"],
            "Surged radio, adaptive (%)": ad["adaptive"],
            "Relay failed, before (%)": hp["before_failure"],
            "Relay failed, during (%)": hp["during_failure"],
            "Relay failed, after recovery (%)": hp["after_recovery"]})
    except Exception as e:
        skipped.append(f"{run.name} ({type(e).__name__}: {e})")

print("# Repeat runs (12 radios, EMANE)\n")
print(f"{len(rows)} complete runs: " + ", ".join(r["run"] for r in rows) + "\n")
if skipped: print("Skipped: " + "; ".join(skipped) + "\n")
if rows:
    keys = [k for k in rows[0] if k != "run"]
    print("| Experiment | Mean | Min | Max |\n|---|---|---|---|")
    for k in keys:
        v = [r[k] for r in rows]
        print(f"| {k} | {st.mean(v):.2f} | {min(v):.2f} | {max(v):.2f} |")
    print("\nEach row is computed from the run folders listed above; the same numbers are in each run's `evo3_full_report.json`.")
