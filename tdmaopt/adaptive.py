from math import ceil, isfinite

from .schedule import count_violations, frame_length, greedy_schedule


class AdaptiveTDMA:
    def __init__(
        self,
        network,
        max_slots_per_radio=32,
        pdr_floor=0.10,
        ema_alpha=0.35,
        quality_weight=0.50,
    ):
        if max_slots_per_radio < 1:
            raise ValueError("max_slots_per_radio must be positive")

        if not 0 < pdr_floor <= 1:
            raise ValueError("pdr_floor must be between 0 and 1")

        if not 0 < ema_alpha <= 1:
            raise ValueError("ema_alpha must be between 0 and 1")

        if quality_weight < 0:
            raise ValueError("quality_weight cannot be negative")

        self.network = network
        self.max_slots_per_radio = int(max_slots_per_radio)
        self.pdr_floor = float(pdr_floor)
        self.ema_alpha = float(ema_alpha)
        self.quality_weight = float(quality_weight)

        self.metrics = {}
        self.demand = {}
        self.slots = {}

        self.refresh_topology(initial=True)

    def _read_adjacency(self):
        if not hasattr(self.network, "_graph"):
            raise TypeError("network must provide an _graph() method")

        raw = self.network._graph()
        adjacency = {
            int(node): {int(neighbour) for neighbour in neighbours}
            for node, neighbours in raw.items()
        }

        for node in list(adjacency):
            for neighbour in adjacency[node]:
                if neighbour not in adjacency:
                    raise ValueError(
                        f"Neighbour {neighbour} is missing from the conflict graph"
                    )
                adjacency[neighbour].add(node)

        return adjacency

    def refresh_topology(self, initial=False):
        adjacency = self._read_adjacency()
        base_demand = getattr(self.network, "demand", {})
        base_slots = getattr(self.network, "slots", {})

        old_metrics = self.metrics
        old_demand = self.demand
        old_slots = self.slots

        self.metrics = {}
        self.demand = {}
        self.slots = {}

        for node in adjacency:
            if node in old_metrics:
                self.metrics[node] = dict(old_metrics[node])
            else:
                initial_queue = max(0, int(base_demand.get(node, 1)))
                self.metrics[node] = {
                    "queue_packets": initial_queue,
                    "pdr": None,
                    "link_quality": None,
                }

            if node in old_demand:
                self.demand[node] = old_demand[node]
            else:
                self.demand[node] = max(0, int(base_demand.get(node, 1)))

            if node in old_slots:
                self.slots[node] = list(old_slots[node])
            else:
                self.slots[node] = list(base_slots.get(node, []))

        if initial:
            return {
                "frame_slots": frame_length(self.slots),
                "changed_radios": [],
                "changed_radio_count": 0,
                "moved_slot_assignments": 0,
                "violations": count_violations(adjacency, self.slots)[0],
            }

        return self.adapt()

    def _smooth(self, old_value, new_value):
        if old_value is None:
            return new_value

        return (
            self.ema_alpha * new_value
            + (1.0 - self.ema_alpha) * old_value
        )

    def update_radio(
        self,
        radio_id,
        queue_packets=None,
        pdr=None,
        link_quality=None,
    ):
        radio_id = int(radio_id)

        if radio_id not in self.metrics:
            raise KeyError(
                f"Radio {radio_id} is not in the current network. "
                "Call refresh_topology() after a topology change."
            )

        if queue_packets is not None:
            queue_value = int(queue_packets)

            if queue_value != queue_packets or queue_value < 0:
                raise ValueError("queue_packets must be a non-negative integer")

            self.metrics[radio_id]["queue_packets"] = queue_value

        if pdr is not None:
            pdr_value = float(pdr)

            if not isfinite(pdr_value) or not 0 <= pdr_value <= 1:
                raise ValueError("pdr must be between 0 and 1")

            old_value = self.metrics[radio_id]["pdr"]
            self.metrics[radio_id]["pdr"] = self._smooth(
                old_value,
                pdr_value,
            )

        if link_quality is not None:
            quality_value = float(link_quality)

            if not isfinite(quality_value) or not 0 <= quality_value <= 1:
                raise ValueError("link_quality must be between 0 and 1")

            old_value = self.metrics[radio_id]["link_quality"]
            self.metrics[radio_id]["link_quality"] = self._smooth(
                old_value,
                quality_value,
            )

    def record_delivery(
        self,
        radio_id,
        sent,
        received,
        queue_packets=None,
        link_quality=None,
    ):
        sent = int(sent)
        received = int(received)

        if sent <= 0:
            raise ValueError("sent must be greater than zero")

        if received < 0 or received > sent:
            raise ValueError("received must be between zero and sent")

        measured_pdr = received / sent

        self.update_radio(
            radio_id,
            queue_packets=queue_packets,
            pdr=measured_pdr,
            link_quality=link_quality,
        )

        return measured_pdr

    def _required_slots(self, node):
        queue_size = self.metrics[node]["queue_packets"]
        measured_pdr = self.metrics[node]["pdr"]

        if queue_size == 0:
            return 0

        if measured_pdr is None:
            measured_pdr = 1.0

        effective_pdr = max(self.pdr_floor, measured_pdr)
        required = ceil(queue_size / effective_pdr)

        return min(required, self.max_slots_per_radio)

    def _priority(self, node, adjacency):
        metric = self.metrics[node]

        queue_size = metric["queue_packets"]
        measured_pdr = metric["pdr"]
        quality = metric["link_quality"]

        if measured_pdr is None:
            measured_pdr = 1.0

        if quality is None:
            quality = 1.0

        reliability_factor = 1.0 / max(
            self.pdr_floor,
            measured_pdr,
        )

        quality_factor = 1.0 + self.quality_weight * (1.0 - quality)

        traffic_score = queue_size * reliability_factor * quality_factor
        degree_score = len(adjacency[node])

        return traffic_score, degree_score

    def _fixed_assignments(self, adjacency, new_demand):
        fixed = {}

        for node in adjacency:
            old_slots = self.slots.get(node, [])
            old_demand = self.demand.get(node)

            if old_demand == new_demand[node]:
                if len(old_slots) == new_demand[node]:
                    fixed[node] = list(old_slots)

        while True:
            conflict_found = False

            for node in sorted(fixed):
                for neighbour in adjacency[node]:
                    if neighbour not in fixed or neighbour <= node:
                        continue

                    overlap = set(fixed[node]) & set(fixed[neighbour])

                    if overlap:
                        node_priority = self._priority(node, adjacency)
                        neighbour_priority = self._priority(
                            neighbour,
                            adjacency,
                        )

                        if node_priority < neighbour_priority:
                            loser = node
                        else:
                            loser = neighbour

                        del fixed[loser]
                        conflict_found = True
                        break

                if conflict_found:
                    break

            if not conflict_found:
                break

        return fixed

    def adapt(self):
        adjacency = self._read_adjacency()
        active_nodes = set(adjacency)

        if active_nodes != set(self.metrics):
            raise RuntimeError(
                "Network topology changed. Call refresh_topology() first."
            )

        old_slots = {
            node: list(slots)
            for node, slots in self.slots.items()
        }

        new_demand = {
            node: self._required_slots(node)
            for node in adjacency
        }

        fixed = self._fixed_assignments(
            adjacency,
            new_demand,
        )

        order = sorted(
            adjacency,
            key=lambda node: (
                self._priority(node, adjacency)[0],
                self._priority(node, adjacency)[1],
                -node,
            ),
            reverse=True,
        )

        new_slots, frame = greedy_schedule(
            adjacency,
            new_demand,
            fixed=fixed,
            order=order,
        )

        violations, total_transmissions = count_violations(
            adjacency,
            new_slots,
        )

        if violations:
            new_slots, frame = greedy_schedule(
                adjacency,
                new_demand,
                order=order,
            )

            violations, total_transmissions = count_violations(
                adjacency,
                new_slots,
            )

        if violations:
            raise RuntimeError(
                f"Adaptive scheduler produced {violations} conflicting transmissions"
            )

        changed_radios = []

        for node in adjacency:
            if old_slots.get(node, []) != new_slots.get(node, []):
                changed_radios.append(node)

        moved_assignments = 0

        for node in adjacency:
            old_set = set(old_slots.get(node, []))
            new_set = set(new_slots.get(node, []))
            moved_assignments += len(old_set.symmetric_difference(new_set))

        self.demand = new_demand
        self.slots = {
            node: list(slots)
            for node, slots in new_slots.items()
        }

        self.network.demand = dict(self.demand)
        self.network.slots = {
            node: list(slots)
            for node, slots in self.slots.items()
        }

        return {
            "frame_slots": frame,
            "changed_radios": sorted(changed_radios),
            "changed_radio_count": len(changed_radios),
            "moved_slot_assignments": moved_assignments,
            "fixed_radios": len(fixed),
            "violations": violations,
            "total_transmissions": total_transmissions,
            "demand": dict(self.demand),
            "slots": {
                node: list(slots)
                for node, slots in self.slots.items()
            },
        }

    def is_valid(self):
        adjacency = self._read_adjacency()
        violations, _ = count_violations(adjacency, self.slots)
        return violations == 0

    def metrics_snapshot(self):
        result = {}

        for node, metric in self.metrics.items():
            result[node] = {
                "queue_packets": metric["queue_packets"],
                "pdr": (
                    1.0
                    if metric["pdr"] is None
                    else metric["pdr"]
                ),
                "link_quality": (
                    1.0
                    if metric["link_quality"] is None
                    else metric["link_quality"]
                ),
                "assigned_slots": list(self.slots.get(node, [])),
                "required_slots": self.demand.get(node, 0),
            }

        return result
