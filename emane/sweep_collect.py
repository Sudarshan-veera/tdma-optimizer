#!/usr/bin/env python3
"""Helper for sweep_evo3.sh.
  sweep_collect.py plan  <plan.json> <load> <secs> <out_plan.json>     scale offered load (load = fraction of slot capacity)
  sweep_collect.py collect <plan.json> <dir> <csv> <load> <rep> <sched>  append one row per link to the CSV"""
import csv
import json
import os
import sys
import time

cmd = sys.argv[1]
if cmd == "plan":
    p = json.load(open(sys.argv[2]))
    load, secs = float(sys.argv[3]), float(sys.argv[4])
    for L in p["links"]:
        L["pps"] = round(load * len(L["slots"]) * 1e6 / (p["slot_us"] * p["frame"]), 2)
        L["sent"] = int(round(L["pps"] * secs))
    json.dump(p, open(sys.argv[5], "w"))
else:
    p = json.load(open(sys.argv[2]))
    d, path, load, rep, sched = sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6], sys.argv[7]
    new = not os.path.exists(path)
    c = p.get("collision") or {}
    tot_got = tot_sent = 0
    with open(path, "a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["time", "load", "rep", "sched", "nem", "parent", "slots", "sent", "got", "role"])
        for L in p["links"]:
            try:
                got = json.load(open(f"{d}/rx_{L['parent']}.json")).get(str(L["nem"]), 0)
            except OSError:
                got = 0
            role = "a" if L["nem"] == c.get("a") else "b" if L["nem"] == c.get("b") else ""
            w.writerow([int(time.time()), load, rep, sched, L["nem"], L["parent"],
                        "-".join(map(str, L["slots"])), L["sent"], got, role])
            tot_got += got
            tot_sent += L["sent"]
    print(f"   load {load} rep {rep} {sched:<4} overall delivery {100.0 * tot_got / max(tot_sent, 1):5.1f}%")
