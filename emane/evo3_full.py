#!/usr/bin/env python3
"""Evolution 3 FULL pipeline: the optimizer's best-case schedule + all eight advancements, for ANY n radios / coverage.

Input is results/opt_nN.json written by `python3 -m tdmaopt.hetero` (the best-case scheduler: it asks for n and coverage).
Nothing here assumes 12 radios: radio i = NEM i+1, gateway = NEM 1, relays/senders come from the optimizer's parent tree.

  python3 emane/evo3_full.py offline results/opt_nN.json --out DIR        (no EMANE needed)
  python3 emane/evo3_full.py all     results/opt_nN.json --out DIR        (inside the EMANE lab, see run_evo3_full.sh)
  python3 emane/evo3_full.py all     results/opt_nN.json --out DIR --dry-run   (control-flow test with a fake lab; NOT evidence)

Status of each advancement is written to the report (measured_emane / computed / simulated), so claims stay honest.
"""
import argparse
import json
import math
import os
import random
import statistics as st
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "emane"))

from tdmaopt.adaptive import AdaptiveTDMA                                   # noqa: E402
from tdmaopt.evolution import (ClockModel, DistributedSlotAgent, EnergyModel, EnergyProfile,   # noqa: E402
                               FadingSINRModel, MultiHopRouting, OnlineMetricPredictor,
                               SelfHealingManager, negotiate_distributed)
from tdmaopt.phy import fspl_db, phy_for_range                              # noqa: E402
from tdmaopt.schedule import best_schedule, count_violations, frame_length, greedy_schedule  # noqa: E402
from adaptive_bridge import PlanNetwork, full_schedule_xml, update_schedule_xml  # noqa: E402


# ----------------------------------------------------------------------------- topology
class Net:
    """Optimizer result as NEM-id graph. radio r -> NEM r+1, gateway = NEM 1."""

    def __init__(self, topo):
        self.topo = topo
        rows = sorted(topo["layout"], key=lambda r: int(r["radio"]))
        self.rows = rows
        self.frame = int(topo["frame"])
        self.ids = [r["radio"] + 1 for r in rows]
        self.gw = 1
        self.pos = {r["radio"] + 1: (r["x_m"], r["y_m"]) for r in rows}
        self.rng = {r["radio"] + 1: float(r["range_m"]) for r in rows}
        self.parent = {r["radio"] + 1: r["parent"] + 1 for r in rows if r["parent"] >= 0}
        self.slots = {r["radio"] + 1: list(r["tx_slots"]) for r in rows if r["parent"] >= 0}
        self.n = len(rows)
        self.cov = 1.0                                  # coverage multiplier (used only for resilience analysis)

    def dist(self, a, b):
        return math.dist(self.pos[a], self.pos[b])

    def in_range(self, a, b):                       # same rule as the EEL pathloss file in gen_evo3.py
        return a != b and self.dist(a, b) <= self.cov * min(self.rng[a], self.rng[b]) + 1e-9

    def children(self, node, parent=None):
        parent = parent or self.parent
        return [c for c, p in parent.items() if p == node]

    def subtree(self, node, parent=None):
        parent = parent or self.parent
        out, todo = [], [node]
        while todo:
            x = todo.pop()
            out.append(x)
            todo += self.children(x, parent)
        return out

    def path(self, node, parent=None):
        parent = parent or self.parent
        p, seen = [node], {node}
        while p[-1] != self.gw:
            nxt = parent.get(p[-1])
            if nxt is None or nxt in seen:
                return None
            p.append(nxt)
            seen.add(nxt)
        return p

    def topo_with_parents(self, parent, drop=()):
        rows = []
        for r in self.rows:
            nem = r["radio"] + 1
            if nem in drop:
                continue
            row = dict(r)
            if nem != self.gw:
                row["parent"] = parent[nem] - 1
            rows.append(row)
        return {"layout": rows}


def schedule_for(net, parent, drop=()):
    """Conflict-free schedule for an arbitrary parent tree (used after a failure). Returns {nem: [slots]}, frame."""
    pn = PlanNetwork(net.topo_with_parents(parent, drop))
    slots, frame = greedy_schedule(pn.adjacency, pn.demand)
    bad, _ = count_violations(pn.adjacency, slots)
    if bad:
        raise RuntimeError(f"recovery schedule has {bad} conflicts")
    return {r + 1: s for r, s in slots.items()}, frame


# ----------------------------------------------------------------------------- offline advancements
def distributed_scheduling(net):
    pn = PlanNetwork(net.topo)
    cap = max(net.frame * 4, sum(pn.demand.values()) + 1)
    agents = {r: DistributedSlotAgent(r, pn.adjacency[r], pn.demand[r], cap) for r in pn.demand}
    res = negotiate_distributed(agents)
    bad, total = count_violations(pn.adjacency, res)
    used = frame_length(res)
    return {"status": "computed_local_negotiation (not over real radio messages)", "radios": len(res),
            "conflict_violations": bad, "frame_distributed": used, "frame_centralized_best": net.frame,
            "frame_overhead_pct": round(100.0 * (used - net.frame) / net.frame, 1), "transmissions": total}


