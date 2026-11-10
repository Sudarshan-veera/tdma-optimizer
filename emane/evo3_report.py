#!/usr/bin/env python3
"""Per-link delivery table for one phase.  usage: evo3_report.py plan.json <dir with rx_<nem>.json> <label>"""
import json
import sys

plan = json.load(open(sys.argv[1]))
d, label = sys.argv[2], sys.argv[3]
rows, worst = [], 100.0
print(f"\n[{label}]  per-link delivery (packets heard by the parent / packets sent)")
print(f"{'radio':>5} {'parent':>6} {'slots':<14} {'dist m':>7} {'got':>5} {'sent':>5} {'loss %':>7}")
tot_got = tot_sent = 0
for L in plan["links"]:
    try:
        got = json.load(open(f"{d}/rx_{L['parent']}.json")).get(str(L["nem"]), 0)
    except OSError:
        got = 0
    SENT = L["sent"]
    loss = 100.0 * (1 - got / SENT)
    worst = min(worst, 100 - loss)
    tot_got += got
    tot_sent += SENT
    mark = ""
    c = plan.get("collision")
    if c and L["nem"] in (c["a"], c["b"]):
        mark = "  <- collision pair" if label != "good" and label != "good_again" else "  (pair under test)"
    print(f"{L['nem']:>5} {L['parent']:>6} {str(L['slots']):<14} {L['dist_m']:>7} {got:>5} {SENT:>5} {loss:>7.1f}{mark}")
print(f"overall delivery {100.0 * tot_got / tot_sent:.1f}%   worst link {worst:.1f}%")
