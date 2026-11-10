from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from math import ceil, log10
import random
from typing import Callable, Mapping


class OnlineMetricPredictor:
    def __init__(self, window: int = 12):
        if window < 2:
            raise ValueError("window must be at least 2")
        self.window = window
        self.history = defaultdict(lambda: deque(maxlen=window))

    def observe(self, radio_id: int, queue_packets: int, pdr: float) -> None:
        queue_packets = int(queue_packets)
        pdr = float(pdr)
        if queue_packets < 0 or not 0.0 <= pdr <= 1.0:
            raise ValueError("invalid queue depth or PDR")
        self.history[int(radio_id)].append((queue_packets, pdr))

    @staticmethod
    def _forecast(values: list[float]) -> float:
        if not values:
            return 0.0
        if len(values) == 1:
            return values[-1]
        n = len(values)
        x_mean = (n - 1) / 2.0
        y_mean = sum(values) / n
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = sum((i - x_mean) * (value - y_mean) for i, value in enumerate(values)) / denominator
        return y_mean + slope * (n - x_mean)

    def predict(self, radio_id: int) -> dict[str, float | int]:
        samples = self.history.get(int(radio_id))
        if not samples:
            raise KeyError(f"No observations for radio {radio_id}")
        queue = self._forecast([float(item[0]) for item in samples])
        pdr = self._forecast([float(item[1]) for item in samples])
        return {"queue_packets": max(0, int(ceil(queue))), "pdr": min(1.0, max(0.0, pdr))}

    def update_controller(self, controller, radio_id: int) -> dict[str, float | int]:
        predicted = self.predict(radio_id)
        controller.update_radio(
            radio_id=radio_id,
            queue_packets=predicted["queue_packets"],
            pdr=predicted["pdr"],
            link_quality=predicted["pdr"],
        )
        return predicted


class LiveAdaptiveRuntime:
    def __init__(self, controller, metrics_provider: Callable[[], Mapping], publisher: Callable | None = None, max_changed_radios: int | None = None, predictor: OnlineMetricPredictor | None = None):
        self.controller = controller
        self.metrics_provider = metrics_provider
        self.publisher = publisher
        self.max_changed_radios = max_changed_radios
        self.predictor = predictor
        self.cycles = 0

    def step(self) -> dict:
        metrics = self.metrics_provider()
        known = set(self.controller.metrics)
        incoming = {int(key) for key in metrics}
        if incoming != known:
            raise RuntimeError("Live metric radio set differs from topology; refresh topology first")
        for radio_text, values in metrics.items():
            radio = int(radio_text)
            queue_packets = int(values["queue_packets"])
            pdr = float(values["pdr"])
            link_quality = float(values.get("link_quality", pdr))
            if self.predictor is not None:
                self.predictor.observe(radio, queue_packets, pdr)
                prediction = self.predictor.predict(radio)
                queue_packets = max(queue_packets, int(prediction["queue_packets"]))
            self.controller.update_radio(
                radio_id=radio,
                queue_packets=queue_packets,
                pdr=pdr,
                link_quality=link_quality,
            )
        report = self.controller.adapt()
        published = False
        within_churn_limit = self.max_changed_radios is None or report["changed_radio_count"] <= self.max_changed_radios
        if self.publisher is not None and report["violations"] == 0 and within_churn_limit and report["changed_radio_count"]:
            self.publisher(report)
            published = True
        self.cycles += 1
        return {"cycle": self.cycles, "published": published, "report": report}

    def run(self, cycles: int, interval_s: float = 1.0, stop_event=None) -> list[dict]:
        import time
        if cycles < 1 or interval_s < 0:
            raise ValueError("cycles must be positive and interval_s non-negative")
        results = []
        for _ in range(cycles):
            if stop_event is not None and stop_event.is_set():
                break
            results.append(self.step())
            if interval_s and len(results) < cycles:
                time.sleep(interval_s)
        return results


