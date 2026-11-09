#!/usr/bin/env python3
"""
schedule.json (from tdma_brain.py) -> a complete EMANE config set, one NEM per network namespace.

Writes into --out:
  schedule_good.xml   the Brain's schedule (TDMA full schedule event)
  schedule_bad.xml    same schedule but Node_03 forced into Node_01's slot: a hidden-terminal
                      pair (01 and 03 are 600 m apart, both hear Node_02) -> deliberate collision
  scenario.eel        pathloss events (80 dB in range, 200 dB out of range)
  platform-N.xml, nem-N.xml, transport-N.xml, tdmaradiomodel.xml
  eventservice.xml, eelgenerator.xml
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import emane_bridge as eb  # noqa: E402

OTA = "224.1.2.8:45702"
EVT = "224.1.2.8:45703"
DTD = "file:///usr/share/emane/dtd"
PCR = "file:///usr/share/emane/xml/models/mac/tdmaeventscheduler/tdmabasemodelpcr.xml"
HDR = '<?xml version="1.0" encoding="UTF-8"?>\n'


def write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("schedule_json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--rate", default="10M", help="slot data rate (10M gives ~1.2 kB per 1 ms slot)")
    ap.add_argument("--evt-device", default="br0", help="device the event service uses")
    a = ap.parse_args(argv)
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    with open(a.schedule_json, encoding="utf-8") as fh:
        data = json.load(fh)
    ids = sorted(eb.nem_id(n) for n in data["coords"])

    write(f"{out}/schedule_good.xml", eb.make_schedule_xml(data, rate=a.rate))
    bad = dict(data, slots=dict(data["slots"]))
    bad["slots"]["Node_03"] = bad["slots"]["Node_01"]
    write(f"{out}/schedule_bad.xml", eb.make_schedule_xml(bad, rate=a.rate))
    write(f"{out}/scenario.eel", eb.make_eel(data))

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
    print(f"Wrote EMANE config set for {len(ids)} NEMs into {out}")


if __name__ == "__main__":
    main()
