"""Slot assignment: conflict graph, greedy (weighted), distributed, exact, random baseline, SINR repair.

A schedule is a dict  node -> list of slot indices  within a frame of length F.
Every non-gateway node owns one uplink (node -> parent), so "node" and "link" are the same thing here.
"""
import itertools
import time

import numpy as np

from .phy import Channel


# --------------------------------------------------------------------------- demand
def subtree_loads(parent):
    """Packets a node must send per frame when every node generates one packet per frame
    (own packet + everything it forwards). This is the convergecast demand."""
    N = len(parent)
    load = np.zeros(N, dtype=int)
    for v in range(1, N):
        if parent[v] == -2:
            continue
        u = v
        while u > 0:
            load[u] += 1
            u = parent[u]
    return {v: int(load[v]) for v in range(1, N) if parent[v] >= 0}


def unit_demand(parent):
    return {v: 1 for v in range(1, len(parent)) if parent[v] >= 0}


# --------------------------------------------------------------------------- conflicts
def conflict_graph(chan: Channel, parent):
    """Node-level conflict graph: i and k conflict if links i->p(i) and k->p(k) cannot share a slot
    (shared endpoint / half duplex / hidden terminal / interference)."""
    nodes = [v for v in range(chan.N) if parent[v] >= 0]
    adj = {v: set() for v in nodes}
    for a in range(len(nodes)):
        i = nodes[a]
        for b in range(a + 1, len(nodes)):
            k = nodes[b]
            if chan.link_conflict(i, int(parent[i]), k, int(parent[k])):
                adj[i].add(k)
                adj[k].add(i)
    return adj


def frame_length(slots):
    return 1 + max((max(s) for s in slots.values() if s), default=-1)


# --------------------------------------------------------------------------- greedy
def greedy_schedule(adj, demand, fixed=None, order=None):
    """Greedy weighted colouring.  Heavy / busy nodes first.
    fixed : already-assigned nodes (dict) that must not move (used by the incremental scheduler).
    Guarantee: F <= max_i ( d_i + sum_{j in N(i)} d_j )   (and <= Delta+1 for unit demand)."""
    slots = dict(fixed) if fixed else {}
    todo = [v for v in adj if v not in slots]
    if order is None:
        todo.sort(key=lambda v: (-(demand[v] * (1 + len(adj[v]))), v))
    else:
        todo = [v for v in order if v in set(todo)]
    for v in todo:
        used = set()
        for u in adj[v]:
            used.update(slots.get(u, ()))
        mine, c = [], 0
        while len(mine) < demand[v]:
            if c not in used:
                mine.append(c)
            c += 1
        slots[v] = mine
    return slots, frame_length(slots)


def greedy_bound(adj, demand):
    """Worst-case frame length the greedy algorithm can ever need."""
    return max((demand[v] + sum(demand[u] for u in adj[v]) for v in adj), default=0)


def lower_bound(adj, demand):
    """Greedy-clique lower bound on any valid frame length."""
    best = 0
    for v in adj:
        clique = [v]
        for u in sorted(adj[v], key=lambda x: -demand[x]):
            if all(u in adj[w] for w in clique):
                clique.append(u)
        best = max(best, sum(demand[w] for w in clique))
    return best


# --------------------------------------------------------------------------- distributed
def distributed_schedule(adj, rng, max_rounds=10_000):
    """Round-based randomised slot choice (unit demand). Every pending node picks a random slot
    that none of its already-settled conflict neighbours uses, from a palette of Delta+1 slots.
    Clashes are resolved by node id. Terminates because the palette can never be exhausted.
    Returns (slots, rounds)."""
    delta = max((len(a) for a in adj.values()), default=0)
    palette = delta + 1
    slot, pending, rounds = {}, set(adj), 0
    while pending:
        rounds += 1
        if rounds > max_rounds:
            raise RuntimeError("did not converge")
        pick = {}
        for v in pending:
            used = {slot[u] for u in adj[v] if u in slot}
            free = [s for s in range(palette) if s not in used]
            pick[v] = int(rng.choice(free))
        for v in sorted(pending):
            if not any(u in pick and pick[u] == pick[v] and u < v for u in adj[v]):
                slot[v] = pick[v]
        pending = {v for v in pending if v not in slot}
    return {v: [s] for v, s in slot.items()}, rounds


