#!/usr/bin/env python3
"""Evolution 3 -> EMANE.  Reads results/opt_n*.json (written by `python3 -m tdmaopt.hetero`) and writes a full EMANE
config set for ANY number of radios, one NEM per network namespace.

  radio i  ->  NEM id i+1  (radio 0 is the gateway, NEM 1; EMANE ids start at 1)
  control address 192.168.77.<id>, radio address 10.100.0.<id>
  schedule_good.xml : the optimizer's schedule (a radio may own several slots)
  schedule_bad.xml  : same, but two siblings (same parent) forced into the same slots -> deliberate collision
  scenario.eel      : pathloss events; link i-j is in range when distance <= min(range_i, range_j), as in the optimizer
  plan.json         : who talks to whom (used by the run script and the probe)
"""
import argparse
import json
import math
import os

OTA, EVT = "224.1.2.8:45702", "224.1.2.8:45703"
DTD = "file:///usr/share/emane/dtd"
PCR = "file:///usr/share/emane/xml/models/mac/tdmaeventscheduler/tdmabasemodelpcr.xml"
HDR = '<?xml version="1.0" encoding="UTF-8"?>\n'


def write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def schedule_xml(tx, frame, slot_us=1000, rate="10M", rx_only=()):
    """tx: {nem_id: [slot,...]}.  Transmit slots are listed; a radio that appears in at least one tx slot gets receive
    slots everywhere else.  A radio that NEVER transmits (the gateway) is unknown to the scheduler, so it must be given
    explicit <rx/> slots (rx_only) or it hears nothing."""
    by_slot = {}
    for nem, slots in tx.items():
        for s in slots:
            by_slot.setdefault(s, []).append(nem)
    lines = ["<emane-tdma-schedule>",
             f"  <structure frames='1' slots='{frame}' slotoverhead='0' slotduration='{slot_us}' bandwidth='1M'/>",
             f"  <multiframe frequency='2.4G' power='0' class='0' datarate='{rate}'>",
             "    <frame index='0'>"]
    for s in sorted(by_slot):
        lines.append(f"      <slot index='{s}' nodes='{','.join(str(n) for n in sorted(by_slot[s]))}'><tx/></slot>")
    for s in range(frame):
        if rx_only:
            lines.append(f"      <slot index='{s}' nodes='{','.join(str(n) for n in sorted(rx_only))}'><rx/></slot>")
    lines += ["    </frame>", "  </multiframe>", "</emane-tdma-schedule>"]
    return "\n".join(lines) + "\n"


def make_eel(pos, rng, in_db=80, out_db=200):
    ids = sorted(pos)
    lines = []
    for a in ids:
        pairs = " ".join(f"nem:{b},{in_db if math.dist(pos[a], pos[b]) <= min(rng[a], rng[b]) + 1e-9 else out_db}"
                         for b in ids if b != a)
        lines.append(f"0.0 nem:{a} pathloss {pairs}")
    return "\n".join(lines) + "\n"


