#!/usr/bin/env python3
"""
EMANE bridge: schedule.json (from tdma_brain.py) -> EMANE artefacts
  * schedule.xml : TDMA schedule consumed by `emaneevent-tdmaschedule`
  * scenario.eel : pathloss events so EMANE's radio reach matches the Brain's range model

Mapping: Node_NN -> NEM id NN.  One frame, one multiframe.  Slot i lists every NEM that
transmits in slot i (spatial reuse = several NEMs per slot).  EMANE auto-fills all slots
not listed for a NEM as receive slots, so only transmit slots are emitted.
"""
import argparse
import json
import math
import re


def nem_id(name: str) -> int:
    nums = re.findall(r"\d+", name)
    if not nums:
        raise ValueError(f"Cannot derive an NEM id from node name {name!r}")
    return int(nums[-1])


def make_schedule_xml(data, slot_us=1000, overhead_us=0, freq="2.4G", rate="1M", bandwidth="1M"):
    by_slot = {}
    for name, s in data["slots"].items():
        by_slot.setdefault(s, []).append(nem_id(name))
    lines = ["<emane-tdma-schedule>",
             f"  <structure frames='1' slots='{data['frame_length']}' "
             f"slotoverhead='{overhead_us}' slotduration='{slot_us}' bandwidth='{bandwidth}'/>",
             f"  <multiframe frequency='{freq}' power='0' class='0' datarate='{rate}'>",
             "    <frame index='0'>"]
    for s in sorted(by_slot):
        nodes = ",".join(str(n) for n in sorted(by_slot[s]))
        lines.append(f"      <slot index='{s}' nodes='{nodes}'><tx/></slot>")
    lines += ["    </frame>", "  </multiframe>", "</emane-tdma-schedule>"]
    return "\n".join(lines) + "\n"


def make_eel(data, in_range_db=80, out_range_db=200):
    c, r = data["coords"], data["range"]
    names = sorted(c, key=nem_id)
    return "".join(
        f"0.0 nem:{nem_id(a)} pathloss nem:{nem_id(b)},"
        f"{in_range_db if math.dist(c[a], c[b]) <= r else out_range_db}\n"
        for a in names for b in names if a != b)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("schedule_json")
    p.add_argument("--xml", default="schedule.xml")
    p.add_argument("--eel", default="scenario.eel")
    p.add_argument("--slot-us", type=int, default=1000, help="slot duration in microseconds (1 ms)")
    a = p.parse_args(argv)
    with open(a.schedule_json, encoding="utf-8") as fh:
        data = json.load(fh)
    with open(a.xml, "w", encoding="utf-8") as fh:
        fh.write(make_schedule_xml(data, slot_us=a.slot_us))
    with open(a.eel, "w", encoding="utf-8") as fh:
        fh.write(make_eel(data))
    print(f"Wrote {a.xml} and {a.eel}")


if __name__ == "__main__":
    main()
