"""Topology generators and the routing tree (everything flows to the gateway, node 0)."""
from collections import deque

import numpy as np

from .phy import PHY, Channel, max_range


def chain(n_nodes: int, spacing: float):
    """Gateway at x=0 and n_nodes-1 relays in a line."""
    return np.array([[i * spacing, 0.0] for i in range(n_nodes)])


def grid(rows: int, cols: int, spacing: float):
    pos = [[c * spacing, r * spacing] for r in range(rows) for c in range(cols)]
    return np.array(pos)


def build_tree(chan: Channel):
    """BFS tree to node 0. Ties go to the strongest link.
    Returns (parent, hops): parent[0] = -1, unreachable nodes = -2."""
    N = chan.N
    hops = np.full(N, -1)
    hops[0] = 0
    dq = deque([0])
    while dq:
        u = dq.popleft()
        for v in np.flatnonzero(chan.comm[u]):
            if hops[v] < 0:
                hops[v] = hops[u] + 1
                dq.append(v)
    parent = np.full(N, -2)
    parent[0] = -1
    for v in range(1, N):
        if hops[v] < 0:
            continue
        cands = [u for u in np.flatnonzero(chan.comm[v]) if hops[u] == hops[v] - 1]
        parent[v] = max(cands, key=lambda u: chan.P[v, u])
    return parent, hops


def random_connected(n: int, phy: PHY, rng, model: str = "disk", tries: int = 500):
    """n nodes uniformly in a square sized so the network is connected with decent probability.
    Gateway at the centre. Returns (chan, parent, hops)."""
    Rc = max_range(phy)
    side = Rc * np.sqrt(np.pi * n / (np.log(max(n, 3)) + 2.0))
    for _ in range(tries):
        pos = rng.uniform(0, side, size=(n, 2))
        pos[0] = (side / 2, side / 2)
        chan = Channel(pos, phy, rng=rng, model=model)
        parent, hops = build_tree(chan)
        if (parent != -2).all():
            return chan, parent, hops
    raise RuntimeError("could not generate a connected topology")


def coverage_radius(chan: Channel, parent) -> float:
    """Farthest reachable node from the gateway (metres)."""
    ok = np.flatnonzero(parent != -2)
    return float(chan.D[0, ok].max())
