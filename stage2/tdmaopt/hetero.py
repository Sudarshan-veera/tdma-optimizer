"""TDMA optimizer for radios with DIFFERENT ranges.

Input : number of radios and the maximum coverage range of each one (radio 0 = the user's radio / gateway),
        plus the minimum-separation rule (no radio closer to another than  sep x the smaller of their ranges).
Output: the best topology, the position of every radio, the distance of every link, the TDMA slot table.

    python3 -m tdmaopt.hetero                              # asks for the number of radios and each range
    python3 -m tdmaopt.hetero --ranges 500,300,300,200,200,100
    python3 -m tdmaopt.hetero --ranges 500,300,300,200 --goal frame --min-sep 0.6 --distance 900
"""
import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .schedule import conflict_graph, best_schedule, lower_bound, subtree_loads
from .topology import build_tree

RESULTS = Path(__file__).resolve().parent.parent / "results"


# --------------------------------------------------------------------------- channel with per-radio ranges
class HChannel:
    """Disk model, one range per radio. A link i-j works if d <= min(r_i, r_j) (both directions must work).
    A transmitter k jams any receiver within ri_factor * r_k.  Same interface as phy.Channel."""

    def __init__(self, pos, r, ri_factor=1.5, comm_scale=1.0):
        self.pos = np.asarray(pos, float)
        self.r = np.asarray(r, float)
        self.N = len(self.pos)
        self.D = np.linalg.norm(self.pos[:, None] - self.pos[None], axis=2)
        self.comm = (self.D <= comm_scale * np.minimum.outer(self.r, self.r) + 1e-9) & ~np.eye(self.N, dtype=bool)
        self.P = -self.D                      # "stronger" = closer (used for tie-breaks in build_tree)
        self.ri = ri_factor * self.r
        self.Rc = float(self.r[0])

    def success(self, tx, rx, txset):
        if rx in txset:
            return False
        return all(k == tx or self.D[k, rx] > self.ri[k] for k in txset)

    def link_conflict(self, i, pi, k, pk):
        if len({i, pi, k, pk}) < 4:
            return True
        both = {i, k}
        return (not self.success(i, pi, both)) or (not self.success(k, pk, both))


