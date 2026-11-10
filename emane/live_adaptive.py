#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import subprocess
import time
from pathlib import Path

from tdmaopt.adaptive import AdaptiveTDMA
from tdmaopt.evolution import LiveAdaptiveRuntime, OnlineMetricPredictor
from adaptive_bridge import PlanNetwork, full_schedule_xml, update_schedule_xml


def read_metrics(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "radios" in data:
        data = data["radios"]
    if not isinstance(data, dict):
        raise ValueError("metrics file must contain a JSON object keyed by radio ID")
    result = {}
    for radio_text, metric in data.items():
        if not isinstance(metric, dict):
            raise ValueError(f"metrics for radio {radio_text} must be an object")
        required = {"queue_packets", "pdr"}
        if not required.issubset(metric):
            raise ValueError(f"radio {radio_text} requires queue_packets and pdr")
        result[int(radio_text)] = {
            "queue_packets": int(metric["queue_packets"]),
            "pdr": float(metric["pdr"]),
            "link_quality": float(metric.get("link_quality", metric["pdr"])),
        }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topology", required=True)
    parser.add_argument("--emane-plan", required=True)
    parser.add_argument("--metrics-file", required=True)
    parser.add_argument("--out", default="results/emane-live-adaptive")
    parser.add_argument("--interface", default="br0")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--cycles", type=int, default=0)
    parser.add_argument("--max-slots", type=int, default=32)
    parser.add_argument("--max-changed-radios", type=int, default=None)
    parser.add_argument("--rate", default="10M")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    topology = json.loads(Path(args.topology).read_text(encoding="utf-8"))
    plan = json.loads(Path(args.emane_plan).read_text(encoding="utf-8"))
    network = PlanNetwork(topology)
    controller = AdaptiveTDMA(network, max_slots_per_radio=args.max_slots)
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    original_frame = int(plan["frame"])
    slot_us = int(plan["slot_us"])
    nem_ids = [radio + 1 for radio in network.radio_ids]

    def publish(report):
        calculated = int(report["frame_slots"])
        frame = max(original_frame, calculated)
        tx_by_nem = {radio + 1: list(report["slots"].get(radio, [])) for radio in network.demand}
        if frame > original_frame:
            xml = full_schedule_xml(tx_by_nem, nem_ids, frame, slot_us, args.rate)
        else:
            xml = update_schedule_xml(tx_by_nem, nem_ids, frame, args.rate)
        xml_path = output / "schedule_live.xml"
        xml_path.write_text(xml, encoding="utf-8")
        result = {
            "frame_slots": frame,
            "changed_radios": report["changed_radios"],
            "moved_slot_assignments": report["moved_slot_assignments"],
            "conflict_violations": report["violations"],
            "applied": False,
            "schedule_xml": str(xml_path),
        }
        if args.apply:
            subprocess.run(["emaneevent-tdmaschedule", str(xml_path), "-i", args.interface], check=True)
            result["applied"] = True
        (output / "live_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))

    runtime = LiveAdaptiveRuntime(
        controller,
        metrics_provider=lambda: read_metrics(args.metrics_file),
        publisher=publish,
        max_changed_radios=args.max_changed_radios,
        predictor=OnlineMetricPredictor(),
    )
    cycle = 0
    while args.cycles == 0 or cycle < args.cycles:
        result = runtime.step()
        print(json.dumps({"cycle": result["cycle"], "published": result["published"], "changed": result["report"]["changed_radio_count"], "violations": result["report"]["violations"]}))
        cycle += 1
        if args.cycles == 0 or cycle < args.cycles:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
