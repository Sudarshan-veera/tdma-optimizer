"""Closed-form results for convergecast TDMA under the disk model.

Setting: every non-gateway radio generates one packet per frame; links are at most mu*R long (R = radio range);
a transmitter blocks every receiver within rho*R.  Define the conflict reach  g = floor(rho/mu) + 1.

Lemma 1 (gateway cut)      F >= N-1 (+ attached users).
Lemma 2 (path window)      Along any tree path, links whose indices differ by at most g conflict, whatever the geometry
                           (triangle inequality), so g+1 consecutive links form a clique.
Theorem 1 (lower bound)    If some radio must lie >= D from the gateway, the tree contains a path of l = ceil(D/(mu R)) hops
                           and  F >= max(N-1, W(l)),  W(l) = sum of the loads of its first min(g+1,l) links
                           = (g+1)*l - g(g+1)/2  for l >= g+1,  l(l+1)/2 otherwise.
Theorem 2 (tightness)      With conflict-free spacing between arms (see `arms_conflict_free`), a spider with one straight arm
                           of l radios and the rest on other arms meets the bound, provided the schedule is optimal
                           (best_schedule is optimal here because the conflict graph is chordal).
"""
import math

import numpy as np


def reach_hops(rho, mu):
    return int(math.floor(rho / mu + 1e-12)) + 1


def window(l, g):
    """Total load of the first min(g+1, l) links of a unit-load arm with l radios (loads l, l-1, ...)."""
    k = min(g + 1, l)
    return sum(l - j for j in range(k))


def chain_frame(N, rho, mu):
    """Exact minimum frame of a straight chain of N radios (gateway + N-1 relays) with unit demand."""
    return max(N - 1, window(N - 1, reach_hops(rho, mu)))


def frame_lower_bound(N, D, R, mu, rho, users=0):
    """Smallest frame ANY tree topology can have if a radio must be >= D metres from the gateway."""
    l = math.ceil(D / (mu * R) - 1e-12)
    if l > N - 1:
        return None                                    # not reachable with N radios
    return max(N - 1 + users, window(l, reach_hops(rho, mu)))


def arms_conflict_free(mu, rho, arms):
    """Do first-hop radios of different arms stay out of each other's interference range (beyond the shared gateway)?
    Two arms are opposite (distance 2 mu R); three arms are 120 deg apart (distance sqrt(3) mu R)."""
    return rho < {1: 99.0, 2: 2.0 * mu, 3: math.sqrt(3.0) * mu}.get(arms, 0.0)


def spider_arms(N, l):
    """Arm lengths: one arm of exactly >= l radios, remaining radios on at most two more arms."""
    rest = N - 1
    first = max(l, math.ceil(rest / 3))
    first = min(first, rest)
    left = rest - first
    if left == 0:
        return [first]
    a = math.ceil(left / 2)
    return [first, a] if left - a == 0 else [first, a, left - a]


def spider_positions(arms, step):
    """Gateway at the origin, arms at 0 / 180 deg (two arms) or 0 / 120 / 240 deg (three arms)."""
    angles = {1: [0.0], 2: [0.0, math.pi], 3: [0.0, 2 * math.pi / 3, 4 * math.pi / 3]}[len(arms)]
    pts = [(0.0, 0.0)]
    for L, th in zip(arms, angles):
        for j in range(1, L + 1):
            pts.append((j * step * math.cos(th), j * step * math.sin(th)))
    return np.array(pts)