def _sinr_tools(net):
    sens, beta, noise = -90.0, 8.0, 10 ** (-100.0 / 10)
    pt = {k: phy_for_range(v).pt_dbm for k, v in net.rng.items()}
    pl = lambda d: float(fspl_db(1.0, 2.4e9) + 10 * 2.7 * math.log10(max(d, 1.0)))

    def power_mw(tx, rx, boost=0.0):
        return 10 ** ((pt[tx] + boost - pl(net.dist(tx, rx))) / 10)

    def slot_ok(txs, boost=0.0):
        """No fading: does every transmitter in this slot reach its parent with SINR >= beta and power >= sensitivity?"""
        for tx in txs:
            rx = net.parent[tx]
            sig = power_mw(tx, rx, boost)
            if 10 * math.log10(sig) < sens:
                return False
            intf = sum(power_mw(k, rx, boost) for k in txs if k != tx)
            if 10 * math.log10(sig / (noise + intf)) < beta:
                return False
        return True
    return pt, pl, slot_ok


def sinr_safe_schedule(net):
    """Re-pack the optimizer's transmissions so every slot passes the aggregate-SINR check (the disk-model schedule does not)."""
    pn = PlanNetwork(net.topo)
    _, _, slot_ok = _sinr_tools(net)
    adj = {r + 1: {x + 1 for x in v} for r, v in pn.adjacency.items()}
    units = sorted(((n, k) for n, sl in net.slots.items() for k in range(len(sl))),
                   key=lambda t: (-len(net.slots[t[0]]), t[0]))
    slots = []                                            # list of sets of nodes
    for n, _k in units:
        for s_ in slots:
            if n in s_ or any(m in adj[n] for m in s_):
                continue
            if slot_ok(s_ | {n}):
                s_.add(n)
                break
        else:
            if not slot_ok({n}):
                raise RuntimeError(f"NEM {n} cannot meet SINR even alone: link is too long for its coverage")
            slots.append({n})
    return {n: [i for i, s_ in enumerate(slots) if n in s_] for n in net.slots}, len(slots)


