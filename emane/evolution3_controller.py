import argparse
import json
import math
import re
import sys
import xml.etree.ElementTree as ET

from pathlib import Path
from collections import defaultdict


def walk_objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_objects(child)


def read_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def first_value(record, names, default=None):
    for name in names:
        if name in record and record[name] is not None:
            return record[name]
    return default


def as_int(value):
    try:
        if isinstance(value, str):
            match = re.search(r"-?\d+", value)
            return int(match.group()) if match else None
        return int(value)
    except (TypeError, ValueError):
        return None


def as_float(value, default=None):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


class PredictiveAdapter:
    def __init__(self, alpha=0.35):
        self.alpha = alpha
        self.pdr = {}
        self.queue = {}

    def update(self, radio, pdr, queue):
        old_pdr = self.pdr.get(radio, pdr)
        old_queue = self.queue.get(radio, queue)
        predicted_pdr = self.alpha * pdr + (1 - self.alpha) * old_pdr
        predicted_queue = self.alpha * queue + (1 - self.alpha) * old_queue
        self.pdr[radio] = predicted_pdr
        self.queue[radio] = predicted_queue
        return {
            "predicted_pdr": round(predicted_pdr, 6),
            "predicted_queue": round(predicted_queue, 3),
            "confidence": "low_single_snapshot"
        }


class RecoveryPlanner:
    def __init__(self, parents):
        self.parents = parents

    def gateway_distance(self, node):
        seen = set()
        distance = 0
        current = node

        while current in self.parents and current not in seen:
            seen.add(current)
            current = self.parents[current]
            distance += 1
            if current == 1:
                return distance

        return None

    def propose(self, node):
        old_parent = self.parents.get(node)
        node_distance = self.gateway_distance(node)

        if old_parent is None or node_distance is None:
            return {
                "node": node,
                "current_parent": old_parent,
                "recovery": "no_safe_parent_change",
                "reason": "parent route to gateway is unknown"
            }

        candidates = []
        for candidate in range(1, 13):
            if candidate in (node, old_parent):
                continue
            candidate_distance = self.gateway_distance(candidate)
            if candidate_distance is not None and candidate_distance < node_distance:
                candidates.append((candidate_distance, candidate))

        if not candidates:
            return {
                "node": node,
                "current_parent": old_parent,
                "recovery": "no_safe_parent_change",
                "reason": "no verified alternative parent in the known route graph"
            }

        candidates.sort()
        return {
            "node": node,
            "current_parent": old_parent,
            "candidate_parent": candidates[0][1],
            "recovery": "candidate_only",
            "reason": "candidate is closer to gateway; link connectivity still requires validation"
        }



class DistributedSlotCoordinator:
    def negotiate(self, assignments, slot_count, parents=None):
        parents = parents or {}

        def conflicts(a, b):
            if a == b:
                return True

            pa = parents.get(a)
            pb = parents.get(b)

            return (
                pa == b
                or pb == a
                or (pa is not None and pa == pb)
            )

        def count_conflicts(mapping):
            count = 0
            for nodes in mapping.values():
                unique = sorted(set(nodes))
                for i, a in enumerate(unique):
                    for b in unique[i + 1:]:
                        if conflicts(a, b):
                            count += 1
            return count

        collisions_before = count_conflicts(assignments)
        occupied = defaultdict(list)
        leases = defaultdict(list)
        capacity_exceeded = []

        transmissions = [
            (slot, node)
            for slot, nodes in sorted(assignments.items())
            for node in sorted(set(nodes))
        ]

        for preferred_slot, node in transmissions:
            candidates = [preferred_slot] + [
                slot for slot in range(slot_count)
                if slot != preferred_slot
            ]

            chosen = None

            for candidate in candidates:
                if candidate < 0 or candidate >= slot_count:
                    continue

                if node in occupied[candidate]:
                    continue

                if all(
                    not conflicts(node, other)
                    for other in occupied[candidate]
                ):
                    chosen = candidate
                    break

            if chosen is None:
                capacity_exceeded.append(node)
            else:
                occupied[chosen].append(node)
                leases[node].append(chosen)

        negotiated = {
            slot: sorted(nodes)
            for slot, nodes in occupied.items()
            if nodes
        }

        return {
            "assignments": negotiated,
            "leases": {
                str(node): sorted(slots)
                for node, slots in sorted(leases.items())
            },
            "lease_count": sum(len(slots) for slots in leases.values()),
            "collisions_before": collisions_before,
            "collisions_after": count_conflicts(negotiated),
            "slot_capacity": slot_count,
            "capacity_exceeded": sorted(capacity_exceeded)
        }


