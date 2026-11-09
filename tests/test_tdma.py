import json, random, subprocess, sys, xml.etree.ElementTree as ET
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tdma_brain as t
import emane_bridge as eb

ROOT = Path(__file__).resolve().parents[1]


def run(coords, **kw):
    return t.solve(coords, **kw)


def test_demo_grid_conflict_free_and_optimal():
    coords = t.demo_coords()
    G, C, slots, lb, proven = run(coords)
    assert t.verify(coords, 500.0, slots) == []
    assert proven and max(slots.values()) + 1 == lb == 9


def test_direct_link_needs_different_slots():
    _, _, s, _, _ = run({"Node_01": (0, 0), "Node_02": (300, 0)})
    assert s["Node_01"] != s["Node_02"]


def test_hidden_terminal_needs_different_slots():
    # A--B--C, A and C are 800 m apart (not neighbours) but both hear B
    c = {"Node_01": (0, 0), "Node_02": (400, 0), "Node_03": (800, 0)}
    _, _, s, _, _ = run(c)
    assert len(set(s.values())) == 3


def test_spatial_reuse_three_hops_apart():
    c = {f"Node_{i+1:02d}": (i * 400.0, 0) for i in range(4)}  # chain of 4
    _, _, s, _, proven = run(c)
    assert max(s.values()) + 1 == 3 and proven
    assert s["Node_01"] == s["Node_04"]            # 3 hops apart -> forced reuse


def test_isolated_nodes_all_share_one_slot():
    c = {f"Node_{i+1:02d}": (i * 5000.0, 0) for i in range(6)}
    _, _, s, _, _ = run(c)
    assert set(s.values()) == {0}


def test_range_boundary_is_inclusive():
    assert t.build_graph({"a": (0, 0), "b": (500, 0)}).has_edge("a", "b")
    assert not t.build_graph({"a": (0, 0), "b": (500.01, 0)}).has_edge("a", "b")


def test_single_node_and_fully_connected():
    assert run({"Node_01": (0, 0)})[2] == {"Node_01": 0}
    c = {f"Node_{i+1:02d}": (i, 0) for i in range(8)}
    _, _, s, _, _ = run(c)
    assert len(set(s.values())) == 8


@pytest.mark.parametrize("seed", range(60))
def test_random_topologies_valid_and_not_worse_than_bound(seed):
    r = random.Random(seed)
    n = r.randint(2, 16)
    c = {f"Node_{i+1:02d}": (r.uniform(0, 1500), r.uniform(0, 1500)) for i in range(n)}
    _, C, s, lb, proven = run(c, restarts=40)
    assert t.verify(c, 500.0, s) == []
    assert max(s.values()) + 1 >= lb


def test_verifier_catches_bad_schedule():
    c = {"Node_01": (0, 0), "Node_02": (400, 0), "Node_03": (800, 0)}
    assert t.verify(c, 500.0, {"Node_01": 0, "Node_02": 1, "Node_03": 0})  # hidden terminal
    assert t.verify(c, 500.0, {"Node_01": 0, "Node_02": 0, "Node_03": 1})  # direct link


@pytest.mark.parametrize("bad", ["not json", "[]", "{}", '{"a": [1]}', '{"a": ["x", 2]}', '{"a": [NaN, 1]}'])
def test_bad_input_rejected(bad):
    with pytest.raises(t.InputError):
        t.parse_coords(bad)


def test_cli_end_to_end(tmp_path):
    out = tmp_path / "s.json"
    proc = subprocess.run([sys.executable, str(ROOT / "tdma_brain.py"), "--json-out", str(out)],
                          capture_output=True, text=True)
    assert proc.returncode == 0
    assert "Schedule verified conflict-free" in proc.stdout
    assert json.loads(out.read_text())["frame_length"] == 9
    bad = subprocess.run([sys.executable, str(ROOT / "tdma_brain.py"), "oops"], capture_output=True, text=True)
    assert bad.returncode == 2


def test_bridge_xml_matches_schedule(tmp_path):
    coords = t.demo_coords()
    _, _, s, _, _ = run(coords)
    data = {"frame_length": max(s.values()) + 1, "range": 500.0, "coords": coords, "slots": s}
    root = ET.fromstring(eb.make_schedule_xml(data))
    assert int(root.find("structure").get("slots")) == data["frame_length"]
    assert root.find("structure").get("slotduration") == "1000"
    tx = {}
    for slot in root.iter("slot"):
        for nem in slot.get("nodes").split(","):
            tx[int(nem)] = int(slot.get("index"))
    assert tx == {eb.nem_id(n): v for n, v in s.items()}       # every node transmits exactly once
    eel = eb.make_eel(data).splitlines()
    assert len(eel) == 16
    assert all(len(l.split()) == 3 + 15 for l in eel)


def test_emane_config_set(tmp_path):
    import glob
    import json
    import subprocess
    import sys
    coords = t.demo_coords()
    _, _, s, _, _ = run(coords)
    sj = tmp_path / "s.json"
    sj.write_text(json.dumps({"frame_length": max(s.values()) + 1, "range": 500.0,
                              "coords": coords, "slots": s}))
    r = subprocess.run([sys.executable, "emane/gen_configs.py", str(sj), "--out", str(tmp_path / "o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    files = glob.glob(str(tmp_path / "o" / "*.xml"))
    assert len(files) == 16 * 3 + 5          # platform/nem/transport per NEM + 5 shared files
    for f in files:
        ET.parse(f)                           # well-formed
    good = (tmp_path / "o" / "schedule_good.xml").read_text()
    bad = (tmp_path / "o" / "schedule_bad.xml").read_text()
    assert good != bad and "nodes='1,3," in bad.replace("4,13,16", "")  # 03 moved into 01's slot
