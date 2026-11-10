from tdmaopt.adaptive import AdaptiveTDMA
from tdmaopt.schedule import greedy_schedule, count_violations


class ToyNetwork:
    def __init__(self):
        self.adjacency = {
            1: {2, 3},
            2: {1},
            3: {1},
            4: {5},
            5: {4},
            6: set(),
        }

        self.demand = {
            node: 1
            for node in self.adjacency
        }

        self.slots, _ = greedy_schedule(
            self.adjacency,
            self.demand,
        )

    def _graph(self):
        return {
            node: set(neighbours)
            for node, neighbours in self.adjacency.items()
        }


def test_adaptive_increases_slots_for_queued_traffic():
    network = ToyNetwork()
    controller = AdaptiveTDMA(network)

    old_slots = {
        node: list(slots)
        for node, slots in network.slots.items()
    }

    controller.update_radio(
        1,
        queue_packets=3,
        pdr=0.75,
        link_quality=0.60,
    )

    report = controller.adapt()

    assert controller.demand[1] == 4
    assert report["violations"] == 0
    assert report["changed_radios"] == [1]
    assert controller.is_valid()

    for node in (2, 3, 4, 5, 6):
        assert controller.slots[node] == old_slots[node]


def test_adaptive_keeps_schedule_when_metrics_do_not_change():
    network = ToyNetwork()
    controller = AdaptiveTDMA(network)

    old_slots = {
        node: list(slots)
        for node, slots in controller.slots.items()
    }

    report = controller.adapt()

    assert report["changed_radio_count"] == 0
    assert report["moved_slot_assignments"] == 0
    assert controller.slots == old_slots
    assert controller.is_valid()


def test_adaptive_zero_queue_releases_slots():
    network = ToyNetwork()
    controller = AdaptiveTDMA(network)

    controller.update_radio(
        1,
        queue_packets=0,
    )

    report = controller.adapt()

    assert controller.demand[1] == 0
    assert controller.slots[1] == []
    assert report["violations"] == 0
    assert controller.is_valid()


def test_delivery_measurement_updates_pdr_and_demand():
    network = ToyNetwork()
    controller = AdaptiveTDMA(network)

    measured_pdr = controller.record_delivery(
        radio_id=1,
        sent=10,
        received=5,
        queue_packets=3,
        link_quality=0.40,
    )

    report = controller.adapt()

    assert measured_pdr == 0.5
    assert controller.metrics_snapshot()[1]["pdr"] == 0.5
    assert controller.demand[1] == 6
    assert report["violations"] == 0
    assert controller.is_valid()


def test_adaptive_refresh_handles_new_radio():
    network = ToyNetwork()
    controller = AdaptiveTDMA(network)

    network.adjacency[6].add(7)
    network.adjacency[7] = {6}
    network.demand[7] = 1

    report = controller.refresh_topology()

    assert 7 in controller.slots
    assert 7 in controller.demand
    assert report["violations"] == 0
    assert controller.is_valid()


def test_invalid_pdr_is_rejected():
    network = ToyNetwork()
    controller = AdaptiveTDMA(network)

    try:
        controller.update_radio(1, pdr=1.5)
    except ValueError:
        return

    raise AssertionError("Invalid PDR should raise ValueError")
