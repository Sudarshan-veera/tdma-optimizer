from emane.adaptive_bridge import (
    PlanNetwork,
    full_schedule_xml,
    update_schedule_xml,
)


def small_topology():
    return {
        "layout": [
            {
                "radio": 0,
                "x_m": 0.0,
                "y_m": 0.0,
                "range_m": 500.0,
                "parent": -1,
                "tx_slots": [],
            },
            {
                "radio": 1,
                "x_m": 100.0,
                "y_m": 0.0,
                "range_m": 300.0,
                "parent": 0,
                "tx_slots": [0],
            },
            {
                "radio": 2,
                "x_m": -100.0,
                "y_m": 0.0,
                "range_m": 300.0,
                "parent": 0,
                "tx_slots": [1],
            },
            {
                "radio": 3,
                "x_m": 200.0,
                "y_m": 0.0,
                "range_m": 300.0,
                "parent": 1,
                "tx_slots": [2],
            },
        ]
    }


def test_plan_network_preserves_radio_ids_and_subtree_loads():
    network = PlanNetwork(small_topology())

    assert network.radio_ids == [0, 1, 2, 3]
    assert network.demand == {
        1: 2,
        2: 1,
        3: 1,
    }
    assert network.slots == {
        1: [0],
        2: [1],
        3: [2],
    }

    for radio, neighbours in network._graph().items():
        for neighbour in neighbours:
            assert radio in network._graph()[neighbour]


def test_update_schedule_keeps_existing_structure():
    xml = update_schedule_xml(
        {2: [1], 3: [0]},
        [1, 2, 3],
        3,
        "10M",
    )

    assert "<structure" not in xml
    assert "nodes='1'" in xml
    assert "nodes='2'" in xml
    assert "nodes='3'" in xml
    assert "<tx/>" in xml
    assert "<rx/>" in xml
    assert xml.count("<slot ") == 9


def test_full_schedule_contains_structure_and_silent_gateway():
    xml = full_schedule_xml(
        {2: [1]},
        [1, 2, 3],
        3,
        10000,
        "10M",
    )

    assert "<structure" in xml
    assert "slots='3'" in xml
    assert "slotduration='10000'" in xml
    assert "nodes='2'" in xml
    assert "nodes='1,3'" in xml
    assert "<tx/>" in xml
    assert "<rx/>" in xml
