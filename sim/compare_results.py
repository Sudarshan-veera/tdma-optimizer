#!/usr/bin/env python3
"""
compare_results.py - put the MATLAB, ns-3 and Python results side by side and flag any mismatch.

    python sim/compare_results.py --matlab matlab_results.csv --ns3 ns3_results.csv --python py_results.csv

Deterministic scenarios (Brain, bad, token, one slot) must agree exactly in every simulator.
The random row depends on each tool's random-number generator, so it is only shown.
"""
import argparse
import csv


def key(name):
    s = name.lower()
    if "matlab schedule" in s:
        return "own colouring (MATLAB)"
    if "brain" in s:
        return "Brain schedule"
    if "bad" in s:
        return "Bad (03 in 01's slot)"
    if "token" in s:
        return "Token passing"
    if "one slot" in s:
        return "All in one slot"
    if "random" in s:
        return "Random (mean)"
    return name


def load(path):
    out = {}
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[key(r["scenario"])] = r
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--matlab", required=True)
    ap.add_argument("--ns3", required=True)
    ap.add_argument("--python", required=True)
    a = ap.parse_args()
    tools = {"MATLAB": load(a.matlab), "ns-3": load(a.ns3), "Python": load(a.python)}
    fields = [("delivered_per_frame", "delivered"), ("collisions_per_frame", "collided"),
              ("hidden_terminal_per_frame", "hidden"), ("direct_per_frame", "direct")]
    bad = 0
    print(f"{'Scenario':<26}{'Tool':<8}{'Slots':>6}{'Delivered':>11}{'Collided':>10}{'Hidden':>8}{'Direct':>8}{'Delivery':>10}")
    print("-" * 87)
    for sc in ["Brain schedule", "Bad (03 in 01's slot)", "Token passing", "All in one slot", "Random (mean)"]:
        vals = []
        for t, d in tools.items():
            r = d.get(sc)
            if r is None:
                print(f"{sc:<26}{t:<8}  (missing)")
                continue
            v = [float(r[f]) for f, _ in fields]
            vals.append(v)
            print(f"{sc:<26}{t:<8}{int(float(r['slots_per_frame'])):>6}{v[0]:>11.2f}{v[1]:>10.2f}{v[2]:>8.2f}{v[3]:>8.2f}"
                  f"{float(r['delivery_ratio']) * 100:>9.2f}%")
        if sc != "Random (mean)" and vals:
            same = all(all(abs(x - y) < 1e-6 for x, y in zip(vals[0], v)) for v in vals[1:])
            print(f"{'':<26}-> {'MATCH' if same else 'MISMATCH'}\n")
            bad += 0 if same else 1
        else:
            print()
    print("RESULT:", "all deterministic scenarios agree in MATLAB, ns-3 and Python" if bad == 0 else f"{bad} scenario(s) differ - paste this output")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