# --------------------------------------------------------------------------- exact (unit demand)
def exact_min_frame(adj, ub, time_limit=10.0):
    """Minimum number of slots for unit demand = chromatic number of the conflict graph.
    DSATUR branch-and-bound, started from the greedy value `ub`.
    Returns (best, proven_optimal)."""
    nodes = list(adj)
    n = len(nodes)
    if n == 0:
        return 0, True
    idx = {v: i for i, v in enumerate(nodes)}
    nb = [[idx[u] for u in adj[v]] for v in nodes]
    lb = lower_bound(adj, {v: 1 for v in adj})
    best = [ub]
    color = [-1] * n
    t0 = time.time()
    state = {"timeout": False}

    def rec(ncol, colored):
        if best[0] <= lb:
            return
        if time.time() - t0 > time_limit:
            state["timeout"] = True
            return
        if colored == n:
            best[0] = min(best[0], ncol)
            return
        bv, bs, bd = -1, -1, -1
        for v in range(n):
            if color[v] < 0:
                sat = len({color[u] for u in nb[v] if color[u] >= 0})
                if sat > bs or (sat == bs and len(nb[v]) > bd):
                    bv, bs, bd = v, sat, len(nb[v])
        used = {color[u] for u in nb[bv] if color[u] >= 0}
        for c in range(ncol + 1):
            if c in used:
                continue
            newn = max(ncol, c + 1)
            if newn >= best[0]:
                continue
            color[bv] = c
            rec(newn, colored + 1)
            color[bv] = -1
            if state["timeout"]:
                return

    rec(0, 0)
    return best[0], not state["timeout"]


def expand_demand(adj, demand):
    """Turn a weighted problem into plain graph colouring: node v becomes demand[v] copies that
    conflict with each other and with every copy of every neighbour. Lets exact_min_frame handle weights."""
    ex = {(v, c): set() for v in adj for c in range(demand[v])}
    for v in adj:
        for c in range(demand[v]):
            ex[(v, c)].update((v, c2) for c2 in range(demand[v]) if c2 != c)
            for u in adj[v]:
                ex[(v, c)].update((u, c2) for c2 in range(demand[u]))
    return ex


# --------------------------------------------------------------------------- random baseline
def random_schedule(adj, demand, F, rng):
    """Baseline: every node picks `demand` random slots out of a frame of length F, ignoring conflicts."""
    return {v: sorted(int(s) for s in rng.choice(F, size=min(demand[v], F), replace=False)) for v in adj}


def count_violations(adj, slots):
    """Number of (node, slot) transmissions that overlap with a conflicting node in the same slot."""
    bad, total = 0, 0
    for v, sv in slots.items():
        for s in sv:
            total += 1
            if any(s in slots.get(u, ()) for u in adj[v]):
                bad += 1
    return bad, total


# --------------------------------------------------------------------------- SINR validation + repair
def failing_transmissions(chan: Channel, parent, slots):
    """(node, slot) pairs whose reception fails under the aggregate-interference model."""
    F = frame_length(slots)
    per_slot = [set() for _ in range(F)]
    for v, sv in slots.items():
        for s in sv:
            per_slot[s].add(v)
    bad = []
    for s, txs in enumerate(per_slot):
        for v in txs:
            if not chan.success(v, int(parent[v]), txs):
                bad.append((v, s))
    return bad


def repair_sinr(chan: Channel, parent, slots, max_iter=100_000):
    """Pairwise-conflict schedules can still fail when many weak interferers add up.
    Move one failing transmission at a time to the first slot where it works and breaks nobody
    (or to a fresh slot). Every move strictly lowers the number of failures, so this converges.
    Returns (slots, iterations)."""
    slots = {v: list(s) for v, s in slots.items()}
    it = 0
    while True:
        bad = failing_transmissions(chan, parent, slots)
        if not bad:
            return slots, it
        it += 1
        if it > max_iter:
            raise RuntimeError("repair did not converge")
        v, s = bad[0]
        slots[v].remove(s)
        F = frame_length(slots)
        placed = False
        for t in range(F + 1):
            if t in slots[v]:
                continue
            txs = {u for u, su in slots.items() if t in su} | {v}
            if all(chan.success(u, int(parent[u]), txs) for u in txs):
                slots[v].append(t)
                slots[v].sort()
                placed = True
                break
        assert placed