class MultiHopRouting:
    def __init__(self, link_pdr: Mapping[int, Mapping[int, float]], gateway: int = 0):
        self.gateway = int(gateway)
        self.link_pdr = {int(node): {int(parent): float(pdr) for parent, pdr in parents.items()} for node, parents in link_pdr.items()}
        self.link_pdr.setdefault(self.gateway, {})
        for node, parents in self.link_pdr.items():
            for parent, pdr in parents.items():
                if not 0.0 <= pdr <= 1.0:
                    raise ValueError(f"invalid PDR on link {node}->{parent}")

    def _best_path(self, node: int, visiting: set[int]) -> tuple[float, list[int]] | None:
        if node == self.gateway:
            return 0.0, [self.gateway]
        if node in visiting:
            return None
        visiting = set(visiting)
        visiting.add(node)
        best = None
        for parent, pdr in self.link_pdr.get(node, {}).items():
            if pdr <= 0.0:
                continue
            tail = self._best_path(parent, visiting)
            if tail is None:
                continue
            cost = 1.0 / pdr + tail[0]
            candidate = (cost, [node] + tail[1])
            if best is None or candidate[0] < best[0]:
                best = candidate
        return best

    def route(self, node: int) -> list[int]:
        result = self._best_path(int(node), set())
        if result is None:
            raise RuntimeError(f"No route from radio {node} to gateway {self.gateway}")
        return result[1]

    def best_parent(self, node: int, candidates: Mapping[int, float] | None = None) -> int:
        node = int(node)
        options = self.link_pdr.get(node, {}) if candidates is None else {int(k): float(v) for k, v in candidates.items()}
        best = None
        for parent, pdr in options.items():
            if parent == node or not 0.0 < pdr <= 1.0:
                continue
            tail = self._best_path(parent, {node})
            if tail is None:
                continue
            candidate = (1.0 / pdr + tail[0], parent)
            if best is None or candidate < best:
                best = candidate
        if best is None:
            raise RuntimeError(f"No healthy parent for radio {node}")
        return best[1]

    def fail_link(self, node: int, parent: int) -> list[int]:
        node, parent = int(node), int(parent)
        if node in self.link_pdr and parent in self.link_pdr[node]:
            self.link_pdr[node][parent] = 0.0
        return self.route(node)


class SelfHealingManager:
    def __init__(self, routing: MultiHopRouting, parents: Mapping[int, int]):
        self.routing = routing
        self.parents = {int(node): int(parent) for node, parent in parents.items()}

    def recover(self, failed_node: int) -> dict[int, int]:
        failed_node = int(failed_node)
        for parent in self.routing.link_pdr.get(failed_node, {}):
            self.routing.link_pdr[failed_node][parent] = 0.0
        affected = sorted(node for node, parent in self.parents.items() if parent == failed_node)
        changes = {}
        for node in affected:
            new_parent = self.routing.best_parent(node)
            self.parents[node] = new_parent
            changes[node] = new_parent
        return changes


class DistributedSlotAgent:
    def __init__(self, radio_id: int, neighbours, demand: int, frame_slots: int):
        if demand < 0 or frame_slots < 1 or demand > frame_slots:
            raise ValueError("invalid demand or frame size")
        self.radio_id = int(radio_id)
        self.neighbours = {int(value) for value in neighbours}
        self.demand = int(demand)
        self.frame_slots = int(frame_slots)
        self.slots: list[int] = []

    def advertise(self) -> dict:
        return {"radio_id": self.radio_id, "slots": list(self.slots)}

    def negotiate(self, neighbour_advertisements) -> list[int]:
        occupied = set()
        for advertisement in neighbour_advertisements:
            if int(advertisement["radio_id"]) in self.neighbours:
                occupied.update(int(slot) for slot in advertisement["slots"])
        available = [slot for slot in range(self.frame_slots) if slot not in occupied]
        start = self.radio_id % self.frame_slots
        available.sort(key=lambda slot: ((slot - start) % self.frame_slots, slot))
        if len(available) < self.demand:
            raise RuntimeError(f"radio {self.radio_id} cannot reserve {self.demand} conflict-free slots")
        self.slots = sorted(available[:self.demand])
        return list(self.slots)


def negotiate_distributed(agents: Mapping[int, DistributedSlotAgent]) -> dict[int, list[int]]:
    reservations = {}
    ordered = sorted(agents.values(), key=lambda agent: agent.radio_id)
    for agent in ordered:
        local_view = [agents[node].advertise() for node in agent.neighbours if node in agents and node in reservations]
        agent.negotiate(local_view)
        reservations[agent.radio_id] = agent.advertise()
    return {radio: list(value["slots"]) for radio, value in reservations.items()}