class EnergyEstimator:
    def estimate(self, tx_slots, rx_slots, total_slots, slot_us=10000):
        voltage = 3.3
        tx_ma = 120.0
        rx_ma = 50.0
        idle_ma = 5.0
        slot_seconds = slot_us / 1_000_000

        tx_time = tx_slots * slot_seconds
        rx_time = rx_slots * slot_seconds
        idle_time = max(0, total_slots - tx_slots - rx_slots) * slot_seconds

        energy_mwh = voltage * (
            tx_ma * tx_time +
            rx_ma * rx_time +
            idle_ma * idle_time
        ) / 3600.0

        return {
            "tx_slots": tx_slots,
            "rx_slots": rx_slots,
            "idle_slots": max(0, total_slots - tx_slots - rx_slots),
            "estimated_energy_mwh_per_frame": round(energy_mwh, 8),
            "assumptions": {
                "voltage_v": voltage,
                "tx_current_ma": tx_ma,
                "rx_current_ma": rx_ma,
                "idle_current_ma": idle_ma,
                "slot_duration_us": slot_us
            },
            "measurement_status": "model_estimate_not_hardware_measurement"
        }


class ClockGuardModel:
    def calculate(self, clock_records, frame_duration_us, base_guard_us=50.0):
        offsets = []
        drifts = []

        for record in clock_records:
            offset = as_float(first_value(
                record, ["clock_offset_us", "offset_us", "clock_offset"]
            ))
            drift = as_float(first_value(
                record, ["drift_ppm", "clock_drift_ppm", "drift"]
            ))
            if offset is not None:
                offsets.append(abs(offset))
            if drift is not None:
                drifts.append(abs(drift))

        if not offsets and not drifts:
            return {
                "recommended_guard_us": base_guard_us,
                "max_offset_us": None,
                "max_drift_ppm": None,
                "status": "fallback_guard_no_clock_telemetry"
            }

        max_offset = max(offsets, default=0.0)
        max_drift = max(drifts, default=0.0)
        drift_error = max_drift * frame_duration_us / 1_000_000.0
        guard = base_guard_us + max_offset + drift_error

        return {
            "recommended_guard_us": round(guard, 3),
            "max_offset_us": round(max_offset, 3),
            "max_drift_ppm": round(max_drift, 3),
            "status": "calculated_from_available_clock_metrics"
        }


def extract_metrics(data):
    output = {}

    radios = data.get("radios", {}) if isinstance(data, dict) else {}

    if isinstance(radios, dict):
        for radio_key, record in radios.items():
            radio_id = as_int(radio_key)

            if radio_id is None or not isinstance(record, dict):
                continue

            pdr = as_float(record.get("pdr"))
            queue = as_float(record.get("queue_packets"), 0.0)

            if pdr is None:
                continue

            if pdr > 1.0 and pdr <= 100.0:
                pdr /= 100.0

            nem_id = radio_id + 1

            if 2 <= nem_id <= 12:
                output[nem_id] = {
                    "pdr": max(0.0, min(1.0, pdr)),
                    "queue": max(0.0, queue)
                }

    return output


