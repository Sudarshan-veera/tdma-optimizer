"""How far from the user can the network reach?  Chain study + a constrained max-distance search."""
import numpy as np

from .phy import PHY, Channel, max_range
from .schedule import (conflict_graph, frame_length, best_schedule, subtree_loads, unit_demand)
from .topology import build_tree, chain


def chain_point(phy: PHY, n_nodes: int, margin: float = 0.9):
    """Chain of n_nodes (gateway + relays) with spacing margin*Rc."""
    spacing = margin * max_range(phy)
    chan = Channel(chain(n_nodes, spacing), phy, model="disk")
    parent, _ = build_tree(chan)
    assert (parent != -2).all(), "chain is disconnected: margin must be < 1"
    adj = conflict_graph(chan, parent)
    _, F_unit = best_schedule(adj, unit_demand(parent))
    _, F_conv = best_schedule(adj, subtree_loads(parent))
    return {"nodes": n_nodes, "hops": n_nodes - 1, "distance_m": (n_nodes - 1) * spacing,
            "F_unit": F_unit, "F_conv": F_conv}


def chain_study(phy: PHY, n_max: int = 30, margin: float = 0.9):
    return [chain_point(phy, n, margin) for n in range(2, n_max + 1)]


def max_coverage_distance(phy: PHY, slot_ms: float, latency_ms: float, rate_pps: float,
                          margin: float = 0.9, n_cap: int = 200):
    """Largest chain (and distance) such that, with one packet per node every 1/rate_pps seconds:
         * the frame is short enough to carry that rate:   F_conv * slot_ms <= 1000 / rate_pps
         * worst-case end-to-end latency (hops * frame) fits: hops * F_conv * slot_ms <= latency_ms
    F_conv grows with n, so the first n that fails ends the search."""
    best = None
    for n in range(2, n_cap + 1):
        r = chain_point(phy, n, margin)
        frame_ms = r["F_conv"] * slot_ms
        if frame_ms > 1000.0 / rate_pps or r["hops"] * frame_ms > latency_ms:
            break
        best = {**r, "frame_ms": frame_ms, "worst_latency_ms": r["hops"] * frame_ms}
    return best