class FadingSINRModel:
    def __init__(self, model: str = "rayleigh", rician_k: float = 3.0, seed: int | None = None, sinr_threshold_db: float = 8.0):
        if model not in {"rayleigh", "rician", "none"}:
            raise ValueError("model must be rayleigh, rician or none")
        if rician_k < 0:
            raise ValueError("rician_k must be non-negative")
        self.model = model
        self.rician_k = float(rician_k)
        self.rng = random.Random(seed)
        self.sinr_threshold_db = float(sinr_threshold_db)

    def power_gain(self) -> float:
        if self.model == "none":
            return 1.0
        if self.model == "rayleigh":
            return self.rng.expovariate(1.0)
        k = self.rician_k
        scale = 1.0 / (2.0 * (k + 1.0))
        real = self.rng.gauss((2.0 * k * scale) ** 0.5, scale ** 0.5)
        imag = self.rng.gauss(0.0, scale ** 0.5)
        return real * real + imag * imag

    def received_mw(self, tx_dbm: float, path_loss_db: float) -> float:
        return 10.0 ** ((float(tx_dbm) - float(path_loss_db)) / 10.0) * self.power_gain()

    def sinr_db(self, signal_mw: float, interference_mw=(), noise_mw: float = 1e-10) -> float:
        denominator = float(noise_mw) + sum(max(0.0, float(value)) for value in interference_mw)
        if signal_mw <= 0.0 or denominator <= 0.0:
            return float("-inf")
        return 10.0 * log10(float(signal_mw) / denominator)

    def allowed(self, signal_mw: float, interference_mw=(), noise_mw: float = 1e-10) -> bool:
        return self.sinr_db(signal_mw, interference_mw, noise_mw) >= self.sinr_threshold_db


@dataclass(frozen=True)
class EnergyProfile:
    tx_w: float
    rx_w: float
    idle_w: float
    sleep_w: float

    def __post_init__(self):
        if min(self.tx_w, self.rx_w, self.idle_w, self.sleep_w) < 0:
            raise ValueError("power values cannot be negative")


class EnergyModel:
    def __init__(self, profile: EnergyProfile):
        self.profile = profile

    def estimate(self, tx_slots: Mapping[int, list[int]], frame_slots: int, slot_us: int, frames: int = 1, rx_slots: Mapping[int, list[int]] | None = None, sleep_slots: Mapping[int, list[int]] | None = None) -> dict[int, dict[str, float]]:
        if frame_slots < 1 or slot_us <= 0 or frames < 1:
            raise ValueError("invalid frame timing")
        rx_slots = rx_slots or {}
        sleep_slots = sleep_slots or {}
        radios = set(tx_slots) | set(rx_slots) | set(sleep_slots)
        result = {}
        slot_s = slot_us * 1e-6
        total_s = frame_slots * slot_s * frames
        for radio in radios:
            tx_set = set(tx_slots.get(radio, []))
            rx_set = set(rx_slots.get(radio, [])) - tx_set
            sleep_set = set(sleep_slots.get(radio, [])) - tx_set - rx_set
            tx = len(tx_set)
            rx = len(rx_set)
            sleep = len(sleep_set)
            if tx + rx + sleep > frame_slots:
                raise ValueError(f"radio {radio} has more assigned states than frame capacity")
            idle = frame_slots - tx - rx - sleep
            result[int(radio)] = {
                "tx_j": tx * slot_s * frames * self.profile.tx_w,
                "rx_j": rx * slot_s * frames * self.profile.rx_w,
                "idle_j": idle * slot_s * frames * self.profile.idle_w,
                "sleep_j": sleep * slot_s * frames * self.profile.sleep_w,
                "total_frame_time_s": total_s,
            }
            result[int(radio)]["total_j"] = result[int(radio)]["tx_j"] + result[int(radio)]["rx_j"] + result[int(radio)]["idle_j"] + result[int(radio)]["sleep_j"]
        return result


@dataclass
class ClockModel:
    offset_us: float = 0.0
    drift_ppm: float = 0.0

    def advance(self, elapsed_s: float) -> float:
        if elapsed_s < 0:
            raise ValueError("elapsed time cannot be negative")
        self.offset_us += self.drift_ppm * elapsed_s
        return self.offset_us

    def synchronize(self, master_time_us: float, local_time_us: float) -> float:
        self.offset_us += float(master_time_us) - float(local_time_us)
        return self.offset_us

    @staticmethod
    def required_guard_us(clocks, horizon_s: float = 1.0) -> int:
        if horizon_s < 0:
            raise ValueError("horizon_s cannot be negative")
        errors = [abs(clock.offset_us) + abs(clock.drift_ppm) * horizon_s for clock in clocks]
        return int(ceil(2.0 * max(errors, default=0.0)))

    def slot_start_us(self, frame_start_us: float, slot_index: int, slot_duration_us: int) -> float:
        if slot_index < 0 or slot_duration_us <= 0:
            raise ValueError("invalid slot timing")
        return float(frame_start_us) + slot_index * slot_duration_us + self.offset_us