def extract_parents(plan, topology):
    parents = {}

    for source in (topology, plan):
        for record in walk_objects(source):
            node = as_int(first_value(
                record, ["nem_id", "nem", "node_id", "radio_id", "radio", "id"]
            ))
            parent = as_int(first_value(
                record, ["parent_nem", "parent_id", "parent"]
            ))

            if node is None or parent is None:
                continue

            if "nem_id" not in record and "nem" not in record:
                node += 1
                if parent != 1:
                    parent += 1

            if 2 <= node <= 12 and 1 <= parent <= 12 and node != parent:
                parents[node] = parent

    return parents



def extract_schedule(path):
    root = ET.parse(path).getroot()

    def local_tag(element):
        return element.tag.split("}")[-1].lower()

    structure = next(
        (item for item in root.iter() if local_tag(item) == "structure"),
        None
    )

    declared_slots = None
    if structure is not None:
        declared_slots = as_int(structure.attrib.get("slots"))

    assignments = defaultdict(list)
    rx_counts = defaultdict(int)
    tx_entries = 0
    rx_entries = 0
    tx_slot_entries = 0

    for slot in root.iter():
        if local_tag(slot) != "slot":
            continue

        index = as_int(slot.attrib.get("index"))
        if index is None:
            continue

        nodes = []
        for value in slot.attrib.get("nodes", "").split(","):
            value = value.strip()
            if value:
                node = as_int(value)
                if node is not None:
                    nodes.append(node)

        children = {local_tag(child) for child in slot}

        if "tx" in children:
            assignments[index].extend(nodes)
            tx_entries += len(nodes)
            tx_slot_entries += 1

        if "rx" in children:
            for node in nodes:
                rx_counts[node] += 1
                rx_entries += 1

    if declared_slots is None:
        declared_slots = max(
            [*assignments.keys(), -1]
        ) + 1

    assignments = {
        index: sorted(set(nodes))
        for index, nodes in assignments.items()
    }

    return {
        "root_tag": root.tag,
        "slot_elements": declared_slots,
        "assignments": assignments,
        "rx_counts": dict(rx_counts),
        "parsed_tx_elements": tx_entries,
        "tx_slot_entries": tx_slot_entries,
        "rx_entries": rx_entries
    }


