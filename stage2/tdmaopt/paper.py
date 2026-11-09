"""Reproduces every number, table and figure of paper/main.tex.   python -m tdmaopt.paper [--heavy]"""
import argparse, json, math, os, time
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from . import theory as T
from .phy import PHY, Channel, phy_for_range
from .schedule import best_schedule, greedy_schedule, conflict_graph, subtree_loads
from .topology import build_tree

R = 100.0
OUT = "results/paper"
plt.rcParams.update({"font.size": 8, "font.family": "serif", "axes.grid": True, "grid.alpha": .3, "figure.dpi": 150})


def frames(pos, rho, mu):
    ch = Channel(pos, phy_for_range(mu * R * 1.0001, PHY(ri_factor=rho / mu)), model="disk")
    par, _ = build_tree(ch)
    if (par == -2).any():
        return None
    adj, d = conflict_graph(ch, par), subtree_loads(par)
    hops = np.zeros(len(par), int)
    for v in range(1, len(par)):
        u, h = v, 0
        while u != 0:
            u, h = par[u], h + 1
        hops[v] = h
    return greedy_schedule(adj, d)[1], best_schedule(adj, d)[1], int(hops.max())


def grow(N, rng, mu=0.9, spread=0.5):
    """Random connected layout: each radio is dropped within mu*R of an earlier one (biased to recent ones -> elongated)."""
    pts = [np.zeros(2)]
    for i in range(1, N):
        j = int(len(pts) - 1 - min(len(pts) - 1, rng.geometric(spread) - 1))
        th, r = rng.uniform(0, 2 * math.pi), mu * R * math.sqrt(rng.uniform(0.2, 1.0)) * .9999
        pts.append(pts[j] + r * np.array([math.cos(th), math.sin(th)]))
    return np.array(pts)


def ci95(x):
    x = np.asarray(x, float)
    return float(x.mean()), float(1.96 * x.std(ddof=1) / math.sqrt(len(x))) if len(x) > 1 else 0.0


def exp_theory(rhos=(1.0, 1.25, 1.5, 1.75, 2.0, 2.5), mus=(0.8, 0.9, 1.0), Ns=(6, 10, 20, 40, 80)):
    rows, ok, tot = [], 0, 0
    for rho in rhos:
        for mu in mus:
            for N in Ns:
                pos = np.array([[i * mu * R * .9999, 0.0] for i in range(N)])
                f = frames(pos, rho, mu); th = T.chain_frame(N, rho, mu)
                rows.append(dict(kind="chain", rho=rho, mu=mu, N=N, theory=th, greedy=f[0], best=f[1]))
                ok += f[1] == th; tot += 1
                for D in (0.35, 0.6, 0.85):
                    Dm = D * (N - 1) * mu * R
                    l = math.ceil(Dm / (mu * R) - 1e-9)
                    lb = T.frame_lower_bound(N, Dm, R, mu, rho)
                    arms = T.spider_arms(N, l)
                    if lb is None or not T.arms_conflict_free(mu, rho, len(arms)):
                        continue
                    f = frames(T.spider_positions(arms, mu * R * .9999), rho, mu)
                    rows.append(dict(kind="spider", rho=rho, mu=mu, N=N, theory=lb, greedy=f[0], best=f[1]))
                    ok += f[1] == lb; tot += 1
    return rows, ok, tot


def exp_bound(trials=2000, seed=1):
    rng = np.random.default_rng(seed); viol = 0; tight = 0; n = 0; gaps = []
    for _ in range(trials):
        N = int(rng.integers(8, 41)); rho = float(rng.choice([1.0, 1.5, 2.0])); mu = 0.9
        f = frames(grow(N, rng, mu, rng.choice([.15, .4, .8])), rho, mu)
        if f is None:
            continue
        g = T.reach_hops(rho, mu)
        lb = max(N - 1, T.window(f[2], g)); n += 1
        viol += f[1] < lb; tight += f[1] == lb; gaps.append(f[0] - f[1])
    return dict(n=n, violations=viol, tight=tight, greedy_excess_mean=float(np.mean(gaps)),
                greedy_worse=int(sum(g > 0 for g in gaps)))