def pick_collision_pair(layout):
    """Two radios with the same parent: if they share a slot, the parent cannot hear either (collision at the parent)."""
    best = None
    kids = {}
    for r in layout:
        if r["parent"] >= 0 and r["tx_slots"]:
            kids.setdefault(r["parent"], []).append(r)
    for p, ks in kids.items():
        if len(ks) < 2:
            continue
        ks.sort(key=lambda r: -len(r["tx_slots"]))
        a, b = ks[0], ks[1]
        score = (len(b["tx_slots"]), len(a["tx_slots"]))
        if best is None or score > best[0]:
            best = (score, p, a, b)
    return best


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("opt_json", help="results/opt_n*.json from tdmaopt.hetero")
    ap.add_argument("--out", required=True)
    ap.add_argument("--rate", default="10M")
    ap.add_argument("--evt-device", default="br0")
    ap.add_argument("--secs", type=int, default=15, help="probe duration used to compute packets sent")
    ap.add_argument("--load", type=float, default=0.5, help="offered load as a fraction of each radio's slot capacity")
    ap.add_argument("--slot-ms", type=float, default=10.0,
                    help="slot length in ms. 1 ms slots are too tight for WSL2 timers (EMANE reported late timer events and missed "
                         "rx slots); 10 ms slows the whole emulation 10x without changing the schedule")
    ap.add_argument("--gateway-beacon", action="store_true",
                    help="fallback: give the gateway its own extra tx slot (frame + 1) instead of explicit rx slots")
    a = ap.parse_args(argv)
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    d = json.load(open(a.opt_json, encoding="utf-8"))
    L = d["layout"]
    pos = {r["radio"] + 1: (r["x_m"], r["y_m"]) for r in L}
    rng = {r["radio"] + 1: r["range_m"] for r in L}
    tx = {r["radio"] + 1: list(r["tx_slots"]) for r in L if r["tx_slots"]}
    frame = int(d["frame"])
    ids = sorted(pos)

    silent = [n for n in ids if n not in tx]          # radios that never transmit (the gateway)
    if a.gateway_beacon:
        for n in silent:
            tx[n] = [frame]
        frame += 1
        silent = []
    write(f"{out}/schedule_good.xml", schedule_xml(tx, frame, slot_us=int(a.slot_ms * 1000), rate=a.rate, rx_only=silent))
    pair = pick_collision_pair(L)
    bad = {k: list(v) for k, v in tx.items()}
    plan = {"n": len(ids), "frame": frame, "goal": d.get("goal"), "best": d.get("best"),
            "slot_us": int(a.slot_ms * 1000),
            "links": [{"nem": r["radio"] + 1, "parent": r["parent"] + 1, "slots": r["tx_slots"],
                       "dist_m": r["link_m"],
                       # offered load = 80% of what the radio's own slots can carry (1 packet per slot, 1 ms slots)
                       "pps": round(a.load * len(r["tx_slots"]) * 1e6 / (a.slot_ms * 1000 * frame), 2),
                       "sent": int(round(a.load * len(r["tx_slots"]) * 1e6 / (a.slot_ms * 1000 * frame) * a.secs))}
                      for r in L if r["parent"] >= 0], "collision": None}
    if pair:
        _, p, ra, rb = pair
        na, nb = ra["radio"] + 1, rb["radio"] + 1
        bad[nb] = list(tx[na])[:len(tx[nb])]
        plan["collision"] = {"a": na, "b": nb, "parent": p + 1, "bad_slots_b": bad[nb]}
    for n in tx:
        if n not in bad:
            bad[n] = list(tx[n])
    write(f"{out}/schedule_bad.xml", schedule_xml(bad, frame, slot_us=int(a.slot_ms * 1000), rate=a.rate, rx_only=silent))
    write(f"{out}/scenario.eel", make_eel(pos, rng))
    write(f"{out}/plan.json", json.dumps(plan, indent=1))

    write(f"{out}/tdmaradiomodel.xml", HDR + f"""<!DOCTYPE mac SYSTEM "{DTD}/mac.dtd">
<mac library="tdmaeventschedulerradiomodel">
  <param name="fragmentcheckthreshold" value="2"/>
  <param name="fragmenttimeoutthreshold" value="5"/>
  <param name="neighbormetricdeletetime" value="60.0"/>
  <param name="neighbormetricupdateinterval" value="1.0"/>
  <param name="queue.aggregationenable" value="on"/>
  <param name="queue.aggregationslotthreshold" value="90.0"/>
  <param name="queue.depth" value="255"/>
  <param name="queue.fragmentationenable" value="on"/>
  <param name="queue.strictdequeueenable" value="off"/>
  <param name="pcrcurveuri" value="{PCR}"/>
</mac>
""")
    for n in ids:
        write(f"{out}/transport-{n}.xml", HDR + f"""<!DOCTYPE transport SYSTEM "{DTD}/transport.dtd">
<transport library="transvirtual">
  <param name="address" value="10.100.0.{n}"/>
  <param name="mask" value="255.255.255.0"/>
</transport>
""")
        write(f"{out}/nem-{n}.xml", HDR + f"""<!DOCTYPE nem SYSTEM "{DTD}/nem.dtd">
<nem>
  <transport definition="transport-{n}.xml"/>
  <mac definition="tdmaradiomodel.xml"/>
  <phy>
    <param name="fixedantennagain" value="0.0"/>
    <param name="fixedantennagainenable" value="on"/>
    <param name="bandwidth" value="1M"/>
    <param name="noisemode" value="all"/>
    <param name="propagationmodel" value="precomputed"/>
    <param name="systemnoisefigure" value="4.0"/>
    <param name="subid" value="7"/>
  </phy>
</nem>
""")
        write(f"{out}/platform-{n}.xml", HDR + f"""<!DOCTYPE platform SYSTEM "{DTD}/platform.dtd">
<platform>
  <param name="otamanagerchannelenable" value="on"/>
  <param name="otamanagergroup" value="{OTA}"/>
  <param name="otamanagerdevice" value="eth0"/>
  <param name="eventservicegroup" value="{EVT}"/>
  <param name="eventservicedevice" value="eth0"/>
  <param name="controlportendpoint" value="0.0.0.0:47000"/>
  <nem id="{n}" definition="nem-{n}.xml"/>
</platform>
""")
    write(f"{out}/eventservice.xml", HDR + f"""<!DOCTYPE eventservice SYSTEM "{DTD}/eventservice.dtd">
<eventservice>
  <param name="eventservicegroup" value="{EVT}"/>
  <param name="eventservicedevice" value="{a.evt_device}"/>
  <generator definition="eelgenerator.xml"/>
</eventservice>
""")
    write(f"{out}/eelgenerator.xml", HDR + f"""<!DOCTYPE eventgenerator SYSTEM "{DTD}/eventgenerator.dtd">
<eventgenerator library="eelgenerator">
  <param name="inputfile" value="{out}/scenario.eel"/>
  <paramlist name="loader">
    <item value="pathloss:eelloaderpathloss:delta"/>
  </paramlist>
</eventgenerator>
""")
    print(f"Wrote EMANE config set for {len(ids)} NEMs, frame {frame} slots, into {out}")
    if plan["collision"]:
        c = plan["collision"]
        print(f"Collision probe: NEM {c['a']} and NEM {c['b']} (parent NEM {c['parent']}) share slots {c['bad_slots_b']} in the bad schedule")


if __name__ == "__main__":
    main()
