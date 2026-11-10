from tdmaopt.evolution import (
    ClockModel,
    DistributedSlotAgent,
    EnergyModel,
    EnergyProfile,
    FadingSINRModel,
    MultiHopRouting,
    OnlineMetricPredictor,
    SelfHealingManager,
    negotiate_distributed,
)


def test_predictor_tracks_queue_and_bounds_pdr():
    predictor = OnlineMetricPredictor()
    predictor.observe(1, 2, 0.9)
    predictor.observe(1, 4, 0.8)
    prediction = predictor.predict(1)
    assert prediction["queue_packets"] >= 5
    assert 0.0 <= prediction["pdr"] <= 1.0


def test_multihop_route_uses_best_reliable_path():
    routing = MultiHopRouting({1: {0: 0.4, 2: 0.9}, 2: {0: 0.9}})
    assert routing.route(1) == [1, 2, 0]


def test_failed_link_recovers_on_alternate_path():
    routing = MultiHopRouting({1: {0: 0.9, 2: 0.8}, 2: {0: 0.9}})
    assert routing.fail_link(1, 0) == [1, 2, 0]


def test_self_healing_reparents_children_of_failed_relay():
    routing = MultiHopRouting({1: {0: 1.0}, 2: {1: 0.9, 0: 0.8}, 3: {2: 0.9}})
    manager = SelfHealingManager(routing, {1: 0, 2: 1, 3: 2})
    assert manager.recover(1) == {2: 0}
    assert manager.parents[3] == 2


def test_distributed_agents_reserve_non_conflicting_slots():
    agents = {
        1: DistributedSlotAgent(1, {2}, 2, 4),
        2: DistributedSlotAgent(2, {1}, 2, 4),
    }
    slots = negotiate_distributed(agents)
    assert set(slots[1]).isdisjoint(slots[2])


def test_fading_models_are_reproducible_and_sinr_checked():
    first = FadingSINRModel("rayleigh", seed=7)
    second = FadingSINRModel("rayleigh", seed=7)
    assert first.power_gain() == second.power_gain()
    assert FadingSINRModel("none").allowed(1.0, [], 0.01)
    assert not FadingSINRModel("none").allowed(0.001, [1.0], 0.01)


def test_energy_estimate_counts_tx_rx_and_idle():
    model = EnergyModel(EnergyProfile(2.0, 1.0, 0.5, 0.05))
    result = model.estimate({1: [0]}, 4, 1000, rx_slots={1: [1]}, sleep_slots={1: [2]})[1]
    assert result["tx_j"] == 0.002
    assert result["rx_j"] == 0.001
    assert result["sleep_j"] == 0.00005
    assert result["idle_j"] == 0.0005


def test_clock_guard_includes_offset_and_drift():
    clocks = [ClockModel(2.0, 10.0), ClockModel(-1.0, -5.0)]
    guard = ClockModel.required_guard_us(clocks, 2.0)
    assert guard == 44
    clocks[0].advance(1.0)
    assert clocks[0].offset_us == 12.0
    clocks[0].synchronize(100.0, 112.0)
    assert clocks[0].offset_us == 0.0


def test_live_runtime_updates_and_respects_churn_limit():
    from tdmaopt.evolution import LiveAdaptiveRuntime

    class FakeController:
        def __init__(self):
            self.metrics = {1: {}, 2: {}}
            self.updated = {}

        def update_radio(self, radio_id, queue_packets, pdr, link_quality):
            self.updated[radio_id] = (queue_packets, pdr, link_quality)

        def adapt(self):
            return {
                "changed_radio_count": 1,
                "changed_radios": [1],
                "moved_slot_assignments": 1,
                "violations": 0,
                "frame_slots": 3,
                "slots": {1: [0], 2: [2]},
            }

    controller = FakeController()
    published = []
    metrics = {
        1: {"queue_packets": 4, "pdr": 0.9, "link_quality": 0.8},
        2: {"queue_packets": 2, "pdr": 1.0, "link_quality": 1.0},
    }
    runtime = LiveAdaptiveRuntime(controller, lambda: metrics, published.append, max_changed_radios=1)
    result = runtime.step()
    assert result["published"] is True
    assert len(published) == 1
    assert controller.updated[1] == (4, 0.9, 0.8)


def test_predictor_is_used_for_queue_ahead_of_measured_backlog():
    from tdmaopt.evolution import LiveAdaptiveRuntime

    class FakeController:
        def __init__(self):
            self.metrics = {1: {}}
            self.updated = {}

        def update_radio(self, radio_id, queue_packets, pdr, link_quality):
            self.updated[radio_id] = (queue_packets, pdr, link_quality)

        def adapt(self):
            return {"changed_radio_count": 0, "changed_radios": [], "moved_slot_assignments": 0, "violations": 0, "frame_slots": 1, "slots": {1: [0]}}

    controller = FakeController()
    predictor = OnlineMetricPredictor()
    predictor.observe(1, 2, 0.9)
    predictor.observe(1, 6, 0.9)
    runtime = LiveAdaptiveRuntime(
        controller,
        lambda: {1: {"queue_packets": 3, "pdr": 0.9}},
        predictor=predictor,
    )
    runtime.step()
    assert controller.updated[1][0] > 3