def fading_study(net, frames, seed, boosts=(0, 3, 6, 10, 15)):
    """Per-link SINR with each radio's power set by its own coverage (heterogeneous); concurrent tx per slot interfere."""
    frames = max(30, min(frames, 8000 // max(1, len(net.slots))))      # keep large networks tractable
    pt, pl, slot_ok = _sinr_tools(net)
    noise = 10 ** (-100.0 / 10)

    def run(slots, kind, boost):
        by_slot = {}
        for nem, sl in slots.items():
            for s_ in sl:
                by_slot.setdefault(s_, []).append(nem)
        m = FadingSINRModel(kind, rician_k=3.0, seed=seed, sinr_threshold_db=8.0)
        sent = got = 0
        for _ in range(1 if kind == "none" else frames):
            for txs in by_slot.values():
                for tx in txs:
                    rx = net.parent[tx]
                    sig = m.received_mw(pt[tx] + boost, pl(net.dist(tx, rx)))
                    intf = [m.received_mw(pt[k] + boost, pl(net.dist(k, rx))) for k in txs if k != tx]
                    sent += 1
                    if 10 * math.log10(max(sig, 1e-30)) >= -90.0 and m.allowed(sig, intf, noise):
                        got += 1
        return round(got / sent, 4)

    safe, safe_frame = sinr_safe_schedule(net)
    out = {"optimizer_schedule": {}, "sinr_safe_schedule": {}}
    for name, sl in (("optimizer_schedule", net.slots), ("sinr_safe_schedule", safe)):
        for kind in ("none", "rayleigh", "rician"):
            for boost in ((0,) if kind == "none" else boosts):
                out[name][f"{kind}+{boost}dB"] = run(sl, kind, boost)
    return {"status": "simulated (Monte Carlo, not EMANE; EMANE here uses binary 80/200 dB pathloss, so it cannot show SINR effects)",
            "frames": frames, "pdr": out, "frame_optimizer": net.frame, "frame_sinr_safe": safe_frame,
            "sinr_safe_frame_overhead_pct": round(100.0 * (safe_frame - net.frame) / net.frame, 1),
            "note": "no-fading rows show whether the schedule is SINR-safe at all; boost columns = extra transmit power as fade margin"}


def energy_study(net, profile, slot_us=1000):
    em = EnergyModel(profile)
    tx = {k: v for k, v in net.slots.items()}
    allslots = set(range(net.frame))
    base_rx, aware_rx, aware_sleep = {}, {}, {}
    for nem in net.ids:
        mine = set(tx.get(nem, []))
        base_rx[nem] = sorted(allslots - mine)
        kids = set()
        for c in net.children(nem):
            kids |= set(tx.get(c, []))
        aware_rx[nem] = sorted(kids - mine)
        aware_sleep[nem] = sorted(allslots - mine - set(aware_rx[nem]))
    base = em.estimate(tx, net.frame, slot_us, rx_slots=base_rx)
    aware = em.estimate(tx, net.frame, slot_us, rx_slots=aware_rx, sleep_slots=aware_sleep)
    tb = sum(v["total_j"] for v in base.values())
    ta = sum(v["total_j"] for v in aware.values())
    return {"status": "modelled (assumed power values, no hardware measurement)",
            "power_w": {"tx": profile.tx_w, "rx": profile.rx_w, "idle": profile.idle_w, "sleep": profile.sleep_w},
            "baseline_j_per_frame": tb, "aware_j_per_frame": ta,
            "saving_pct": round(100.0 * (1 - ta / tb), 2),
            "policy": "a radio listens only in slots where one of its own children transmits, sleeps otherwise"}


def clock_study(net, seed, slot_us, sim_s=60.0, beacon_s=1.0, drift_ppm=20.0, sync_jitter_us=1.0):
    r = random.Random(seed)
    clocks = {n: ClockModel(offset_us=r.uniform(-500, 500), drift_ppm=r.uniform(-drift_ppm, drift_ppm))
              for n in net.ids if n != net.gw}
    before0 = max(abs(c.offset_us) for c in clocks.values())
    worst_pre, t = 0.0, 0.0
    free = {n: ClockModel(c.offset_us, c.drift_ppm) for n, c in clocks.items()}
    while t < sim_s:
        for c in clocks.values():
            c.advance(beacon_s)
        worst_pre = max(worst_pre, max(abs(c.offset_us) for c in clocks.values()))
        for c in clocks.values():
            c.synchronize(0.0, c.offset_us)
            c.offset_us += r.gauss(0, sync_jitter_us)
        t += beacon_s
    for c in free.values():
        c.advance(sim_s)
    after = max(abs(c.offset_us) for c in clocks.values())
    guard = ClockModel.required_guard_us(clocks.values(), horizon_s=beacon_s)
    return {"status": "simulated (assumed drift, no hardware clocks)", "radios": len(clocks),
            "assumed_max_drift_ppm": drift_ppm, "beacon_interval_s": beacon_s,
            "initial_max_offset_us": round(before0, 1), "unsynchronised_offset_after_sim_us": round(max(abs(c.offset_us) for c in free.values()), 1),
            "worst_offset_before_a_beacon_us": round(worst_pre, 1), "offset_after_sync_us": round(after, 2),
            "recommended_guard_us": guard, "slot_us": slot_us, "guard_fraction_of_slot": round(guard / slot_us, 4),
            "guard_fits_in_slot": guard < slot_us}


def healing_sweep(net):
    """Every single relay failure: can every orphan re-attach outside the failed subtree, and what frame results?"""
    rows = []
    for f in sorted({p for p in net.parent.values() if p != net.gw}):
        sub = set(net.subtree(f))
        outside = {n: {p: 1.0 for p in net.ids if p not in sub and net.in_range(n, p)} for n in net.ids if n not in sub and n != net.gw}
        routing = MultiHopRouting(outside, gateway=net.gw)
        orphans = net.children(f)
        parents, ok = dict(net.parent), True
        for o in orphans:
            cand = {p: 1.0 for p in net.ids if p not in sub and net.in_range(o, p)}
            try:
                parents[o] = routing.best_parent(o, cand)
            except RuntimeError:
                ok = False
        frame = schedule_for(net, parents, drop=(f,))[1] if ok else None
        rows.append({"failed_relay": f, "orphans": orphans, "all_rehomed": ok,
                     "new_parents": {o: parents[o] for o in orphans}, "frame_after": frame})
    return {"status": "computed (algorithm level; the live test is reported separately)",
            "relay_failures_tested": len(rows), "recoverable": sum(r["all_rehomed"] for r in rows), "cases": rows}


def offline(net, args):
    prof = EnergyProfile(args.tx_w, args.rx_w, args.idle_w, args.sleep_w)
    slot_us = args.slot_ms * 1000
    return {"distributed_scheduling": distributed_scheduling(net),
            "fading_sinr": fading_study(net, args.frames, args.seed),
            "energy_aware": energy_study(net, prof),
            "clock_sync": clock_study(net, args.seed, int(slot_us)),
            "self_healing_algorithm": healing_sweep(net)}


# ----------------------------------------------------------------------------- lab (real EMANE or dry-run fake)
def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


class Lab:
    """Runs one traffic window through the optimizer's tree: senders -> relays -> gateway sink (multihop_probe.py)."""

    def __init__(self, net, out):
        self.net, self.out = net, Path(out)

    def apply(self, xml_text, tag):
        p = self.out / f"schedule_{tag}.xml"
        p.write_text(xml_text)
        sh(["emaneevent-tdmaschedule", str(p), "-i", "br0"])
        time.sleep(3)

    def _restart_events(self, cfg_dir):
        subprocess.run(["pkill", "-f", "emaneeventservice"], check=False)
        time.sleep(1)
        sh(["emaneeventservice", "-d", "-l", "3", "-f", str(Path(cfg_dir) / "eventservice.log"), "eventservice.xml"], cwd=str(cfg_dir))
        time.sleep(4)

    def reconfigure(self, topo, out, args):
        """Switch the lab to another coverage (pathloss file) and schedule: restart the event service with a new EEL."""
        import gen_evo3
        Path(out / "opt_resilient.json").write_text(json.dumps(topo))
        gen_evo3.main([str(out / "opt_resilient.json"), "--out", str(out / "cfg_resilient"), "--secs", str(args.secs),
                       "--load", str(args.load), "--slot-ms", str(args.slot_ms)])
        self._restart_events(out / "cfg_resilient")
        self.apply((out / "cfg_resilient/schedule_good.xml").read_text(), "resilient")

    def restore(self, out):
        if (out / "cfg_resilient").exists():
            self._restart_events(out / "cfg")
        self.apply((out / "schedule_good_ref.xml").read_text(), "restore")

    def _mac(self, nem):
        if not hasattr(self, "_macs"):
            self._macs = {}
        if nem not in self._macs:
            r = subprocess.run(["ip", "netns", "exec", f"n{nem}", "cat", "/sys/class/net/emane0/address"], capture_output=True, text=True)
            self._macs[nem] = r.stdout.strip() or None
        return self._macs[nem]

    def _static_neighbors(self, parents):
        """Unicast needs ARP, and the gateway never transmits (it only receives), so nobody could answer an ARP request:
        give every radio a permanent neighbour entry for its parent."""
        for node, parent in parents.items():
            mac = self._mac(parent)
            if mac:
                subprocess.run(["ip", "netns", "exec", f"n{node}", "ip", "neigh", "replace", f"10.100.0.{parent}",
                                "lladdr", mac, "dev", "emane0", "nud", "permanent"], check=False)

    def window(self, parents, pps, secs, dead=(), tag="w"):
        net, probe = self.net, str(ROOT / "emane/multihop_probe.py")
        logs = self.out / "logs"
        logs.mkdir(exist_ok=True)
        self._static_neighbors(parents)
        rep = self.out / f"{tag}_sink.json"
        run = secs + 8
        procs = []

        def spawn(nem, role, *a):
            fh = open(logs / f"{tag}_{role}{nem}.log", "w")
            procs.append(subprocess.Popen(["ip", "netns", "exec", f"n{nem}", "python3", probe, role, *a], stdout=fh, stderr=subprocess.STDOUT))
            return procs[-1]
        sink = spawn(net.gw, "sink", "--seconds", str(run), "--out", str(rep))
        relays = [spawn(r, "relay", "--nem", str(r), "--parent", str(parents[r]), "--seconds", str(run))
                  for r in sorted({p for p in parents.values() if p != net.gw}) if r not in dead]
        time.sleep(2)
        senders = [spawn(n, "send", "--nem", str(n), "--parent", str(parents[n]), "--pps", str(pps[n]), "--seconds", str(secs))
                   for n in sorted(parents) if n not in dead]
        for p in senders + relays + [sink]:
            p.wait()
        raw = json.loads(rep.read_text()) if rep.exists() else {}
        return summarize(net, parents, pps, secs, raw, dead)


class FakeLab(Lab):
    """Control-flow test only: a capacity model, NOT measurements."""

    def __init__(self, net, out, slot_us, frame, cap_slot):
        super().__init__(net, out)
        self.cap_slot = cap_slot
        self.slot_us, self.cur = slot_us, {n: list(s) for n, s in net.slots.items()}
        self.frame = frame
        self.rnd = random.Random(1)

    def apply(self, xml_text, tag):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_text)
        slots = {}
        for s in root.iter("slot"):
            if s.find("tx") is not None:
                for n in s.attrib["nodes"].split(","):
                    slots.setdefault(int(n), []).append(int(s.attrib["index"]))
        st_ = root.find("structure")
        if st_ is not None:
            self.frame = int(st_.attrib["slots"])
        self.cur = slots

    def reconfigure(self, topo, out, args):
        n2 = Net(topo)
        self.cur, self.frame = {n: list(v) for n, v in n2.slots.items()}, n2.frame

    def restore(self, out):
        self.cur, self.frame = {n: list(v) for n, v in self.net.slots.items()}, self.net.frame

    def window(self, parents, pps, secs, dead=(), tag="w"):
        net = self.net
        through = {n: 0.0 for n in parents}
        for o in parents:
            if o in dead:
                continue
            for hop in (net.path(o, parents) or [])[:-1]:
                through[hop] += pps[o]
        cap = {n: len(self.cur.get(n, [])) * self.cap_slot * 1e6 / (self.slot_us * self.frame) for n in parents}
        ratio = {n: min(1.0, cap[n] / through[n]) if through[n] > 0 else 1.0 for n in parents}
        raw = {}
        for o in parents:
            p = net.path(o, parents)
            if o in dead or p is None or any(h in dead for h in p):
                continue
            e2e = 1.0
            for h in p[:-1]:
                e2e *= ratio[h]
            sent = int(pps[o] * secs)
            got = int(sent * e2e * self.rnd.uniform(0.995, 1.0))
            if got:
                raw[str(o)] = {"received_unique": got, "mean_latency_ms": 30.0 * (len(p) - 1), "max_latency_ms": 60.0 * (len(p) - 1),
                               "mean_hops": len(p) - 2, "last_path": p}
        return summarize(net, parents, pps, secs, raw, dead)


def summarize(net, parents, pps, secs, raw, dead):
    per = {}
    for n in sorted(parents):
        sent = 0 if n in dead else int(pps[n] * secs)
        r = raw.get(str(n), {})
        got = int(r.get("received_unique", 0))
        per[n] = {"sent": sent, "received": got, "pdr": (got / sent) if sent else None,
                  "latency_ms": r.get("mean_latency_ms"), "hops": r.get("mean_hops"), "path": r.get("last_path")}
    tot_s = sum(v["sent"] for v in per.values())
    tot_r = sum(v["received"] for v in per.values())
    return {"per_origin": per, "sent": tot_s, "received": tot_r, "pdr": tot_r / tot_s if tot_s else None}


def pct(x):
    return None if x is None else round(100 * x, 2)


# ----------------------------------------------------------------------------- live advancements

def relay_multipliers(net, cap=3.0, step=0.05):
    """For each relay: the smallest coverage multiplier (same positions) at which all its orphans can re-attach elsewhere."""
    out, c = {}, 1.0
    relays = sorted({p for p in net.parent.values() if p != net.gw})
    while c <= cap + 1e-9 and len(out) < len(relays):
        net.cov = c
        for case in healing_sweep(net)["cases"]:
            if case["all_rehomed"] and case["failed_relay"] not in out:
                out[case["failed_relay"]] = round(c, 2)
        c += step
    net.cov = 1.0
    return out, relays


def scaled_topology(net, c, load, slot_us):
    """Same positions and tree, coverage x c, schedule recomputed by the best-case scheduler for the new interference."""
    topo = json.loads(json.dumps(net.topo))
    for r in topo["layout"]:
        r["range_m"] = round(r["range_m"] * c, 3)
    pn = PlanNetwork(topo)
    slots, frame = best_schedule(pn.adjacency, pn.demand)
    for r in topo["layout"]:
        r["tx_slots"] = list(slots.get(r["radio"], []))
    topo["frame"] = frame
    topo["best"] = f"{net.topo.get('best')} (coverage x{c} for resilience)"
    return topo


def heal_live(net, plan, args, lab, out):
    slot_us = plan["slot_us"]
    per_relay, relays = relay_multipliers(net)
    base_ok = healing_sweep(net)
    info = {"relay_failures_tested": base_ok["relay_failures_tested"], "recoverable_at_design_coverage": base_ok["recoverable"],
            "coverage_multiplier_needed_per_relay": {str(k): v for k, v in sorted(per_relay.items())},
            "relays_never_recoverable_within_3x": [r for r in relays if r not in per_relay]}
    if base_ok["relay_failures_tested"] == 0:
        return {"status": "not_applicable", "reason": "no relays: every radio talks directly to the gateway", **info}
    topo_h, net_h, restore, mult, target = net.topo, net, False, 1.0, None
    if base_ok["recoverable"] == 0:
        if not per_relay:
            return {"status": "not_testable", "reason": "no relay failure can be recovered even at 3x coverage (the layout is a set of chains)", **info}
        if not args.resilient:
            return {"status": "not_testable_at_design_coverage", "reason": "no relay has a backup parent at the design coverage; re-run with --resilient", **info}
        # cheapest relay to protect: smallest coverage increase, then the largest subtree
        target = min(per_relay, key=lambda r: (per_relay[r], -len(net.subtree(r)), r))
        mult = per_relay[target]
        topo_h = scaled_topology(net, mult, args.load, slot_us)
        net_h = Net(topo_h)
        net_h.parent = dict(net.parent)
        restore = True
    info["coverage_multiplier_used"] = mult
    cases = [c for c in healing_sweep(net_h)["cases"] if c["all_rehomed"] and c["orphans"]]
    if not cases:
        return {"status": "not_testable", "reason": "no recoverable relay failure", **info}
    cases.sort(key=lambda c: (c["failed_relay"] != target, -len(net_h.subtree(c["failed_relay"])), c["failed_relay"]))
    f = cases[0]["failed_relay"]
    plan_h = {"slot_us": slot_us, "frame": net_h.frame}
    pps0 = {n: round(args.load * len(net_h.slots[n]) * 1e6 / (slot_us * net_h.frame), 2) for n in net_h.slots}
    if restore:
        lab.reconfigure(topo_h, out, args)
    print(f"[healing] killing relay NEM {f} (subtree {sorted(net_h.subtree(f))}); frame {net_h.frame}")
    parents0 = dict(net_h.parent)
    normal = lab.window(parents0, pps0, args.secs, tag="heal_normal")
    down = lab.window(parents0, pps0, args.secs, dead={f}, tag="heal_failed")
    suspects = {n for n, v in down["per_origin"].items() if n != f and v["sent"] and v["pdr"] is not None and v["pdr"] < 0.2}
    suspects.add(f)
    detected = f in sorted(n for n in suspects if parents0.get(n) not in suspects)
    sub = set(net_h.subtree(f))
    link = {n: {p: (0.0 if p in sub else 1.0) for p in net_h.ids if p != n and net_h.in_range(n, p)} for n in net_h.ids if n != net_h.gw}
    mgr = SelfHealingManager(MultiHopRouting(link, gateway=net_h.gw), parents0)
    changes = mgr.recover(f)
    new_parents = dict(parents0)
    new_parents.update(changes)
    tx2, frame2 = schedule_for(net_h, new_parents, drop=(f,))
    lab.apply(full_schedule_xml(tx2, net_h.ids, frame2, slot_us, "10M"), "healed")
    healed_parents = {n: p for n, p in new_parents.items() if n != f}
    pps2 = {n: round(args.load * len(tx2[n]) * 1e6 / (slot_us * frame2), 2) if tx2.get(n) else pps0[n] for n in healed_parents}
    healed = lab.window(healed_parents, pps2, args.secs, tag="heal_recovered")
    live_nodes = [n for n in parents0 if n != f]
    agg = lambda w: round(100.0 * sum(w["per_origin"][n]["received"] for n in live_nodes if n in w["per_origin"]) /
                          max(1, sum(w["per_origin"][n]["sent"] for n in live_nodes if n in w["per_origin"])), 2)
    res = {"status": "measured_emane", "failed_relay": f, "affected_nodes": sorted(sub - {f}),
           "detected_from_delivery": bool(detected), "new_parents": {str(k): v for k, v in changes.items()},
           "frame_before": net_h.frame, "frame_after": frame2,
           "pdr_pct_of_surviving_nodes": {"before_failure": agg(normal), "during_failure": agg(down), "after_recovery": agg(healed)},
           **info,
           "note": "the failure is a stopped relay process; detection uses one measurement window, so recovery time is about one window plus schedule publication"}
    lab.restore(out)
    return res

def base_pps(net, plan):
    return {l["nem"]: float(l["pps"]) for l in plan["links"]}


def live(net, plan, args, lab, out):
    rep = {}
    slot_us, frame0 = plan["slot_us"], int(plan["frame"])
    pps0 = base_pps(net, plan)
    parents0 = dict(net.parent)

    # --- windows: multi-hop baseline + predictive adaptation (walk-forward)
    wins = []
    pred = OnlineMetricPredictor(window=max(4, args.windows))
    errs, naive = [], []
    for w in range(args.windows):
        print(f"[window {w + 1}/{args.windows}] baseline multi-hop traffic")
        res = lab.window(parents0, pps0, args.secs, tag=f"base{w + 1}")
        if w == 0 and res["received"] == 0:
            print("!! zero packets reached the gateway in the first window: the live results would be meaningless. See", out / "logs")
            return {"multi_hop": {"status": "FAILED: zero packets reached the gateway (live stage aborted, nothing below is a measurement)",
                                  "hint": f"read {out}/logs/base1_sink*.log and base1_send*.log"}}
        if w >= 2:   # forecast made from windows 0..w-1, compared with what window w actually did
            for n, v in res["per_origin"].items():
                if v["pdr"] is None or n not in pred.history:
                    continue
                errs.append(abs(pred.predict(n)["pdr"] - v["pdr"]))
                naive.append(abs(pred.history[n][-1][1] - v["pdr"]))
        for n, v in res["per_origin"].items():
            if v["pdr"] is not None:
                pred.observe(n, max(0, v["sent"] - v["received"]), v["pdr"])
        wins.append(res)
    lat = {}
    for res in wins:
        for n, v in res["per_origin"].items():
            if v["latency_ms"] is not None:
                lat.setdefault(round(v["hops"] or 0) + 1, []).append(v["latency_ms"])
    rep["multi_hop"] = {"status": "measured_emane", "routes": {n: net.path(n) for n in sorted(parents0)},
                        "windows": [{"pdr_pct": pct(w["pdr"]), "sent": w["sent"], "received": w["received"]} for w in wins],
                        "pdr_pct_mean_sd": [round(st.mean(100 * w["pdr"] for w in wins), 2),
                                            round(st.stdev(100 * w["pdr"] for w in wins), 2) if len(wins) > 1 else 0.0],
                        "latency_ms_by_path_length": {str(k): round(st.mean(v), 1) for k, v in sorted(lat.items())}}
    rep["predictive"] = {"status": "measured_emane (walk-forward: forecast window k from windows < k)",
                         "windows": args.windows, "forecasts_scored": len(errs),
                         "pdr_forecast_mae": round(st.mean(errs), 5) if errs else None,
                         "persistence_baseline_mae": round(st.mean(naive), 5) if naive else None,
                         "note": "with near-100% PDR both errors are tiny; the forecast is only useful when links degrade"}

    # --- adaptive scheduling under a traffic surge: static schedule vs controller-published schedule
    # Capacity of one slot in packets (10 Mbit/s x slot time / packet size, derated): the plan's baseline probe rate is far below it,
    # so the surge is expressed as a multiple of the surge node's OWN slot capacity.  Override with --pkts-per-slot if you measure it.
    cap_slot = args.pkts_per_slot or max(1, int(0.7 * 10e6 * (slot_us / 1e6) / 8 / 300))
    cap_pps = lambda nslots, frame: nslots * cap_slot * 1e6 / (slot_us * frame)
    pn = PlanNetwork(net.topo)

    def size_slots(surge_pps, quality):
        """Slots sized from offered packets per frame; that depends on the frame length that results, so iterate to a fixed point.
        No fixed point (frame keeps growing) means the surge exceeds what the airtime can carry at this planned utilisation."""
        ctl = AdaptiveTDMA(pn, max_slots_per_radio=max(32, 2 * net.n))
        ft = frame0
        for _ in range(12):
            frame_time = ft * slot_us / 1e6
            for r in ctl.metrics:
                offered = sum(surge_pps[o] for o in net.subtree(r + 1)) * frame_time          # packets per frame
                need = int(math.ceil(offered / cap_slot / args.headroom))                      # slots per frame
                # measured end-to-end PDR is passed as link quality (priority only); using it to inflate demand would double count
                ctl.update_radio(r, queue_packets=max(1, need), pdr=1.0, link_quality=quality.get(r + 1, 1.0))
            rpt = ctl.adapt()
            if int(rpt["frame_slots"]) == ft:
                return rpt, True
            ft = int(rpt["frame_slots"])
            if ft > 3 * frame0:
                break
        return rpt, False

    chosen = None
    for leaf in sorted(parents0, key=lambda n: (len(net.path(n) or []), len(net.slots[n]), n)):     # nearest-to-gateway first
        factor = args.surge
        while factor >= 1.2:
            surge = dict(pps0)
            surge[leaf] = max(pps0[leaf], factor * cap_pps(len(net.slots[leaf]), frame0))
            rpt, converged = size_slots(surge, {})
            if converged:
                chosen = (leaf, factor, surge)
                break
            factor -= 0.2
        if chosen:
            break
    if not chosen:
        rep["adaptive_scheduling"] = {"status": "not_applicable", "reason": "no radio can be surged by 1.2x of its own slot capacity within the airtime at this planned utilisation"}
    else:
        leaf, factor, surge = chosen
        print(f"[adaptive] surge x{factor:.1f} of its slot capacity at NEM {leaf}; static schedule first")
        static = lab.window(parents0, surge, args.secs, tag="surge_static")
        quality = {n: (v["pdr"] if v["pdr"] is not None else 1.0) for n, v in static["per_origin"].items()}
        rpt, converged = size_slots(surge, quality)
        ref_slots, ref_frame = best_schedule(pn.adjacency, {r: max(1, d) for r, d in rpt["demand"].items()})
        frame1 = int(rpt["frame_slots"])
        tx = {r + 1: list(s_) for r, s_ in rpt["slots"].items()}
        xml = full_schedule_xml(tx, net.ids, frame1, slot_us, "10M")
        changed = sorted(n for n in net.slots if sorted(tx.get(n, [])) != sorted(net.slots[n]))
        print(f"[adaptive] controller: {len(changed)} radios changed, frame {frame0}->{frame1}, violations {rpt['violations']}")
        if rpt["violations"]:
            raise SystemExit("adaptive schedule has conflicts; not applying")
        lab.apply(xml, "adaptive")
        adaptive = lab.window(parents0, surge, args.secs, tag="surge_adaptive")
        rep["adaptive_scheduling"] = {
            "status": "measured_emane", "surge_node": leaf, "surge_x_of_own_slot_capacity": round(factor, 2),
            "assumed_packets_per_slot": cap_slot, "surge_pps": round(surge[leaf], 1), "planned_utilisation": args.headroom,
            "slots_before": len(net.slots[leaf]), "slots_after": len(tx.get(leaf, [])),
            "frame_before": frame0, "frame_after": frame1, "frame_best_case_scheduler_same_demand": ref_frame,
            "changed_radios": changed, "conflict_violations": rpt["violations"],
            "surge_node_pdr_pct": {"static": pct(static["per_origin"][leaf]["pdr"]), "adaptive": pct(adaptive["per_origin"][leaf]["pdr"])},
            "network_pdr_pct": {"static": pct(static["pdr"]), "adaptive": pct(adaptive["pdr"])}}
    # restore the optimizer's schedule for the next experiment
    lab.restore(out)

    rep["self_healing_live"] = heal_live(net, plan, args, lab, out)
    return rep


# ----------------------------------------------------------------------------- main
def markdown(rep):
    L = [f"# Evolution 3 full run: {rep['n']} radios, frame {rep['frame']} ({rep['best']})", "", f"Mode: **{rep['mode']}**", ""]
    for k, v in rep["advancements"].items():
        L += [f"## {k}", "", f"Status: {v.get('status')}", "", "```json", json.dumps({a: b for a, b in v.items() if a not in ('status', 'cases')}, indent=1), "```", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["offline", "all"])
    ap.add_argument("opt_json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--plan", help="plan.json from gen_evo3.py (default: <out>/plan.json, created if missing)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-live-radios", type=int, default=30,
                    help="refuse the live EMANE stage above this many radios (one laptop cannot emulate more accurately)")
    ap.add_argument("--resilient", action="store_true",
                    help="if the best-case layout has no backup parents, test self-healing at the smallest coverage increase that gives them")
    ap.add_argument("--secs", type=int, default=12, help="seconds of traffic per window")
    ap.add_argument("--windows", type=int, default=4)
    ap.add_argument("--surge", type=float, default=2.0, help="largest traffic surge to try at the least-served radio (reduced until feasible)")
    ap.add_argument("--pkts-per-slot", type=int, default=0, help="packets one slot can carry (default: estimated from slot time, 10 Mbit/s, 256 B packets)")
    ap.add_argument("--headroom", type=float, default=0.8, help="slot utilisation the controller plans for (1.0 = no spare slots)")
    ap.add_argument("--load", type=float, default=0.5)
    ap.add_argument("--slot-ms", type=float, default=10.0)
    ap.add_argument("--frames", type=int, default=500, help="Monte Carlo frames per fading model")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--tx-w", type=float, default=1.2)
    ap.add_argument("--rx-w", type=float, default=0.9)
    ap.add_argument("--idle-w", type=float, default=0.25)
    ap.add_argument("--sleep-w", type=float, default=0.03)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    topo = json.loads(Path(a.opt_json).read_text())
    net = Net(topo)
    rep = {"n": net.n, "frame": net.frame, "best": topo.get("best"), "inputs": topo.get("inputs"),
           "mode": "dry-run (fake lab, NOT evidence)" if a.dry_run else ("emane" if a.mode == "all" else "offline"),
           "advancements": {}}
    adv = rep["advancements"]
    off = offline(net, a)
    adv["distributed_scheduling"] = off["distributed_scheduling"]
    adv["fading_sinr"] = off["fading_sinr"]
    adv["energy_aware"] = off["energy_aware"]
    adv["clock_sync"] = off["clock_sync"]
    adv["self_healing_algorithm"] = off["self_healing_algorithm"]
    if a.mode == "all" and net.n > a.max_live_radios and not a.dry_run:
        print(f"!! {net.n} radios is above --max-live-radios {a.max_live_radios}: skipping the live EMANE stage (offline results only)")
        rep["mode"] = "offline (too many radios for an accurate single-machine EMANE run)"
        a.mode = "offline"
    if a.mode == "all":
        sys.path.insert(0, str(ROOT / "emane"))
        import gen_evo3
        gen_evo3.main([a.opt_json, "--out", str(out / "cfg"), "--secs", str(a.secs), "--load", str(a.load), "--slot-ms", str(a.slot_ms)])
        plan = json.loads(Path(a.plan or out / "cfg/plan.json").read_text())
        (out / "schedule_good_ref.xml").write_text((out / "cfg/schedule_good.xml").read_text())
        cap_est = a.pkts_per_slot or max(1, int(0.7 * 10e6 * (plan["slot_us"] / 1e6) / 8 / 300))
        lab = FakeLab(net, out, plan["slot_us"], int(plan["frame"]), cap_est) if a.dry_run else Lab(net, out)
        live_rep = live(net, plan, a, lab, out)
        if a.dry_run:
            for v in live_rep.values():
                v["status"] = "DRY-RUN fake lab, not a measurement: " + str(v.get("status"))
        adv.update(live_rep)
    (out / "evo3_full_report.json").write_text(json.dumps(rep, indent=1, default=str))
    (out / "EVO3_FULL_REPORT.md").write_text(markdown(rep))
    print(json.dumps({k: v.get("status") for k, v in adv.items()}, indent=1))
    print("report:", out / "evo3_full_report.json")


if __name__ == "__main__":
    main()
