import argparse
import csv
import json
import re
import subprocess
from pathlib import Path

import numpy as np

from tdmaopt.adaptive import AdaptiveTDMA
from tdmaopt.hetero import HChannel
from tdmaopt.schedule import conflict_graph, subtree_loads


class PlanNetwork:
    def __init__(self, topology, link_margin=0.9, interference=1.5):
        self.layout = sorted(
            topology["layout"],
            key=lambda row: int(row["radio"]),
        )

        self.radio_ids = [
            int(row["radio"])
            for row in self.layout
        ]

        if not self.radio_ids or self.radio_ids[0] != 0:
            raise ValueError("Radio 0 must be the gateway")

        if len(set(self.radio_ids)) != len(self.radio_ids):
            raise ValueError("Duplicate radio IDs in topology")

        self.index = {
            radio: index
            for index, radio in enumerate(self.radio_ids)
        }

        positions = np.asarray(
            [
                [row["x_m"], row["y_m"]]
                for row in self.layout
            ],
            dtype=float,
        )

        ranges = np.asarray(
            [row["range_m"] for row in self.layout],
            dtype=float,
        )

        parent_index = np.full(len(self.layout), -2, dtype=int)

        for index, row in enumerate(self.layout):
            parent_radio = int(row["parent"])

            if parent_radio < 0:
                if int(row["radio"]) != 0:
                    raise ValueError(
                        "Only radio 0 may be a gateway"
                    )
                parent_index[index] = -1
            else:
                if parent_radio not in self.index:
                    raise ValueError(
                        f"Unknown parent radio {parent_radio}"
                    )

                parent_index[index] = self.index[parent_radio]

        self.channel = HChannel(
            positions,
            ranges,
            ri_factor=interference,
            comm_scale=link_margin,
        )

        graph_index = conflict_graph(
            self.channel,
            parent_index,
        )

        self.adjacency = {
            self.radio_ids[node]: {
                self.radio_ids[neighbour]
                for neighbour in neighbours
            }
            for node, neighbours in graph_index.items()
        }

        demand_index = subtree_loads(parent_index)

        self.demand = {
            self.radio_ids[node]: int(value)
            for node, value in demand_index.items()
        }

        layout_by_radio = {
            int(row["radio"]): row
            for row in self.layout
        }

        self.slots = {
            radio: sorted(
                int(slot)
                for slot in layout_by_radio[radio].get("tx_slots", [])
            )
            for radio in self.demand
        }

    def _graph(self):
        return {
            radio: set(neighbours)
            for radio, neighbours in self.adjacency.items()
        }


def read_queue_snapshot(path):
    if path is None:
        return {}

    data = json.loads(
        Path(path).read_text(encoding="utf-8")
    )

    if "radios" in data:
        data = data["radios"]

    if not isinstance(data, dict):
        raise ValueError("Queue snapshot must be a JSON object")

    result = {}

    for radio_text, value in data.items():
        radio = int(radio_text)

        if isinstance(value, dict):
            queue = value.get("queue_packets")
            quality = value.get("link_quality")
        else:
            queue = value
            quality = None

        if queue is None:
            raise ValueError(
                f"Radio {radio} is missing queue_packets"
            )

        queue = int(queue)

        if queue < 0:
            raise ValueError(
                f"Radio {radio} has a negative queue depth"
            )

        if quality is not None:
            quality = float(quality)

            if not 0 <= quality <= 1:
                raise ValueError(
                    f"Radio {radio} link_quality must be between 0 and 1"
                )

        result[radio] = {
            "queue_packets": queue,
            "link_quality": quality,
        }

    return result


def measure_pdr(emane_plan, rx_dir):
    rx_dir = Path(rx_dir)
    measurements = {}

    for link in emane_plan["links"]:
        nem = int(link["nem"])
        parent_nem = int(link["parent"])
        sent = int(link["sent"])

        if sent <= 0:
            raise ValueError(
                f"NEM {nem} has invalid sent count {sent}"
            )

        rx_file = rx_dir / f"rx_{parent_nem}.json"

        if not rx_file.is_file():
            raise FileNotFoundError(
                f"Missing receiver counter file: {rx_file}"
            )

        counts = json.loads(
            rx_file.read_text(encoding="utf-8")
        )

        received = int(
            counts.get(str(nem), counts.get(nem, 0))
        )

        received = min(received, sent)
        radio = nem - 1

        measurements[radio] = {
            "sent": sent,
            "received": received,
            "pdr": received / sent,
        }

    return measurements


