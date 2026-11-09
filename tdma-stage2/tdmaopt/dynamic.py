"""Incremental scheduling: handle a node joining or leaving without recomputing the whole schedule."""
import numpy as np

from .phy import PHY, Channel
from .schedule import conflict_graph, count_violations, frame_length, greedy_schedule


class DynamicNet:
    """Stable integer ids. id 0 is the gateway. Disk model."""

    def __init__(self, phy: PHY, pos_by_id: dict):
        self.phy = phy
        self.pos = {int(k): tuple(v) for k, v in pos_by_id.items()}
        self.parent = {}
        self.slots = {}
        self._refresh_channel()
        self._full_tree()
        self.full_reschedule()

    # ---- helpers --------------------------------------------------------
    def _refresh_channel(self):
        self.ids = sorted(self.pos)
        self.ix = {v: i for i, v in enumerate(self.ids)}
        self.chan = Channel(np.array([self.pos[v] for v in self.ids]), self.phy, model="disk")

    def _comm(self, a, b):
        return bool(self.chan.comm[self.ix[a], self.ix[b]])

    def _hops(self):
        h = {0: 0}
        changed = True
        while changed:
            changed = False
            for v, p in self.parent.items():
                if p >= 0 and p in h and (v not in h or h[v] != h[p] + 1):
                    h[v] = h[p] + 1
                    changed = True
        return h

    def _full_tree(self):
        from .topology import build_tree
        par, _ = build_tree(self.chan)
        self.parent = {self.ids[i]: (self.ids[par[i]] if par[i] >= 0 else int(par[i]))
                       for i in range(len(self.ids)) if i != 0}

    def _best_parent(self, v, exclude=()):
        h = self._hops()
        cands = [u for u in h if u != v and u not in exclude and self._comm(v, u)]
        if not cands:
            return -2
        return min(cands, key=lambda u: (h[u], -self.chan.P[self.ix[v], self.ix[u]]))

    def _loads(self):
        """Packets per frame each reachable node must send (own + forwarded). Nodes whose path to
        the gateway is broken are cut off and get no entry."""
        load = {}
        for v, p in self.parent.items():
            if p < 0:
                continue
            path, u, seen, ok = [v], p, {v}, True
            while u != 0:
                if u in seen or self.parent.get(u, -2) < 0:
                    ok = False
                    break
                seen.add(u)
                path.append(u)
                u = self.parent[u]
            if ok:
                for w in path:
                    load[w] = load.get(w, 0) + 1
        return load

    def _parent_arr(self):
        arr = np.full(len(self.ids), -2)
        arr[0] = -1
        for v in self._loads():
            arr[self.ix[v]] = self.ix[self.parent[v]]
        return arr

    def _graph(self):
        pa = self._parent_arr()
        adj_ix = conflict_graph(self.chan, pa)
        return {self.ids[i]: {self.ids[j] for j in s} for i, s in adj_ix.items()}

    def _descendants(self, v):
        out, stack = set(), [v]
        while stack:
            u = stack.pop()
            for w, p in self.parent.items():
                if p == u and w not in out:
                    out.add(w)
                    stack.append(w)
        return out

    # ---- public ---------------------------------------------------------
    def full_reschedule(self):
        adj = self._graph()
        self.demand = self._loads()
        self.slots, F = greedy_schedule(adj, self.demand)
        return len(self.slots), F

    def valid(self):
        adj = self._graph()
        bad, _ = count_violations(adj, self.slots)
        return bad == 0

    def _incremental(self, parent_changed):
        old_demand = dict(self.demand)
        self.demand = self._loads()
        affected = set(parent_changed)
        for v, d in self.demand.items():
            if old_demand.get(v) != d:
                affected.add(v)
        affected = {v for v in affected if v in self.demand}
        adj = self._graph()
        fixed = {v: s for v, s in self.slots.items() if v in self.demand and v not in affected}
        # anything that still clashes with its neighbours must move too
        changed = True
        while changed:
            changed = False
            for v in list(fixed):
                if any(set(fixed[v]) & set(fixed.get(u, ())) for u in adj[v] if u in fixed):
                    affected.add(v)
                    del fixed[v]
                    changed = True
        self.slots, F = greedy_schedule(adj, self.demand, fixed=fixed)
        return len(affected), F

    def join(self, v, xy):
        self.pos[v] = tuple(xy)
        self._refresh_channel()
        self.parent[v] = -2
        self.parent[v] = self._best_parent(v, exclude=(v,))
        return self._incremental({v})

    def leave(self, v):
        orphans = [w for w, p in self.parent.items() if p == v]
        del self.pos[v]
        del self.parent[v]
        self._refresh_channel()
        for c in orphans:                 # detach; their subtrees follow them
            self.parent[c] = -2
        progress = True
        while progress:                   # re-attach to the surviving tree where a link exists
            progress = False
            for c in orphans:
                if self.parent[c] == -2:
                    np_ = self._best_parent(c)
                    if np_ != -2:
                        self.parent[c] = np_
                        progress = True
        return self._incremental(set(orphans))