def run_self_tests():
    predictor = PredictiveAdapter()
    prediction = predictor.update(2, 0.9, 4)
    assert prediction["predicted_pdr"] == 0.9

    recovery = RecoveryPlanner({2: 1, 3: 2, 4: 3})
    assert recovery.gateway_distance(4) == 3

    coordinator = DistributedSlotCoordinator()
    result = coordinator.negotiate({0: [2], 1: [3]}, 2)
    assert result["collisions_after"] == 0

    energy = EnergyEstimator().estimate(2, 3, 10)
    assert energy["estimated_energy_mwh_per_frame"] > 0

    clock = ClockGuardModel().calculate([], 130000)
    assert clock["recommended_guard_us"] == 50.0

    return 5


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topology", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--schedule", required=True)
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--out", default="results/evolution3-integrated")
    args = parser.parse_args()

    for name in ("topology", "plan", "schedule", "metrics"):
        if not Path(getattr(args, name)).is_file():
            raise FileNotFoundError(f"Missing {name} input: {getattr(args, name)}")

    test_count = run_self_tests()
    topology = read_json(args.topology)
    plan = read_json(args.plan)
    metrics_data = read_json(args.metrics)
    metrics = extract_metrics(metrics_data)
    parents = extract_parents(plan, topology)
    schedule = extract_schedule(args.schedule)

    if not metrics:
        raise RuntimeError(
            "No per-radio PDR metrics found. Check the metrics JSON field names."
        )

    if schedule["slot_elements"] == 0:
        raise RuntimeError(
            "Could not identify slot elements in the schedule XML; no schedule was changed."
        )

    predictor = PredictiveAdapter()
    predictions = {
        str(nem): predictor.update(
            nem, values["pdr"], values["queue"]
        )
        for nem, values in sorted(metrics.items())
    }

    recovery_planner = RecoveryPlanner(parents)
    recovery = []
    for nem, values in sorted(metrics.items()):
        if values["pdr"] < 0.50:
            recovery.append(recovery_planner.propose(nem))

    distributed = DistributedSlotCoordinator().negotiate(
        schedule["assignments"],
        schedule["slot_elements"],
        parents=parents
    )

    total_slots = schedule["slot_elements"]
    tx_per_nem = defaultdict(int)
    for nodes in distributed["assignments"].values():
        for nem in nodes:
            tx_per_nem[nem] += 1

    energy = {}
    for nem in range(1, 13):
        tx_count = tx_per_nem[nem]
        rx_count = schedule["rx_counts"].get(nem, 0)
        energy[str(nem)] = EnergyEstimator().estimate(
            tx_count, rx_count, total_slots
        )

    clock_records = [
        record for record in walk_objects(metrics_data)
        if any(key in record for key in (
            "clock_offset_us", "offset_us", "clock_offset",
            "drift_ppm", "clock_drift_ppm", "drift"
        ))
    ]
    clock = ClockGuardModel().calculate(
        clock_records, total_slots * 10000
    )

    policy = {
        "controller": "TDMA Evolution 3 integrated decision layer",
        "test_count": test_count,
        "topology_radios": 12,
        "input_schedule_slots": total_slots,
        "predictive_adaptation": predictions,
        "self_healing": {
            "low_pdr_threshold": 0.50,
            "proposals": recovery,
            "status": "candidate_routes_only_not_automatically_switched"
        },
        "distributed_scheduling": distributed,
        "energy_model": energy,
        "clock_synchronization": clock,
        "schedule_input": str(Path(args.schedule)),
        "schedule_change": "none",
        "automatic_emane_publish": False
    }

    report = {
        "experiment": "Evolution 3 integrated controller validation",
        "input_metrics_radios": len(metrics),
        "input_parent_routes": len(parents),
        "schedule_slots_detected": total_slots,
        "tx_elements_detected": schedule["parsed_tx_elements"],
        "tx_slot_entries_detected": schedule["tx_slot_entries"],
        "rx_entries_detected": schedule["rx_entries"],
        "distributed_leases": distributed["lease_count"],
        "capacity_exceeded": distributed["capacity_exceeded"],
        "distributed_slot_collisions_after": distributed["collisions_after"],
        "predictor_status": "single-snapshot baseline; needs time-series telemetry for validated forecasting",
        "self_healing_status": "candidate generation only; requires link-connectivity confirmation before route switching",
        "energy_status": "model estimate using assumed radio currents, not measured hardware energy",
        "clock_status": clock["status"],
        "emane_status": "existing live EMANE schedule left untouched",
        "validation": (
            "PASS"
            if (
                schedule["parsed_tx_elements"] > 0
                and distributed["lease_count"] == schedule["parsed_tx_elements"]
                and distributed["collisions_after"] == 0
                and not distributed["capacity_exceeded"]
            )
            else "FAIL_CHECK_SCHEDULE_OR_CAPACITY"
        )
    }

    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)

    (output / "evolution3_policy.json").write_text(
        json.dumps(policy, indent=2), encoding="utf-8"
    )
    (output / "evolution3_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    print("\n========== EVOLUTION 3 INTEGRATED VALIDATION ==========")
    print(f"Built-in checks:              {test_count}/{test_count} passed")
    print(f"Metrics radios:                {len(metrics)}")
    print(f"Known parent routes:           {len(parents)}")
    print(f"Schedule slots:                {total_slots}")
    print(f"TX elements parsed:            {schedule['parsed_tx_elements']}")
    print(f"Distributed collisions after: {distributed['collisions_after']}")
    print(f"Recovery proposals:            {len(recovery)}")
    print(f"Clock model:                   {clock['status']}")
    print(f"Energy model:                  estimated (not measured)")
    print(f"EMANE schedule modified:       NO")
    print(f"Validation:                    {report['validation']}")
    print(f"\nSaved: {output / 'evolution3_policy.json'}")
    print(f"Saved: {output / 'evolution3_report.json'}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
