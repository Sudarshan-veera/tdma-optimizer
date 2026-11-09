import numpy as np
import pytest

from tdmaopt import *
from tdmaopt.coverage import chain_point, max_coverage_distance
from tdmaopt.dynamic import DynamicNet


def net(n, seed, model="disk", sigma=0.0):
    phy = PHY(sigma_db=sigma)
    rng = np.random.default_rng(seed)
    chan, parent, _ = random_connected(n, phy, rng, model=model)
    return phy, chan, parent, rng


def test_range_matches_sensitivity():
    phy = PHY()
    Rc = max_range(phy)
    ch = Channel([[0, 0], [Rc, 0]], phy)
    assert ch.P[0, 1] == pytest.approx(phy.sens_dbm, abs=0.01)


@pytest.mark.parametrize("seed", range(5))
def test_greedy_is_conflict_free_and_bounded(seed):
    _, chan, parent, _ = net(25, seed)
    adj = conflict_graph(chan, parent)
    for demand in (unit_demand(parent), subtree_loads(parent)):
        slots, F = greedy_schedule(adj, demand)
        assert count_violations(adj, slots)[0] == 0
        assert all(len(slots[v]) == demand[v] for v in adj)
        assert lower_bound(adj, demand) <= F <= greedy_bound(adj, demand)
    # collision-free for real, under the physical model
    slots, _ = greedy_schedule(adj, subtree_loads(parent))
    assert failing_transmissions(chan, parent, slots) == []


@pytest.mark.parametrize("seed", range(5))
def test_distributed_converges_and_is_valid(seed):
    _, chan, parent, rng = net(30, seed)
    adj = conflict_graph(chan, parent)
    slots, rounds = distributed_schedule(adj, rng)
    assert count_violations(adj, slots)[0] == 0
    assert frame_length(slots) <= max(len(a) for a in adj.values()) + 1
    assert rounds < 100


@pytest.mark.parametrize("seed", range(5))
def test_exact_never_worse_than_greedy(seed):
    _, chan, parent, _ = net(12, seed)
    adj = conflict_graph(chan, parent)
    _, F = greedy_schedule(adj, unit_demand(parent))
    best, proven = exact_min_frame(adj, F, time_limit=10)
    assert lower_bound(adj, unit_demand(parent)) <= best <= F
    assert proven


def test_random_baseline_collides_but_greedy_does_not():
    _, chan, parent, rng = net(25, 3)
    adj = conflict_graph(chan, parent)
    d = subtree_loads(parent)
    slots, F = greedy_schedule(adj, d)
    bad, total = count_violations(adj, random_schedule(adj, d, F, rng))
    assert bad > 0 and count_violations(adj, slots)[0] == 0


def test_tdma_sim_has_no_collisions_and_conserves_packets():
    _, chan, parent, rng = net(15, 2)
    adj = conflict_graph(chan, parent)
    slots, F = greedy_schedule(adj, subtree_loads(parent))
    r = simulate(chan, parent, "tdma", 0.5 / F, 4000, rng, slots=slots)
    assert r["collision_rate"] == 0.0
    assert r["delivered"] <= r["generated"]
    assert r["delivery_ratio"] > 0.8


def test_aloha_and_csma_run():
    _, chan, parent, rng = net(15, 2)
    for proto in ("aloha", "csma"):
        r = simulate(chan, parent, proto, 0.01, 3000, rng)
        assert 0 <= r["collision_rate"] <= 1 and r["delivered"] <= r["generated"]


@pytest.mark.parametrize("seed", range(3))
def test_sinr_repair_converges_to_zero_failures(seed):
    _, chan, parent, _ = net(30, seed, model="sinr", sigma=6.0)
    adj = conflict_graph(chan, parent)
    slots, _ = greedy_schedule(adj, subtree_loads(parent))
    fixed, _ = repair_sinr(chan, parent, slots)
    assert failing_transmissions(chan, parent, fixed) == []
    assert all(len(fixed[v]) == len(slots[v]) for v in slots)


def test_dynamic_join_leave_stay_valid():
    phy = PHY()
    rng = np.random.default_rng(5)
    chan, parent, _ = random_connected(25, phy, rng)
    dn = DynamicNet(phy, {i: chan.pos[i] for i in range(chan.N)})
    assert dn.valid()
    nxt = 100
    for ev in range(16):
        if ev % 2 == 0:
            cand = rng.choice([v for v in dn.pos if v != 0])
            x, y = np.array(dn.pos[int(cand)]) + rng.normal(0, 60, 2)
            moved, F = dn.join(nxt, (x, y))
            nxt += 1
        else:
            leaf_ok = [v for v in dn.parent if v != 0]
            moved, F = dn.leave(int(rng.choice(leaf_ok)))
        assert dn.valid(), f"invalid after event {ev}"
        assert moved <= len(dn.demand) + 1


def test_chain_scaling_and_max_coverage():
    a, b = chain_point(PHY(), 5), chain_point(PHY(), 15)
    assert b["distance_m"] > a["distance_m"]
    assert a["F_unit"] == 3 and b["F_unit"] == 3        # spatial reuse: 3 slots for any chain length
    assert b["F_conv"] > a["F_conv"]                    # convergecast is gateway-limited
    best = max_coverage_distance(PHY(), slot_ms=10, latency_ms=20000, rate_pps=0.5)
    assert best is not None and best["worst_latency_ms"] <= 20000


def test_viz_patterns_and_search_smoke():
    import numpy as np
    from tdmaopt.viz import PATTERNS, evaluate, anneal
    phy = PHY()
    for name, fn in PATTERNS.items():
        ev = evaluate(fn(18, phy), phy)
        assert ev is not None, name
        assert ev["F_conv"] >= ev["LB"] >= 17 or name == "chain (path graph)" or ev["F_conv"] >= 17
        assert ev["F_conv"] >= 17                      # gateway can take one packet per slot
    pos, ev = anneal(10, phy, fmax=14, rng=np.random.default_rng(0), steps=150)
    assert ev is not None and ev["F_conv"] >= 9


def test_analyze_smoke():
    import subprocess, sys
    r = subprocess.run([sys.executable, "-m", "tdmaopt.analyze", "--n", "10", "--range", "100", "--steps", "0"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "Ranking" in r.stdout
