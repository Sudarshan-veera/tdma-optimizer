#!/usr/bin/env python3
"""
schedule.json (from tdma_brain.py) -> schedule_sim.csv, the input for the ns-3 and MATLAB simulators.

    python tdma_brain.py --json-out schedule.json
    python sim/export_for_sims.py schedule.json sim/schedule_sim.csv

CSV columns: name,x,y,slot   (one row per radio; comment lines start with #)
"""
import argparse
import json


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("schedule_json")
    ap.add_argument("out_csv")
    a = ap.parse_args(argv)
    with open(a.schedule_json, encoding="utf-8") as fh:
        d = json.load(fh)
    names = sorted(d["coords"])
    with open(a.out_csv, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"# range={d['range']} frame_length={d['frame_length']} optimal={d['optimal']}\n")
        fh.write("name,x,y,slot\n")
        for n in names:
            x, y = d["coords"][n]
            fh.write(f"{n},{x},{y},{d['slots'][n]}\n")
    print(f"wrote {a.out_csv} ({len(names)} radios, frame length {d['frame_length']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