def measure_pdr_csv(emane_plan, csv_path, load, rep, schedule):
    measurements = {}
    expected = {
        (int(link["nem"]), int(link["parent"]))
        for link in emane_plan["links"]
    }

    with open(csv_path, newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        required = {"load", "rep", "sched", "nem", "parent", "sent", "got"}

        if not required.issubset(reader.fieldnames or []):
            raise ValueError("CSV is missing required columns")

        for row in reader:
            if row["load"] != str(load):
                continue
            if int(row["rep"]) != int(rep):
                continue
            if row["sched"] != schedule:
                continue

            nem = int(row["nem"])
            parent = int(row["parent"])
            sent = int(row["sent"])
            received = int(row["got"])

            if (nem, parent) not in expected:
                raise ValueError(f"Unexpected link: NEM {nem}, parent {parent}")

            if nem - 1 in measurements:
                raise ValueError(f"Duplicate measurement for NEM {nem}")

            if sent <= 0 or received < 0 or received > sent:
                raise ValueError(f"Invalid packet counts for NEM {nem}")

            measurements[nem - 1] = {
                "sent": sent,
                "received": received,
                "pdr": received / sent,
                "measurement_source": "sweep_csv"
            }

    expected_radios = {nem - 1 for nem, parent in expected}

    if set(measurements) != expected_radios:
        missing = sorted(expected_radios - set(measurements))
        raise ValueError(f"Incomplete CSV batch. Missing radios: {missing}")

    return measurements


def update_schedule_xml(tx_by_nem, nem_ids, frame, rate):
    lines = [
        "<emane-tdma-schedule>",
        (
            f"  <multiframe frequency='2.4G' power='0' "
            f"class='0' datarate='{rate}'>"
        ),
        "    <frame index='0'>",
    ]

    for slot in range(frame):
        for nem in nem_ids:
            kind = (
                "tx"
                if slot in tx_by_nem.get(nem, [])
                else "rx"
            )

            lines.append(
                f"      <slot index='{slot}' nodes='{nem}'>"
                f"<{kind}/></slot>"
            )

    lines.extend([
        "    </frame>",
        "  </multiframe>",
        "</emane-tdma-schedule>",
    ])

    return "\n".join(lines) + "\n"


def full_schedule_xml(tx_by_nem, nem_ids, frame, slot_us, rate):
    by_slot = {}

    for nem, assigned_slots in tx_by_nem.items():
        for slot in assigned_slots:
            by_slot.setdefault(slot, []).append(nem)

    silent = sorted(
        nem
        for nem in nem_ids
        if not tx_by_nem.get(nem)
    )

    lines = [
        "<emane-tdma-schedule>",
        (
            f"  <structure frames='1' slots='{frame}' "
            f"slotoverhead='0' slotduration='{slot_us}' "
            "bandwidth='1M'/>"
        ),
        (
            f"  <multiframe frequency='2.4G' power='0' "
            f"class='0' datarate='{rate}'>"
        ),
        "    <frame index='0'>",
    ]

    for slot in sorted(by_slot):
        nodes = ",".join(
            str(nem)
            for nem in sorted(by_slot[slot])
        )

        lines.append(
            f"      <slot index='{slot}' nodes='{nodes}'>"
            "<tx/></slot>"
        )

    if silent:
        silent_nodes = ",".join(map(str, silent))

        for slot in range(frame):
            lines.append(
                f"      <slot index='{slot}' "
                f"nodes='{silent_nodes}'><rx/></slot>"
            )

    lines.extend([
        "    </frame>",
        "  </multiframe>",
        "</emane-tdma-schedule>",
    ])

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--topology", required=True)
    parser.add_argument("--emane-plan", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--rx-dir")
    group.add_argument("--csv")
    parser.add_argument("--csv-load")
    parser.add_argument("--csv-rep", type=int)
    parser.add_argument("--csv-schedule", choices=["good", "bad"])
    parser.add_argument("--queue-file")
    parser.add_argument("--out", default="results/emane-adaptive")
    parser.add_argument("--interface", default="br0")
    parser.add_argument("--link-margin", type=float, default=0.9)
    parser.add_argument("--interference", type=float, default=1.5)
    parser.add_argument("--max-slots", type=int, default=32)
    parser.add_argument("--rate", default="10M")
    parser.add_argument("--apply", action="store_true")

    args = parser.parse_args()

    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?[GMK]?", args.rate):
        raise ValueError("Invalid EMANE data rate")

    topology = json.loads(
        Path(args.topology).read_text(encoding="utf-8")
    )

    emane_plan = json.loads(
        Path(args.emane_plan).read_text(encoding="utf-8")
    )

    network = PlanNetwork(
        topology,
        link_margin=args.link_margin,
        interference=args.interference,
    )

    if args.csv:
        if args.csv_load is None or args.csv_rep is None or args.csv_schedule is None:
            raise ValueError("CSV requires --csv-load, --csv-rep and --csv-schedule")

        pdr_data = measure_pdr_csv(
            emane_plan,
            args.csv,
            args.csv_load,
            args.csv_rep,
            args.csv_schedule,
        )
    else:
        pdr_data = measure_pdr(emane_plan, args.rx_dir)

    queues = read_queue_snapshot(args.queue_file)

    unknown_radios = set(queues) - set(network.demand)

    if unknown_radios:
        raise ValueError(
            f"Queue snapshot contains unknown radios: {sorted(unknown_radios)}"
        )

    controller = AdaptiveTDMA(
        network,
        max_slots_per_radio=args.max_slots,
    )

    for radio in sorted(network.demand):
        if radio not in pdr_data:
            raise ValueError(
                f"No EMANE PDR measurement for radio {radio}"
            )

        pdr = pdr_data[radio]["pdr"]
        queue_entry = queues.get(radio)

        if queue_entry is None:
            queue_packets = network.demand[radio]
            queue_source = "baseline_subtree_demand"
            quality = pdr
        else:
            queue_packets = queue_entry["queue_packets"]
            queue_source = "queue_snapshot"
            quality = (
                pdr
                if queue_entry["link_quality"] is None
                else queue_entry["link_quality"]
            )

        controller.update_radio(
            radio_id=radio,
            queue_packets=queue_packets,
            pdr=pdr,
            link_quality=quality,
        )

        pdr_data[radio]["queue_packets"] = queue_packets
        pdr_data[radio]["queue_source"] = queue_source
        pdr_data[radio]["link_quality_used"] = quality

    report = controller.adapt()

    original_frame = int(emane_plan["frame"])
    calculated_frame = int(report["frame_slots"])

    if calculated_frame > original_frame:
        frame = calculated_frame
        mode = "full"
    else:
        frame = original_frame
        mode = "update"

    tx_by_nem = {
        radio + 1: list(report["slots"].get(radio, []))
        for radio in network.demand
    }

    nem_ids = sorted(
        radio + 1
        for radio in network.radio_ids
    )

    if mode == "update":
        xml = update_schedule_xml(
            tx_by_nem,
            nem_ids,
            frame,
            args.rate,
        )
    else:
        xml = full_schedule_xml(
            tx_by_nem,
            nem_ids,
            frame,
            int(emane_plan["slot_us"]),
            args.rate,
        )

    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)

    xml_path = output_dir / "schedule_adaptive.xml"
    report_path = output_dir / "adaptive_report.json"

    xml_path.write_text(
        xml,
        encoding="utf-8",
    )

    result = {
        "mode": mode,
        "original_frame_slots": original_frame,
        "calculated_frame_slots": calculated_frame,
        "applied_frame_slots": frame,
        "changed_radios": report["changed_radios"],
        "changed_radio_count": report["changed_radio_count"],
        "moved_slot_assignments": report["moved_slot_assignments"],
        "fixed_radios": report.get("fixed_radios", 0),
        "conflict_violations": report["violations"],
        "per_radio": pdr_data,
        "tx_slots_by_nem": {
            str(nem): slots
            for nem, slots in tx_by_nem.items()
        },
        "schedule_xml": str(xml_path),
        "applied": False,
    }

    report_path.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    print("Adaptive TDMA report")
    print("--------------------")
    print("Schedule mode:", mode)
    print("Original frame:", original_frame)
    print("New frame:", frame)
    print("Changed radios:", report["changed_radios"])
    print("Moved slot assignments:", report["moved_slot_assignments"])
    print("Conflict violations:", report["violations"])
    print("XML file:", xml_path)
    print("Report file:", report_path)

    if report["violations"] != 0:
        raise RuntimeError("Refusing to publish a conflicting schedule")

    if args.apply:
        command = [
            "emaneevent-tdmaschedule",
            str(xml_path),
            "-i",
            args.interface,
        ]

        print("\nPublishing schedule:")
        print(" ".join(command))

        subprocess.run(
            command,
            check=True,
        )

        result["applied"] = True

        report_path.write_text(
            json.dumps(result, indent=2),
            encoding="utf-8",
        )

        print("\nSchedule event submitted successfully.")
        print("Check the NEM scheduler acceptance counters before claiming it was applied.")


if __name__ == "__main__":
    main()