# --------------------------------------------------------------------------- topology structures
def structures(n):
    """name -> ("tree", parent, angle) per slot, or ("ring",).  Slot 0 is the gateway."""
    S = {}
    S["chain (path graph)"] = ("tree", [-1] + list(range(n - 1)), [0.0] * n)
    for a in sorted({2, 3, 4, 5, 6, 8, n - 1}):
        if 2 <= a <= n - 1:
            par, ang = [-1], [0.0]
            for k in range(1, n):
                arm, depth = (k - 1) % a, (k - 1) // a
                par.append(0 if depth == 0 else k - a)
                ang.append(2 * np.pi * arm / a)
            S["star" if a == n - 1 else f"spider, {a} arms"] = ("tree", par, ang)
    for b, nm in ((2, "binary tree"), (3, "ternary tree")):
        par, ang = [-1], [0.0]
        for k in range(1, n):
            p = (k - 1) // b
            par.append(p)
            ang.append(2 * np.pi * (k - 1) / b if p == 0 else ang[p] + ((k - 1) % b - (b - 1) / 2) * np.radians(40))
        S[nm] = ("tree", par, ang)
    if n >= 4:
        s = (n + 1) // 2
        par, ang = [-1] + list(range(s - 1)), [0.0] * s
        for i in range(n - s):
            par.append(i // 2)
            ang.append(np.pi / 2 if i % 2 == 0 else -np.pi / 2)
        S["comb"] = ("tree", par, ang)
        S["ring (cycle graph)"] = ("ring",)
    return S


def orderings(r, K, rng):
    ids = list(range(1, len(r)))
    desc = sorted(ids, key=lambda i: -r[i])
    asc = desc[::-1]
    alt = []
    lo, hi = 0, len(desc) - 1
    while lo <= hi:
        alt.append(desc[lo]); lo += 1
        if lo <= hi:
            alt.append(desc[hi]); hi -= 1
    out = [("largest ranges near the user", desc), ("smallest ranges near the user", asc), ("alternating", alt)]
    for t in range(K):
        out.append((f"random #{t + 1}", list(rng.permutation(ids))))
    return out


def place(struct, perm, r, margin):
    """Positions indexed by radio id. Link length = margin x min(range of the two ends)."""
    n = len(r)
    radio_of = [0] + [int(v) for v in perm]
    pos = np.zeros((n, 2))
    if struct[0] == "ring":
        chord = margin * float(np.min(r))
        R = chord / (2 * np.sin(np.pi / n))
        for k in range(n):
            th = -np.pi / 2 + 2 * np.pi * k / n
            pos[radio_of[k]] = (R * np.cos(th), R + R * np.sin(th))
        return pos
    _, par, ang = struct
    xy = np.zeros((n, 2))
    for k in range(1, n):
        L = margin * min(r[radio_of[par[k]]], r[radio_of[k]])
        xy[k] = xy[par[k]] + L * np.array([np.cos(ang[k]), np.sin(ang[k])])
    for k in range(n):
        pos[radio_of[k]] = xy[k]
    return pos


# --------------------------------------------------------------------------- evaluation
def union_area(pos, r, div=8):
    """Area covered by the union of all coverage discs (m2). Grid cell = smallest range / div; each disc only touches its own bounding box."""
    cell = float(r.min()) / div
    x0, x1 = (pos[:, 0] - r).min(), (pos[:, 0] + r).max()
    y0, y1 = (pos[:, 1] - r).min(), (pos[:, 1] + r).max()
    while ((x1 - x0) / cell + 2) * ((y1 - y0) / cell + 2) > 8e6:
        cell *= 1.5
    nx, ny = int(np.ceil((x1 - x0) / cell)) + 1, int(np.ceil((y1 - y0) / cell)) + 1
    m = np.zeros((ny, nx), bool)
    for (x, y), rr in zip(pos, r):
        i0, i1 = max(int((x - rr - x0) / cell), 0), min(int((x + rr - x0) / cell) + 1, nx - 1)
        j0, j1 = max(int((y - rr - y0) / cell), 0), min(int((y + rr - y0) / cell) + 1, ny - 1)
        xs = x0 + (np.arange(i0, i1 + 1) + 0.5) * cell
        ys = y0 + (np.arange(j0, j1 + 1) + 0.5) * cell
        m[j0:j1 + 1, i0:i1 + 1] |= (xs[None, :] - x) ** 2 + (ys[:, None] - y) ** 2 <= rr * rr
    return float(m.sum() * cell * cell)


def evaluate(pos, r, sep, local=None, scale=1.0, res=8, want_area=True, ri=None):
    """scale = usable fraction of a link's range (fade margin): a link exists only if d <= scale x min(r_i, r_j)."""
    n = len(r)
    chan = HChannel(pos, r, ri_factor=ri, comm_scale=scale)
    need = sep * np.minimum.outer(r, r)
    np.fill_diagonal(need, 0)
    viol = (chan.D < need - 1e-6) & ~np.eye(n, dtype=bool)
    if viol.any():
        i, j = np.unravel_index(np.argmax(np.where(viol, need - chan.D, -1)), viol.shape)
        return {"ok": False, "reason": f"radios {i} and {j} only {chan.D[i, j]:.0f} m apart (rule needs >= {need[i, j]:.0f} m)"}
    parent, hops = build_tree(chan)
    if (parent == -2).any():
        return {"ok": False, "reason": "disconnected"}
    adj = conflict_graph(chan, parent)
    dem = subtree_loads(parent, local)
    slots, F = best_schedule(adj, dem)
    reach = float(chan.D[0].max())
    return {"ok": True, "chan": chan, "parent": parent, "hops": hops, "adj": adj, "demand": dem, "slots": slots,
            "F": F, "LB": lower_bound(adj, dem), "reach": reach, "hops_max": int(hops.max()),
            "latency": int(hops.max()) * F, "area": union_area(pos, r, res) if want_area else 0.0}


GOALS = {
    "area": ("largest covered area (frame length breaks ties)", lambda e: (-e["area"], e["F"])),
    "reach": ("farthest radio from the user", lambda e: (-e["reach"], e["F"])),
    "frame": ("shortest TDMA frame = highest throughput", lambda e: (e["F"], e["latency"], -e["area"])),
    "balanced": ("most covered area per slot", lambda e: (-e["area"] / e["F"], e["F"])),
}


def optimize(r, sep, margin, ri, goal, distance=None, max_frame=None, users=0, K=30, seed=1, steps=0, starts_n=4):
    n = len(r)
    rng = np.random.default_rng(seed)
    local = None
    if users > 0:
        c = np.random.default_rng(seed + 99).multinomial(users, [1.0 / (n - 1)] * (n - 1))
        local = {i: 1 + int(c[i - 1]) for i in range(1, n)}
    key = GOALS[goal][1]
    best, rejected = {}, {}
    for name, st in structures(n).items():
        same = float(np.ptp(r[1:])) == 0.0            # identical radios: which one goes where makes no difference
        perms = orderings(r, K, rng) if (st[0] == "tree" and not same) else orderings(r, 0, rng)[:1]
        for oname, perm in perms:
            pos = place(st, perm, r, margin)
            ev = evaluate(pos, r, sep, local, margin, ri=ri)
            if not ev["ok"]:
                rejected.setdefault(name, ev["reason"])
                continue
            if distance and ev["reach"] < distance:
                rejected[name] = f"reach {ev['reach']:.0f} m < target {distance:.0f} m"
                continue
            if max_frame and ev["F"] > max_frame:
                rejected[name] = f"frame {ev['F']} > allowed {max_frame}"
                continue
            rejected.pop(name, None)
            if name not in best or key(ev) < key(best[name]["ev"]):
                best[name] = {"ev": ev, "order": oname, "pos": pos}
    ranked = sorted(best.items(), key=lambda kv: key(kv[1]["ev"]))
    for nm in best:
        rejected.pop(nm, None)
    if steps > 0 and ranked:
        starts = [e["pos"] - e["pos"][0] for _, e in ranked[:starts_n]]
        found = search_layout(r, sep, margin, goal, starts, local, distance, max_frame, steps, rng, ri)
        if found is not None:
            ranked.append(("custom (searched layout)", found))
            ranked.sort(key=lambda kv: key(kv[1]["ev"]))
    total = sum(local.values()) if local else n - 1
    return ranked, rejected, total, local


# --------------------------------------------------------------------------- output
def layout_rows(entry, r):
    ev, pos = entry["ev"], entry["pos"]
    ch, par = ev["chan"], ev["parent"]
    rows = []
    for v in range(len(r)):
        rows.append({"radio": v, "range_m": float(r[v]), "x_m": round(float(pos[v, 0]), 1), "y_m": round(float(pos[v, 1]), 1),
                     "parent": int(par[v]), "link_m": round(float(ch.D[v, par[v]]), 1) if par[v] >= 0 else None,
                     "hops": int(ev["hops"][v]), "tx_slots": [int(s) for s in ev["slots"].get(v, [])]})
    return rows


# --------------------------------------------------------------------------- free-form search (our own topology)
def _descendants(parent, v):
    out, stack = {v}, [v]
    while stack:
        u = stack.pop()
        for w in range(len(parent)):
            if parent[w] == u and w not in out:
                out.add(w)
                stack.append(w)
    return out


def search_layout(r, sep, margin, goal, starts, local, distance, max_frame, steps, rng, ri):
    """Simulated annealing over the radios' coordinates.  Starts from the best preset layouts and is free to
    invent any shape: move a radio next to another, nudge it, swap two radios, or swing a whole branch around its parent.
    Layouts that break the separation rule, disconnect the network, or miss --distance / --max-frame are never accepted."""
    n = len(r)

    def ok(ev):
        return ev["ok"] and (not distance or ev["reach"] >= distance) and (not max_frame or ev["F"] <= max_frame)

    ev0 = evaluate(starts[0], r, sep, local, margin, ri=ri, res=3)
    A0, R0, F0 = ev0["area"], ev0["reach"], ev0["F"]

    def energy(ev):
        if goal == "area":
            return -ev["area"] / A0 + 0.05 * ev["F"] / F0
        if goal == "reach":
            return -ev["reach"] / R0 + 0.05 * ev["F"] / F0
        if goal == "frame":
            return ev["F"] / F0 - 0.05 * ev["area"] / A0
        return -(ev["area"] / ev["F"]) / (A0 / F0)

    def propose(pos, ev):
        P, v, m = pos.copy(), int(rng.integers(1, n)), rng.random()
        if m < 0.35:
            u = int(rng.integers(0, n))
            u = 0 if u == v else u
            dist = rng.uniform(sep, margin) * min(r[u], r[v])
            th = rng.uniform(0, 2 * np.pi)
            P[v] = P[u] + dist * np.array([np.cos(th), np.sin(th)])
        elif m < 0.6:
            P[v] = P[v] + rng.normal(0, 0.08 * r[v], 2)
        elif m < 0.8 and n > 2:
            w = int(rng.integers(1, n))
            if w != v:
                P[[v, w]] = P[[w, v]]
        else:
            par = ev["parent"]
            grp = list(_descendants(par, v))
            piv, a = P[par[v]].copy(), rng.normal(0, 0.6)
            c, s_ = np.cos(a), np.sin(a)
            d = P[grp] - piv
            P[grp] = piv + np.stack([c * d[:, 0] - s_ * d[:, 1], s_ * d[:, 0] + c * d[:, 1]], axis=1)
        return P

    best = None
    for st in starts:
        cur = st.copy()
        ec = evaluate(cur, r, sep, local, margin, ri=ri, res=3)
        if not ok(ec):
            continue
        Ec = energy(ec)
        bp, bE = cur.copy(), Ec
        T0, T1 = 0.03, 0.0005
        for t in range(steps):
            T = T0 * (T1 / T0) ** (t / max(steps - 1, 1))
            cand = propose(cur, ec)
            ev = evaluate(cand, r, sep, local, margin, ri=ri, res=3, want_area=goal != "frame" or True)
            if not ok(ev):
                continue
            E = energy(ev)
            if E < Ec or rng.random() < np.exp(-(E - Ec) / T):
                cur, ec, Ec = cand, ev, E
                if Ec < bE:
                    bp, bE = cur.copy(), Ec
        if best is None or bE < best[0]:
            best = (bE, bp)
    if best is None:
        return None
    pos = best[1] - best[1][0]                         # gateway at the origin
    ev = evaluate(pos, r, sep, local, margin, ri=ri)
    return {"ev": ev, "order": "free-form search", "pos": pos} if ok(ev) else None


def draw_best(name, entry, r, path, goal):
    ev, pos = entry["ev"], entry["pos"]
    ch, par = ev["chan"], ev["parent"]
    fig, ax = plt.subplots(1, 2, figsize=(15, 6.5), gridspec_kw={"width_ratios": [1.5, 1]})
    a = ax[0]
    cols = plt.cm.tab10(np.arange(len(r)) % 10)
    for v in range(len(r)):
        a.add_patch(plt.Circle(pos[v], r[v], color=cols[v], alpha=0.10, lw=0))
        a.add_patch(plt.Circle(pos[v], r[v], fill=False, ec=cols[v], lw=0.8, ls=":"))
    for v in range(1, len(r)):
        p = par[v]
        a.annotate("", xy=pos[p], xytext=pos[v], arrowprops=dict(arrowstyle="-|>", color="k", lw=1.6, shrinkA=8, shrinkB=8))
        m = (pos[v] + pos[p]) / 2
        if len(r) <= 25:
            a.text(m[0], m[1], f"{ch.D[v, p]:.0f} m", fontsize=7, ha="center", va="bottom",
                   bbox=dict(fc="white", ec="none", alpha=0.7, pad=0.5))
    a.scatter(pos[:, 0], pos[:, 1], c=cols, s=150, edgecolors="k", zorder=5)
    a.scatter(*pos[0], marker="*", s=450, c="gold", edgecolors="k", zorder=6)
    for v in range(len(r)):
        if len(r) <= 25:
            a.text(pos[v, 0], pos[v, 1] - 0.045 * r.max(), f"{v}\n({r[v]:.0f} m)", ha="center", va="top", fontsize=7, zorder=7)
        elif len(r) <= 100:
            a.text(pos[v, 0], pos[v, 1], str(v), ha="center", va="center", fontsize=5, zorder=7)
    a.set_aspect("equal"); a.autoscale()
    a.set_title(f"{name}: {len(r)} radios, covered area {ev['area'] / 1e6:.3f} km2, reach {ev['reach']:.0f} m, "
                f"frame {ev['F']} slots\n(star = user's radio, circles = each radio's coverage, arrows = uplink to parent)", fontsize=9)
    b = ax[1]
    F = ev["F"]
    for v, ss in ev["slots"].items():
        for s in ss:
            b.add_patch(plt.Rectangle((s, v - 0.4), 1, 0.8, color=cols[v], ec="k", lw=0.4))
    b.set_xlim(0, F); b.set_ylim(0.5, len(r) - 0.5)
    b.set_yticks(range(1, len(r))); b.set_xlabel("slot in frame"); b.set_ylabel("transmitting radio")
    b.set_title(f"TDMA frame ({F} slots); radios far apart reuse the same slot", fontsize=9)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def draw_compare(ranked, path):
    fig, a = plt.subplots(figsize=(7.5, 5))
    for nm, e in ranked:
        ev = e["ev"]
        a.scatter(ev["F"], ev["area"] / 1e6, s=60, zorder=3)
        a.annotate(nm, (ev["F"], ev["area"] / 1e6), fontsize=7, xytext=(4, 3), textcoords="offset points")
    a.set_xlabel("TDMA frame length (slots), lower is better"); a.set_ylabel("covered area (km2), higher is better")
    a.set_title("every feasible topology (best arrangement of each)")
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def ask(text, cast, ok, hint):
    """Keep asking until the user types a valid value. There are no default values."""
    while True:
        try:
            raw = input(f"{text}: ").strip()
        except EOFError:
            raise SystemExit(f"\nNo value given for: {text}. Run the program in a terminal, or pass it as a flag (see --help).")
        try:
            v = cast(raw)
            if ok(v):
                return v
        except ValueError:
            pass
        print(f"   not valid: {hint}")


def get_inputs(a):
    """The two problem inputs come from the user: number of radios and effective coverage. Nothing is assumed."""
    n = a.n
    vals = None
    if a.ranges:
        vals = [float(x) for t in a.ranges for x in t.split(",") if x.strip()]
        n = n or (len(vals) if len(vals) > 1 else None)
    if n is None:
        n = ask("Total number of radios to configure (including your own radio)", int, lambda v: v >= 2, "a whole number, at least 2")
    if vals is None:
        print("Effective coverage distance of a radio, in metres.")
        txt = ask("  One number if every radio is the same, or one number per radio separated by commas (radio 0 = yours)",
                  lambda t: [float(x) for x in t.replace(" ", "").split(",") if x],
                  lambda v: len(v) in (1, n) and all(x > 0 for x in v), f"1 positive number, or exactly {n} positive numbers")
        vals = txt
    if len(vals) == 1:
        vals = vals * n
    if len(vals) != n:
        raise SystemExit(f"{n} radios but {len(vals)} coverage values were given")
    if a.sep is not None and not 0 <= a.sep < 1:
        raise SystemExit("--min-sep must be in [0, 1)")
    margin = a.margin
    if not (a.sep <= margin <= 1 and margin > 0):
        raise SystemExit("--link-margin must be between --min-sep and 1")
    return n, np.array(vals, float)


def main():
    ap = argparse.ArgumentParser(description="TDMA optimizer: give the number of radios and their effective coverage; "
                                             "it analyses every topology and arrangement and sorts them for the best case.")
    ap.add_argument("--n", type=int, help="total number of radios (asked if missing)")
    ap.add_argument("--ranges", "--coverage", nargs="*", dest="ranges",
                    help="effective coverage in metres: one value for all radios, or one per radio (radio 0 = yours); asked if missing")
    ap.add_argument("--distance", type=float, default=None, help="optional: coverage distance you need from your radio (m)")
    ap.add_argument("--min-sep", type=float, dest="sep", default=0.5, help="model setting: no radios closer than this x the smaller range")
    ap.add_argument("--link-margin", type=float, dest="margin", default=0.9, help="model setting: link length = this x the weaker range")
    ap.add_argument("--interference", type=float, dest="ri", default=1.5, help="model setting: interference range = this x a radio's range")
    ap.add_argument("--steps", type=int, default=400, help="search effort for the free-form layout (0 = presets only)")
    ap.add_argument("--starts", type=int, default=2, help="search effort: number of start layouts")
    ap.add_argument("--tries", type=int, default=30, help="search effort: orderings tried per preset topology (unequal ranges)")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    n, r = get_inputs(a)
    sep, margin, ri, dist = a.sep, a.margin, a.ri, a.distance
    RESULTS.mkdir(exist_ok=True)
    tag = f"opt_n{n}"
    same = float(np.ptp(r)) == 0.0

    seq = [r[0]] + sorted(r[1:])[::-1]
    max_reach = margin * sum(min(x, y) for x, y in zip(seq, seq[1:]))
    L = [f"# TDMA optimizer: {n} radios", "", "## Your inputs", "",
         f"* Number of radios: {n} (radio 0 = yours)",
         f"* Effective coverage: " + (f"{r[0]:g} m for every radio" if same else ", ".join(f"{x:g}" for x in r) + " m"),
         f"* Needed distance from your radio: " + (f"{dist:g} m" if dist else "not set (all arrangements are compared)"), "",
         "Model settings (change with flags): no two radios closer than "
         f"{sep:g} x the smaller range; links built at {margin:g} x the weaker range; a transmitter blocks receivers within {ri:g} x its range. "
         f"Every radio sends 1 packet per frame to your radio (forwarding included), so a frame has at least {n - 1} slots.", ""]
    feasible = (dist is None) or dist <= max_reach + 1e-9
    goal = "balanced"
    if not feasible:
        L += [f"**{dist:g} m cannot be reached with these {n} radios** (the best straight line reaches {max_reach:.0f} m at this link length). "
              f"Add radios, use longer coverage, or lower the distance. Showing the farthest layout instead.", ""]
        goal, dist = "reach", None
    ranked, rejected, total, _ = optimize(r, sep, margin, ri, goal, distance=dist, steps=a.steps, starts_n=a.starts,
                                          K=a.tries, seed=a.seed)
    if not ranked:
        L.append("No arrangement satisfies the rules.")
        for k, v in rejected.items():
            L.append(f"* {k}: {v}")
        txt = "\n".join(L); (RESULTS / f"{tag}.md").write_text(txt); print(txt); return
    how = {"balanced": "most covered area per TDMA slot", "reach": "farthest reach"}[goal]
    L += [f"## All feasible topologies, sorted best case first ({how})", "",
          "| # | topology | frame (slots) | reach (m) | hops | latency bound (slots) | covered area (km2) | area per slot (km2) |",
          "|---|---|---|---|---|---|---|---|"]
    for i, (nm, e) in enumerate(ranked, 1):
        ev = e["ev"]
        L.append(f"| {i} | {nm} | {ev['F']} | {ev['reach']:.0f} | {ev['hops_max']} | {ev['latency']} | {ev['area'] / 1e6:.3f} | {ev['area'] / 1e6 / ev['F']:.4f} |")
    if rejected:
        L += ["", "Not possible with these radios and rules: " + "; ".join(f"{k} ({v})" for k, v in rejected.items())]
    pick = lambda f: min(ranked, key=lambda kv: f(kv[1]["ev"]))[0]
    L += ["", "Best case for each goal:", "",
          f"* shortest frame (highest throughput): **{pick(lambda e: (e['F'], e['latency']))}**",
          f"* lowest latency: **{pick(lambda e: (e['latency'], e['F']))}**",
          f"* farthest reach: **{pick(lambda e: (-e['reach'], e['F']))}**",
          f"* largest covered area: **{pick(lambda e: (-e['area'], e['F']))}**",
          f"* best balance (area per slot): **{ranked[0][0]}**"]
    name, top = ranked[0]
    ev = top["ev"]
    L += ["", f"## Chosen arrangement: **{name}**", "",
          f"Farthest radio is {ev['reach']:.0f} m from your radio over {ev['hops_max']} hops; one TDMA frame is {ev['F']} slots "
          f"(minimum possible {total}); covered area {ev['area'] / 1e6:.3f} km2.", "",
          "| radio | range (m) | x (m) | y (m) | sends to | distance to that radio (m) | hops | transmit slots |",
          "|---|---|---|---|---|---|---|---|"]
    rows = layout_rows(top, r)
    for w in rows:
        sl = w['tx_slots']
        sl_txt = (','.join(map(str, sl)) if len(sl) <= 6 else f"{sl[0]}..{sl[-1]} ({len(sl)} slots)") if sl else '-'
        L.append(f"| {w['radio']}{' (yours)' if w['radio'] == 0 else ''} | {w['range_m']:g} | {w['x_m']} | {w['y_m']} | "
                 f"{w['parent'] if w['parent'] >= 0 else '-'} | {w['link_m'] if w['link_m'] is not None else '-'} | {w['hops']} | {sl_txt} |")
    L += ["", "Coordinates are in metres with your radio at (0, 0); exact slot lists are in the CSV. Slot assignment is greedy."]
    txt = "\n".join(L)
    (RESULTS / f"{tag}.md").write_text(txt)
    print("\n" + txt)
    with open(RESULTS / f"{tag}_layout.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["radio", "range_m", "x_m", "y_m", "parent", "link_m", "hops", "tx_slots"])
        for x in rows:
            w.writerow([x["radio"], x["range_m"], x["x_m"], x["y_m"], x["parent"], x["link_m"], x["hops"], " ".join(map(str, x["tx_slots"]))])
    (RESULTS / f"{tag}.json").write_text(json.dumps(
        {"inputs": {"ranges_m": r.tolist(), "distance_m": a.distance, "min_sep": sep, "link_margin": margin, "interference": ri},
         "best": name, "frame": ev["F"], "area_m2": ev["area"], "reach_m": ev["reach"], "layout": rows,
         "ranking": [{"topology": k, "frame": e["ev"]["F"], "area_m2": e["ev"]["area"], "reach_m": e["ev"]["reach"]} for k, e in ranked]},
        indent=2))
    draw_best(name, top, r, RESULTS / f"{tag}_best.png", goal)
    draw_compare(ranked, RESULTS / f"{tag}_compare.png")
    print(f"\nwrote results/{tag}.md  .json  _layout.csv  _best.png  _compare.png")


if __name__ == "__main__":
    main()
