#!/usr/bin/env python3
"""Regenerate every figure in docs/EVO3_REPORT.md from a results/evo3-full-* run folder.
Usage: python3 scripts/make_evo3_figures.py results/evo3-full-20261111-082053 docs/img
Only measured/computed values from the run's own files are plotted; nothing is typed in by hand."""
import json, re, sys, pathlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

run = pathlib.Path(sys.argv[1]); out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
rep = json.load(open(run / "evo3_full_report.json"))
adv = rep["advancements"]
plan = json.load(open(run / "cfg" / "plan.json"))
lay = json.load(open(run / "opt_resilient.json"))["layout"]
pos = {r["radio"] + 1: (r["x_m"], r["y_m"]) for r in lay}          # NEM id = radio + 1
links = {l["nem"]: l for l in plan["links"]}
FS = plan["frame"]
plt.rcParams.update({"figure.dpi": 150, "font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
C = {"ok": "#2a7f62", "bad": "#c0392b", "blue": "#2b6cb0", "grey": "#8a8f98"}

def hops(n):
    h = 0
    while n != 1:
        n = links[n]["parent"]; h += 1
    return h

# 1. topology -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(6.4, 5.2))
col = {1: "#222", 2: C["bad"], 3: C["bad"], 5: "#d98c00", 3.5: C["blue"]}
for n, l in links.items():
    (x1, y1), (x2, y2) = pos[n], pos[l["parent"]]
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="->", color=C["grey"], lw=1.2))
for n, (x, y) in pos.items():
    c = "#222" if n == 1 else C["blue"]
    if n in (2, 3): c = C["bad"]
    ax.scatter(x, y, s=260, color=c, zorder=3)
    ax.text(x, y, str(n), color="white", ha="center", va="center", fontsize=8, zorder=4, weight="bold")
ax.scatter([], [], color="#222", s=60, label="gateway (NEM 1, receive only)")
ax.scatter([], [], color=C["blue"], s=60, label="radio (NEM id shown)")
ax.scatter([], [], color=C["bad"], s=60, label="pair used for forced-collision test (NEM 2, 3)")
ax.set_aspect("equal"); ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)")
ax.set_title("12-radio layout chosen by the optimizer (arrows point to parent)")
ax.legend(loc="upper left", fontsize=7, frameon=False)
fig.tight_layout(); fig.savefig(out / "01_topology.png"); plt.close(fig)

# 2. slot timeline --------------------------------------------------------
fig, ax = plt.subplots(figsize=(6.8, 3.6))
for n, l in sorted(links.items()):
    for s in l["slots"]:
        ax.barh(n, 1, left=s, color=C["blue"] if n not in (2, 3) else C["bad"], edgecolor="white")
ax.set_xlim(0, FS); ax.set_xticks(range(FS)); ax.set_yticks(sorted(links)); ax.invert_yaxis()
ax.set_xlabel(f"slot in frame (frame = {FS} slots x 10 ms)"); ax.set_ylabel("transmitting radio (NEM)")
ax.set_title("Optimized TDMA schedule: one row per radio, filled = may transmit")
fig.tight_layout(); fig.savefig(out / "02_schedule.png"); plt.close(fig)

# 3. delivery summary -----------------------------------------------------
def total(fn):
    got = sent = 0
    for line in open(run / "baseline-evidence" / fn):
        m = re.match(r"\s*(\d+)\s+(\d+)\s+\[.*?\]\s+[\d.]+\s+(\d+)\s+(\d+)\s", line)
        if m: got += int(m.group(3)); sent += int(m.group(4))
    return 100.0 * got / sent
good, bad, again = total("good_delivery.txt"), total("bad_delivery.txt"), total("good_again_delivery.txt")
mh = adv["multi_hop"]["pdr_pct_mean_sd"][0]
ad = adv["adaptive_scheduling"]; hl = adv["self_healing_live"]
fig, axs = plt.subplots(1, 3, figsize=(9.4, 3.4), sharey=True)
def bars(ax, labels, vals, cols, title):
    b = ax.bar(labels, vals, color=cols)
    for r, v in zip(b, vals): ax.text(r.get_x() + r.get_width() / 2, v + 1, f"{v:.1f}%", ha="center", fontsize=8)
    ax.set_title(title, fontsize=9); ax.set_ylim(0, 112)
bars(axs[0], ["optimized", "forced\ncollision", "optimized\nrestored"], [good, bad, again], [C["ok"], C["bad"], C["ok"]], "Slot collision test")
bars(axs[1], ["static", "adaptive"], [ad["surge_node_pdr_pct"]["static"], ad["surge_node_pdr_pct"]["adaptive"]], [C["bad"], C["ok"]], "Surged radio (2x its slot capacity)")
hp = hl["pdr_pct_of_surviving_nodes"]
bars(axs[2], ["before", "relay\nfailed", "after\nrecovery"], [hp["before_failure"], hp["during_failure"], hp["after_recovery"]], [C["ok"], C["bad"], C["ok"]], "Relay failure (NEM 5)")
axs[0].set_ylabel("packet delivery (%)")
fig.suptitle("Live EMANE results, 12 radios (one run; ranges over 4 runs in EVO3_REPEATS.md)", fontsize=10)
fig.tight_layout(); fig.savefig(out / "03_delivery.png"); plt.close(fig)

# 4. latency by hops ------------------------------------------------------
lat = adv["multi_hop"]["latency_ms_by_path_length"]
fig, ax = plt.subplots(figsize=(5.2, 3.2))
ks = sorted(lat, key=int); ax.plot([int(k) for k in ks], [lat[k] for k in ks], marker="o", color=C["blue"])
for k in ks: ax.annotate(f"{lat[k]:.0f} ms", (int(k), lat[k]), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=8)
ax.set_xticks([int(k) for k in ks]); ax.set_xlabel("hops to gateway"); ax.set_ylabel("mean latency (ms)")
ax.set_title(f"Latency grows with hops (mean delivery {mh:.2f}%)")
fig.tight_layout(); fig.savefig(out / "04_latency_hops.png"); plt.close(fig)

# 5. fading (simulation) --------------------------------------------------
pdr = adv["fading_sinr"]["pdr"]["optimizer_schedule"]
fig, ax = plt.subplots(figsize=(5.6, 3.4)); xs = [0, 3, 6, 10, 15]
for kind, c in (("rayleigh", C["bad"]), ("rician", C["blue"])):
    ax.plot(xs, [100 * pdr[f"{kind}+{x}dB"] for x in xs], marker="o", color=c, label=kind)
ax.axhline(100 * pdr["none+0dB"], color=C["ok"], ls="--", label="no fading")
ax.set_xlabel("extra transmit power as fade margin (dB)"); ax.set_ylabel("packet delivery (%)"); ax.set_ylim(40, 105)
ax.set_title("SINR + fading Monte Carlo (simulation, not EMANE)"); ax.legend(frameon=False, fontsize=8)
fig.tight_layout(); fig.savefig(out / "05_fading_sim.png"); plt.close(fig)

print(json.dumps({"good": round(good, 2), "bad": round(bad, 2), "restored": round(again, 2), "multihop": mh}, indent=1))
