import argparse
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import numpy as np

from tdmaopt.phy import Channel, PHY, phy_for_range


def parse_nodes(value):
    return [
        int(x.strip())
        for x in value.split(",")
        if x.strip()
    ]


def main():
    parser = argparse.ArgumentParser(
        description="Monte Carlo Rayleigh/Rician TDMA PHY experiment"
    )
    parser.add_argument("--topology", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--schedule", required=True)
    parser.add_argument("--frames", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--out", default="results/phy-fading-study")
    args = parser.parse_args()

    if args.frames < 100:
        raise ValueError("Use at least 100 Monte Carlo frames")

    topology = json.loads(Path(args.topology).read_text())
    plan = json.loads(Path(args.plan).read_text())

    layout = sorted(
        topology["layout"],
        key=lambda row: int(row["radio"])
    )

    positions = np.asarray(
        [[row["x_m"], row["y_m"]] for row in layout],
        dtype=float
    )

    links = {
        int(link["nem"]): {
            "parent": int(link["parent"])
        }
        for link in plan["links"]
    }

    if len(links) != 11:
        raise RuntimeError("Expected 11 transmitting NEMs")

    max_distance = 0.0

    for nem, link in links.items():
        tx = nem - 1
        rx = link["parent"] - 1

        if tx >= len(positions) or rx < 0 or rx >= len(positions):
            raise RuntimeError(f"Invalid NEM mapping for link {nem}")

        distance = float(np.linalg.norm(positions[tx] - positions[rx]))
        max_distance = max(max_distance, distance)

    root = ET.parse(args.schedule).getroot()
    structure = root.find("structure")
    frame_node = root.find(".//frame")

    if structure is None or frame_node is None:
        raise RuntimeError("Schedule XML is missing structure or frame")

    frame_slots = int(structure.attrib["slots"])
    tx_by_slot = defaultdict(list)

    for slot_node in frame_node.findall("slot"):
        if slot_node.find("tx") is None:
            continue

        slot = int(slot_node.attrib["index"])

        if not 0 <= slot < frame_slots:
            raise RuntimeError(f"Invalid slot index: {slot}")

        for nem in parse_nodes(slot_node.attrib.get("nodes", "")):
            if nem not in links:
                raise RuntimeError(f"Unexpected transmitting NEM: {nem}")
            tx_by_slot[slot].append(nem)

    if not tx_by_slot:
        raise RuntimeError("No TX slots found in schedule")

    base_phy = PHY(
        noise_dbm=-100.0,
        sens_dbm=-90.0,
        beta_db=8.0,
        sigma_db=0.0,
    )

    phy = phy_for_range(max_distance * 1.05, base_phy)

    models = [
        ("none", 3.0),
        ("rayleigh", 3.0),
        ("rician", 3.0),
    ]

    results = {}

    print("\n========== PHY FADING MONTE CARLO ==========")
    print("Topology radios:", len(layout))
    print("Schedule frame slots:", frame_slots)
    print("Concurrent TX slots:", len(tx_by_slot))
    print("Maximum parent-link distance:", round(max_distance, 2), "m")
    print("Monte Carlo frames per model:", args.frames)
    print("\nPHY transmit power:", round(phy.pt_dbm, 2), "dBm")
    print("SINR threshold:", phy.beta_db, "dB")

    for model_index, (model, k_factor) in enumerate(models):
        sent = defaultdict(int)
        received = defaultdict(int)

        for frame in range(args.frames):
            channel = Channel(
                positions,
                phy,
                model="sinr",
                fading=model,
                rician_k=k_factor,
                fading_seed=args.seed + model_index * 100000 + frame,
            )

            for slot in sorted(tx_by_slot):
                active_nems = tx_by_slot[slot]
                txset = {nem - 1 for nem in active_nems}

                for nem in active_nems:
                    parent = links[nem]["parent"]
                    sent[nem] += 1

                    if channel.success(nem - 1, parent - 1, txset):
                        received[nem] += 1

        per_link = {}

        for nem in sorted(links):
            ratio = received[nem] / sent[nem] if sent[nem] else 0.0
            per_link[str(nem)] = {
                "sent": sent[nem],
                "received": received[nem],
                "pdr": ratio,
            }

        total_sent = sum(sent.values())
        total_received = sum(received.values())
        overall = total_received / total_sent

        results[model] = {
            "rician_k": k_factor if model == "rician" else None,
            "frames": args.frames,
            "total_sent": total_sent,
            "total_received": total_received,
            "overall_pdr": overall,
            "per_link": per_link,
        }

        print(
            f"{model:<10} "
            f"{total_received:>8}/{total_sent:<8} "
            f"PDR={overall:.4%}"
        )

    output = {
        "experiment": "Monte Carlo block-fading PHY study",
        "not_live_emane_measurement": True,
        "seed": args.seed,
        "frame_slots": frame_slots,
        "frames_per_model": args.frames,
        "max_link_distance_m": max_distance,
        "phy": {
            "tx_dbm": phy.pt_dbm,
            "noise_dbm": phy.noise_dbm,
            "sensitivity_dbm": phy.sens_dbm,
            "sinr_threshold_db": phy.beta_db,
            "path_loss_exponent": phy.n,
        },
        "results": results,
    }

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "fading_report.json"
    report_path.write_text(json.dumps(output, indent=2))

    print("\nReport saved:", report_path)


if __name__ == "__main__":
    main()
