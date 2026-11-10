import json
import math
import random
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from adaptive_bridge import PlanNetwork, measure_pdr
from tdmaopt.evolution import MultiHopRouting, EnergyProfile, EnergyModel


ROOT = Path.cwd()
TOPOLOGY_FILE = ROOT / "results/opt_n12.json"
PLAN_FILE = ROOT / "results/emane-evidence/plan.json"
SCHEDULE_FILE = (
    ROOT /
    "results/emane-live-fresh-20261110-163136/adaptive/schedule_live.xml"
)

CONTAINER = "tdma-adaptive-live"
SAMPLE_COUNT = 4
SLOT_US = 10000

# Illustrative radio power profile.
# Replace these values with measured radio specifications when available.
ENERGY_PROFILE = EnergyProfile(
    tx_w=1.20,
    rx_w=0.90,
    idle_w=0.25,
    sleep_w=0.03
)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    Path(path).write_text(
        json.dumps(data, indent=2),
        encoding="utf-8"
    )


def linear_forecast(values):
    if len(values) < 3:
        raise ValueError("At least three real observations are required")

    count = len(values)
    xs = list(range(count))
    mean_x = sum(xs) / count
    mean_y = sum(values) / count

    denominator = sum((x - mean_x) ** 2 for x in xs)

    slope = sum(
        (xs[i] - mean_x) * (values[i] - mean_y)
        for i in range(count)
    ) / denominator

    intercept = mean_y - slope * mean_x
    prediction = intercept + slope * count

    return {
        "last_observed": round(values[-1], 6),
        "predicted_next": round(max(0.0, min(1.0, prediction)), 6),
        "trend_per_window": round(slope, 8),
        "observation_count": count
    }


def collect_samples(output_dir):
    samples = []

    for index in range(1, SAMPLE_COUNT + 1):
        sample_name = f"sample-{index:02d}"
        sample_dir = output_dir / sample_name
        sample_dir.mkdir(parents=True, exist_ok=True)
        relative_path = str(sample_dir.relative_to(ROOT))

        print(f"\nCollecting real EMANE window {index}/{SAMPLE_COUNT}...")

        subprocess.run(
            [
                "docker", "exec", CONTAINER,
                "bash",
                "/work/emane/collect_live_snapshot.sh",
                relative_path
            ],
            check=True
        )

        sample_dir = ROOT / relative_path
        sample_plan_file = sample_dir / "plan.json"

        if not sample_plan_file.exists():
            raise RuntimeError(
                f"Snapshot plan was not created: {sample_plan_file}"
            )

        sample_plan = read_json(sample_plan_file)
        topology = read_json(TOPOLOGY_FILE)
        network = PlanNetwork(topology)

        measurements = measure_pdr(sample_plan, sample_dir)

        radio_metrics = {}

        for radio in sorted(network.demand):
            if radio not in measurements:
                raise RuntimeError(
                    f"Missing received-packet measurement for radio {radio}"
                )

            result = measurements[radio]
            pdr = float(result["pdr"])

            radio_metrics[str(radio)] = {
                "sent": int(result["sent"]),
                "received": int(result["received"]),
                "pdr": pdr,
                "queue_packets": int(network.demand[radio]),
                "queue_source": "topology_subtree_demand_estimate"
            }

        snapshot = {
            "sample": index,
            "timestamp": datetime.now().astimezone().isoformat(),
            "radios": radio_metrics
        }

        write_json(sample_dir / "metrics.json", snapshot)
        samples.append(snapshot)

        total_sent = sum(x["sent"] for x in radio_metrics.values())
        total_received = sum(x["received"] for x in radio_metrics.values())

        print(
            f"Window {index}: "
            f"{total_received}/{total_sent} packets received"
        )

    return samples


def predictive_adaptation(samples):
    radio_ids = sorted(
        samples[0]["radios"],
        key=int
    )

    predictions = {}

    for radio in radio_ids:
        history = [
            float(sample["radios"][radio]["pdr"])
            for sample in samples
        ]

        predictions[radio] = linear_forecast(history)

    return {
        "status": "multi_window_real_emane_measurement",
        "windows": len(samples),
        "pdr_forecasts": predictions,
        "queue_forecast_status": (
            "not_forecast: queue values are topology demand estimates, "
            "not measured MAC queue telemetry"
        )
    }


def self_healing_validation():
    # Fault-injection graph:
    # 3 -> 2 -> 1 -> gateway is the original path.
    # 3 -> 1 is the available alternate path.
    links = {
        0: {},
        1: {0: 0.99},
        2: {1: 0.98},
        3: {2: 0.97, 1: 0.40}
    }

    router = MultiHopRouting(links, gateway=0)

    original_path = router.route(3)

    # Simulate failure of link 3 -> 2.
    recovered_path = router.fail_link(3, 2)

    assert original_path == [3, 2, 1, 0]
    assert recovered_path == [3, 1, 0]

    return {
        "algorithm_test": "PASS",
        "failure_injected": "link 3 -> 2",
        "original_path": original_path,
        "recovered_path": recovered_path,
        "alternate_path_selected": recovered_path != original_path,
        "validation_type": "deterministic_link_failure_simulation",
        "live_emane_route_modified": False,
        "live_failover_status": (
            "not_executed: alternate live links need independent "
            "connectivity measurements"
        )
    }


