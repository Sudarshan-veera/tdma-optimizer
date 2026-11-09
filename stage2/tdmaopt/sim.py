"""Slot-level simulator: convergecast traffic to the gateway under TDMA, slotted ALOHA, or slotted CSMA."""
from collections import deque

import numpy as np

from .phy import Channel


def simulate(chan: Channel, parent, proto: str, lam: float, T: int, rng,
             slots=None, p: float = 0.1, cw0: int = 8, cwmax: int = 256):
    """Every non-gateway node generates a packet with probability `lam` per slot and routes it
    hop by hop to node 0.  proto in {'tdma','aloha','csma'}."""
    N = chan.N
    nodes = [v for v in range(N) if parent[v] >= 0]
    q = [deque() for _ in range(N)]
    if proto == "tdma":
        F = 1 + max(max(s) for s in slots.values())
        frame = [[] for _ in range(F)]
        for v, sv in slots.items():
            for s in sv:
                frame[s].append(v)
    gen = delivered = attempts = fails = 0
    lat = []
    backoff = {v: int(rng.integers(1, cw0 + 1)) for v in nodes}
    cw = {v: cw0 for v in nodes}
    prev_tx = []
    nn = len(nodes)
    for t in range(T):
        arr = rng.random(nn) < lam
        for k in np.flatnonzero(arr):
            q[nodes[k]].append(t)
            gen += 1
        if proto == "tdma":
            tx = [v for v in frame[t % F] if q[v]]
        elif proto == "aloha":
            tx = [v for v in nodes if q[v] and rng.random() < p]
        else:  # csma
            tx = []
            for v in nodes:
                if not q[v]:
                    continue
                busy = any(chan.comm[v, j] for j in prev_tx)
                if backoff[v] > 0:
                    if not busy:
                        backoff[v] -= 1
                    continue
                if busy:
                    backoff[v] = int(rng.integers(1, cw[v] + 1))
                else:
                    tx.append(v)
        txset = set(tx)
        for v in tx:
            attempts += 1
            if chan.success(v, int(parent[v]), txset):
                b = q[v].popleft()
                if parent[v] == 0:
                    delivered += 1
                    lat.append(t - b + 1)
                else:
                    q[int(parent[v])].append(b)
                if proto == "csma":
                    cw[v] = cw0
                    backoff[v] = int(rng.integers(1, cw0 + 1))
            else:
                fails += 1
                if proto == "csma":
                    cw[v] = min(cw[v] * 2, cwmax)
                    backoff[v] = int(rng.integers(1, cw[v] + 1))
        prev_tx = tx
    return {
        "throughput": delivered / T,                     # packets per slot at the gateway
        "delivery_ratio": delivered / max(gen, 1),
        "mean_latency": float(np.mean(lat)) if lat else float("nan"),
        "p95_latency": float(np.percentile(lat, 95)) if lat else float("nan"),
        "collision_rate": fails / max(attempts, 1),
        "tx_per_delivery": attempts / max(delivered, 1),  # energy proxy
        "generated": gen,
        "delivered": delivered,
    }
