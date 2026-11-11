"""evo3_full: generic-n checks on small hand-made topologies (no EMANE needed)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "emane"))

import evo3_full as ef  # noqa: E402
from tdmaopt.hetero import optimize  # noqa: E402
import numpy as np  # noqa: E402


def topo(n, cov):
    ranked, _, _, _ = optimize(np.array([float(cov)] * n), 0.5, 0.9, 1.5, "balanced", steps=0, starts_n=1, K=5, seed=1)
    name, top = ranked[0]
    from tdmaopt.hetero import layout_rows
    rows = layout_rows(top, np.array([float(cov)] * n))
    return {"best": name, "frame": top["ev"]["F"], "layout": rows}


@pytest.mark.parametrize("n,cov", [(4, 200), (6, 300), (9, 250)])
def test_offline_is_generic(n, cov):
    net = ef.Net(topo(n, cov))
    assert net.n == n and len(net.parent) == n - 1
    d = ef.distributed_scheduling(net)
    assert d["conflict_violations"] == 0
    safe, frame = ef.sinr_safe_schedule(net)
    assert frame >= 1 and set(safe) == set(net.slots)
    e = ef.energy_study(net, ef.EnergyProfile(1.2, 0.9, 0.25, 0.03))
    assert 0 < e["saving_pct"] < 100
    c = ef.clock_study(net, 1, 10000)
    assert c["offset_after_sync_us"] < c["initial_max_offset_us"] + 10


def test_schedule_after_failure_is_conflict_free():
    net = ef.Net(topo(8, 300))
    relays = sorted({p for p in net.parent.values() if p != net.gw})
    assert relays
    parents = dict(net.parent)
    slots, frame = ef.schedule_for(net, parents)       # raises on conflicts
    assert frame >= 1


def test_dry_run_end_to_end(tmp_path):
    p = tmp_path / "opt.json"
    p.write_text(json.dumps(topo(7, 300)))
    import subprocess
    r = subprocess.run([sys.executable, str(ROOT / "emane/evo3_full.py"), "all", str(p), "--out", str(tmp_path / "o"),
                        "--dry-run", "--resilient", "--frames", "30"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    rep = json.loads((tmp_path / "o/evo3_full_report.json").read_text())
    assert "dry-run" in rep["mode"]
    for k in ("multi_hop", "predictive", "adaptive_scheduling", "self_healing_live", "energy_aware", "clock_sync"):
        assert k in rep["advancements"]


def test_resilience_analysis_is_fast_on_100_radios():
    import time
    ranked, _, _, _ = optimize(np.array([500.0] * 100), 0.5, 0.9, 1.5, "balanced", steps=0, starts_n=1, K=5, seed=1)
    from tdmaopt.hetero import layout_rows
    name, top = ranked[0]
    net = ef.Net({"best": name, "frame": top["ev"]["F"], "layout": layout_rows(top, np.array([500.0] * 100))})
    t = time.time()
    ef.relay_multipliers(net)
    ef.healing_sweep(net)
    assert time.time() - t < 30