def exp_greedy_gap(trials=600, seed=2):
    rng = np.random.default_rng(seed); out = []
    for N in (20, 40, 80):
        gg, bb = [], []
        for _ in range(trials // 3):
            f = frames(grow(N, rng, 0.9, rng.choice([.15, .4, .8])), 1.5, 0.9)
            gg.append(f[0]); bb.append(f[1])
        gm, gc = ci95(gg); bm, bc = ci95(bb)
        out.append(dict(N=N, greedy=gm, greedy_ci=gc, best=bm, best_ci=bc, gain_pct=100 * (gm - bm) / gm))
    return out


def exp_scaling(Ns, rho=1.5, mu=0.9):
    out = []
    for N in Ns:
        l = math.ceil(0.5 * (N - 1)) if N < 40 else math.ceil((N - 1) / 3)
        arms = T.spider_arms(N, l); pos = T.spider_positions(arms, mu * R * .9999)
        t = time.time(); f = frames(pos, rho, mu); dt = time.time() - t
        out.append(dict(N=N, arms=arms, frame=f[1], greedy=f[0], bound=T.frame_lower_bound(N, l * mu * R, R, mu, rho), seconds=dt))
    return out


def fig_frame_vs_D(N=60, rho=1.5, mu=0.9):
    fig, ax = plt.subplots(figsize=(3.4, 2.4))
    Ds, lb, bst, grd = [], [], [], []
    for l in range(math.ceil((N - 1) / 3), N):
        arms = T.spider_arms(N, l)
        if not T.arms_conflict_free(mu, rho, len(arms)):
            continue
        f = frames(T.spider_positions(arms, mu * R * .9999), rho, mu)
        Ds.append(l * mu * R / 1000); lb.append(T.frame_lower_bound(N, l * mu * R, R, mu, rho)); bst.append(f[1]); grd.append(f[0])
    ax.plot(Ds, grd, "s--", ms=2.5, lw=.8, label="greedy colouring")
    ax.plot(Ds, bst, "o-", ms=2.5, lw=1, label="proposed (MCS order)")
    ax.plot(Ds, lb, "k:", lw=1.2, label="Theorem 1 bound")
    ax.set_xlabel("required reach $D$ (km)"); ax.set_ylabel("frame length $F$ (slots)"); ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(f"{OUT}/fig_frame_vs_D.pdf"); plt.close(fig)


def fig_rho(N=40, mu=0.9):
    fig, ax = plt.subplots(figsize=(3.4, 2.4))
    rr = np.linspace(1.0, 3.5, 11)
    ax.plot(rr, [T.chain_frame(N, r, mu) for r in rr], "o-", ms=2.5, lw=1, label="chain, closed form")
    ax.plot(rr, [frames(np.array([[i * mu * R * .9999, 0.0] for i in range(N)]), r, mu)[1] for r in rr], "x", ms=4, label="scheduler")
    ax.set_xlabel(r"interference ratio $\rho$"); ax.set_ylabel("frame length (slots)"); ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(f"{OUT}/fig_rho.pdf"); plt.close(fig)


def fig_gap(rows):
    fig, ax = plt.subplots(figsize=(3.4, 2.4))
    xs = [r["N"] for r in rows]; w = .35; i = np.arange(len(xs))
    ax.bar(i - w / 2, [r["greedy"] for r in rows], w, yerr=[r["greedy_ci"] for r in rows], label="greedy", capsize=2)
    ax.bar(i + w / 2, [r["best"] for r in rows], w, yerr=[r["best_ci"] for r in rows], label="proposed", capsize=2)
    ax.set_xticks(i); ax.set_xticklabels(xs); ax.set_xlabel("radios $N$"); ax.set_ylabel("mean frame (slots)"); ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(f"{OUT}/fig_gap.pdf"); plt.close(fig)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--heavy", action="store_true"); a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    rows, ok, tot = exp_theory()
    bound = exp_bound(); gap = exp_greedy_gap()
    scal = exp_scaling([10, 20, 40, 80, 160] + ([320, 476] if a.heavy else []))
    fig_frame_vs_D(); fig_rho(); fig_gap(gap)
    gw = [r for r in rows if r["greedy"] > r["best"]]
    res = dict(theory_cases=tot, theory_exact=ok, bound=bound, gap=gap, scaling=scal,
               greedy_suboptimal_cases=len(gw), worst_greedy_excess=max((r["greedy"] - r["best"] for r in rows), default=0))
    json.dump(res, open(f"{OUT}/results.json", "w"), indent=1)
    with open(f"{OUT}/numbers.tex", "w") as f:
        for k, v in dict(theoryCases=tot, theoryExact=ok, boundTrials=bound["n"], boundViol=bound["violations"], boundTight=bound["tight"],
                         greedySub=len(gw), worstExcess=res["worst_greedy_excess"]).items():
            f.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")
    with open(f"{OUT}/tab_gap.tex", "w") as f:
        f.write("\\begin{tabular}{rrrr}\\toprule $N$ & greedy & proposed & gain (\\%)\\\\\\midrule\n")
        for r in gap:
            f.write(f"{r['N']} & {r['greedy']:.1f}$\\pm${r['greedy_ci']:.1f} & {r['best']:.1f}$\\pm${r['best_ci']:.1f} & {r['gain_pct']:.1f}\\\\\n")
        f.write("\\bottomrule\\end{tabular}\n")
    with open(f"{OUT}/tab_scaling.tex", "w") as f:
        f.write("\\begin{tabular}{rrrr}\\toprule $N$ & frame & bound & time (s)\\\\\\midrule\n")
        for r in scal:
            f.write(f"{r['N']} & {r['frame']} & {r['bound']} & {r['seconds']:.2f}\\\\\n")
        f.write("\\bottomrule\\end{tabular}\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