def schedule_energy_policy(topology, schedule_file):
    root = ET.parse(schedule_file).getroot()
    structure = next(
        (element for element in root.iter()
         if element.tag.split("}")[-1].lower() == "structure"),
        None
    )

    if structure is None:
        raise RuntimeError("Schedule structure element not found")

    frame_slots = int(structure.attrib["slots"])
    slot_us = int(structure.attrib["slotduration"])

    layout = {
        int(item["radio"]): item
        for item in topology["layout"]
    }

    tx_slots = defaultdict(set)
    rx_slots = defaultdict(set)

    for slot in root.iter():
        if slot.tag.split("}")[-1].lower() != "slot":
            continue

        index = int(slot.attrib["index"])
        nodes = {
            int(value.strip())
            for value in slot.attrib.get("nodes", "").split(",")
            if value.strip()
        }

        child_tags = {
            child.tag.split("}")[-1].lower()
            for child in slot
        }

        if "tx" in child_tags:
            for nem in nodes:
                tx_slots[nem].add(index)

                radio = nem - 1
                parent_radio = int(layout[radio]["parent"])
                if parent_radio >= 0:
                    rx_slots[parent_radio + 1].add(index)

        if "rx" in child_tags:
            for nem in nodes:
                rx_slots[nem].add(index)

    all_slots = set(range(frame_slots))
    sleep_slots = {}

    for nem in range(1, 13):
        busy = tx_slots[nem] | rx_slots[nem]
        sleep_slots[nem] = sorted(all_slots - busy)

    tx_map = {
        nem: sorted(slots)
        for nem, slots in tx_slots.items()
    }

    rx_map = {
        nem: sorted(slots)
        for nem, slots in rx_slots.items()
    }

    sleep_map = {
        nem: slots
        for nem, slots in sleep_slots.items()
    }

    model = EnergyModel(ENERGY_PROFILE)

    baseline = model.estimate(
        tx_map,
        frame_slots,
        slot_us,
        frames=1,
        rx_slots=rx_map
    )

    energy_aware = model.estimate(
        tx_map,
        frame_slots,
        slot_us,
        frames=1,
        rx_slots=rx_map,
        sleep_slots=sleep_map
    )

    baseline_total = sum(item["total_j"] for item in baseline.values())
    optimized_total = sum(item["total_j"] for item in energy_aware.values())

    savings = baseline_total - optimized_total

    return {
        "status": "schedule_aware_energy_policy_calculated",
        "frame_slots": frame_slots,
        "slot_duration_us": slot_us,
        "power_profile_w": {
            "tx": ENERGY_PROFILE.tx_w,
            "rx": ENERGY_PROFILE.rx_w,
            "idle": ENERGY_PROFILE.idle_w,
            "sleep": ENERGY_PROFILE.sleep_w
        },
        "per_nem": {
            str(nem): {
                "tx_slots": tx_map.get(nem, []),
                "rx_slots": rx_map.get(nem, []),
                "sleep_candidate_slots": sleep_map[nem],
                "baseline_energy_j": round(
                    baseline[nem]["total_j"], 9
                ),
                "energy_aware_j": round(
                    energy_aware[nem]["total_j"], 9
                )
            }
            for nem in range(1, 13)
        },
        "network_baseline_energy_j_per_frame": round(
            baseline_total, 9
        ),
        "network_energy_aware_j_per_frame": round(
            optimized_total, 9
        ),
        "estimated_savings_j_per_frame": round(savings, 9),
        "estimated_savings_percent": round(
            100 * savings / baseline_total, 3
        ) if baseline_total else 0.0,
        "measurement_status": (
            "model_estimate_using_assumed_power_profile; "
            "sleep slots are candidates, not actual EMANE radio sleep states"
        )
    }


def clock_synchronization_simulation():
    rng = random.Random(20261110)

    clocks = {}
    for nem in range(1, 13):
        clocks[nem] = {
            "offset_us": rng.uniform(-100.0, 100.0),
            "drift_ppm": rng.uniform(-20.0, 20.0)
        }

    def spread():
        offsets = [
            item["offset_us"] for item in clocks.values()
        ]
        return max(offsets) - min(offsets)

    elapsed = 30.0

    for clock in clocks.values():
        clock["offset_us"] += clock["drift_ppm"] * elapsed

    unsynchronized_spread = spread()

    # Simulate master beacons once per second.
    # Each correction has up to 0.5 us residual measurement error.
    for _ in range(30):
        for clock in clocks.values():
            clock["offset_us"] += clock["drift_ppm"]
            residual = rng.uniform(-0.5, 0.5)
            clock["offset_us"] = residual

    synchronized_spread = spread()
    maximum_drift = max(
        abs(item["drift_ppm"])
        for item in clocks.values()
    )

    drift_during_slot_us = (
        maximum_drift * SLOT_US / 1_000_000.0
    )

    base_guard_us = 20.0

    required_guard_us = (
        base_guard_us
        + synchronized_spread
        + drift_during_slot_us
    )

    return {
        "status": "clock_sync_algorithm_simulation_passed",
        "virtual_nems": 12,
        "simulation_duration_s": elapsed,
        "master_beacon_interval_s": 1.0,
        "maximum_assumed_drift_ppm": round(maximum_drift, 4),
        "relative_offset_before_sync_us": round(
            unsynchronized_spread, 4
        ),
        "relative_offset_after_sync_us": round(
            synchronized_spread, 4
        ),
        "recommended_guard_time_us": round(
            required_guard_us, 4
        ),
        "base_guard_time_us": base_guard_us,
        "slot_duration_us": SLOT_US,
        "guard_within_slot": required_guard_us < SLOT_US,
        "measurement_status": (
            "virtual_clock_simulation; independent hardware clock "
            "measurements and real EMANE clock correction are not available"
        )
    }


def run_tests(prediction, recovery, energy, clock):
    tests = 0

    assert prediction["windows"] >= 3
    assert len(prediction["pdr_forecasts"]) == 11
    tests += 1

    assert recovery["algorithm_test"] == "PASS"
    assert recovery["recovered_path"] == [3, 1, 0]
    tests += 1

    assert energy["network_baseline_energy_j_per_frame"] > 0
    assert energy["estimated_savings_j_per_frame"] > 0
    tests += 1

    assert clock["relative_offset_after_sync_us"] < (
        clock["relative_offset_before_sync_us"]
    )
    assert clock["guard_within_slot"]
    tests += 1

    return tests


def main():
    for path in (TOPOLOGY_FILE, PLAN_FILE, SCHEDULE_FILE):
        if not path.exists():
            raise FileNotFoundError(f"Required input missing: {path}")

    container_check = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER],
        capture_output=True,
        text=True
    )

    if container_check.returncode != 0 or (
        container_check.stdout.strip().lower() != "true"
    ):
        raise RuntimeError(
            f"Docker container {CONTAINER} is not running. "
            "Start the existing EMANE container before collecting samples."
        )

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = ROOT / "results" / f"evo3-operational-{stamp}"
    output.mkdir(parents=True, exist_ok=False)

    print("\n========== 1. REAL EMANE TIME-SERIES COLLECTION ==========")
    samples = collect_samples(output)

    print("\n========== 2. PREDICTIVE ADAPTATION ==========")
    prediction = predictive_adaptation(samples)
    print("Real measurement windows:", prediction["windows"])
    print("Predicted radios:", len(prediction["pdr_forecasts"]))

    print("\n========== 3. SELF-HEALING FAILURE INJECTION ==========")
    recovery = self_healing_validation()
    print("Original path:", recovery["original_path"])
    print("Recovered path:", recovery["recovered_path"])
    print("Recovery algorithm:", recovery["algorithm_test"])

    print("\n========== 4. ENERGY-AWARE SCHEDULE POLICY ==========")
    energy = schedule_energy_policy(
        read_json(TOPOLOGY_FILE),
        SCHEDULE_FILE
    )
    print("Baseline energy/frame:",
          energy["network_baseline_energy_j_per_frame"], "J")
    print("Energy-aware/frame:",
          energy["network_energy_aware_j_per_frame"], "J")
    print("Estimated savings:",
          energy["estimated_savings_percent"], "%")

    print("\n========== 5. CLOCK SYNCHRONIZATION ==========")
    clock = clock_synchronization_simulation()
    print("Offset spread before sync:",
          clock["relative_offset_before_sync_us"], "us")
    print("Offset spread after sync:",
          clock["relative_offset_after_sync_us"], "us")
    print("Recommended guard:",
          clock["recommended_guard_time_us"], "us")

    print("\n========== 6. AUTOMATED CHECKS ==========")
    tests = run_tests(prediction, recovery, energy, clock)
    print(f"Operational model checks: {tests}/4 passed")

    report = {
        "experiment": "TDMA Evolution 3 operational upgrade",
        "created_at": datetime.now().astimezone().isoformat(),
        "predictive_adaptation": prediction,
        "self_healing": recovery,
        "energy_awareness": energy,
        "clock_synchronization": clock,
        "automated_checks": {
            "passed": tests,
            "total": 4
        },
        "emane_schedule_modified": False,
        "emane_routes_modified": False
    }

    write_json(output / "evo3_operational_report.json", report)

    write_json(
        output / "emane_measurement_history.json",
        {"samples": samples}
    )

    print("\n========== FINAL RESULT ==========")
    print("Automated checks:", f"{tests}/4")
    print("Predictive history:", len(samples), "real EMANE windows")
    print("Self-healing fault injection:", recovery["algorithm_test"])
    print("Energy policy:", energy["status"])
    print("Clock algorithm:", clock["status"])
    print("Live EMANE schedule modified: NO")
    print("Live EMANE routes modified: NO")
    print("Report:", output / "evo3_operational_report.json")
    print("Measurement history:", output / "emane_measurement_history.json")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("\nUPGRADE FAILED:", error, file=sys.stderr)
        sys.exit(1)
