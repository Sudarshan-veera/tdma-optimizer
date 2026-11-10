"""Radio model: link budget, path loss, shadowing, and reception rules.

Two reception models are supported:
  disk : a link works if d <= Rc; a receiver is jammed by any other transmitter within Ri = ri_factor * Rc.
  sinr : received power uses log-distance path loss + log-normal shadowing; a link works if
         rx power >= sensitivity and SINR >= beta (interference summed over all transmitters).
"""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PHY:
    f_hz: float = 2.4e9        # carrier frequency
    pt_dbm: float = 10.0       # transmit power
    gt_db: float = 0.0         # tx antenna gain
    gr_db: float = 0.0         # rx antenna gain
    sens_dbm: float = -90.0    # receiver sensitivity
    noise_dbm: float = -100.0  # noise floor
    beta_db: float = 8.0       # SINR needed to decode
    n: float = 2.7             # path-loss exponent
    sigma_db: float = 0.0      # log-normal shadowing std-dev (sinr model)
    d0: float = 1.0            # reference distance (m)
    ri_factor: float = 1.5     # interference range / communication range (disk model)


def fspl_db(d, f_hz):
    """Free-space path loss in dB for d in metres, f in Hz."""
    return 20 * np.log10(d) + 20 * np.log10(f_hz) - 147.55


def max_range(p: PHY) -> float:
    """Communication range Rc (m) from the link budget (no shadowing)."""
    budget = p.pt_dbm + p.gt_db + p.gr_db - p.sens_dbm - fspl_db(p.d0, p.f_hz)
    return float(p.d0 * 10 ** (budget / (10 * p.n)))


def phy_for_range(range_m: float, base: PHY = None) -> PHY:
    """A PHY whose link budget gives exactly `range_m` metres (solves for transmit power)."""
    from dataclasses import replace
    base = base or PHY()
    pl = fspl_db(base.d0, base.f_hz) + 10 * base.n * np.log10(range_m / base.d0)
    pt = pl + base.sens_dbm - base.gt_db - base.gr_db
    return replace(base, pt_dbm=float(pt))


class Channel:
    """Pairwise channel between all nodes. Index 0 is the gateway (the "user")."""

    def __init__(
        self,
        pos,
        phy: PHY,
        rng=None,
        model: str = "disk",
        fading: str = "none",
        rician_k: float = 3.0,
        fading_seed: int | None = None,
    ):
        if model not in ("disk", "sinr"):
            raise ValueError("model must be disk or sinr")
        if fading not in ("none", "rayleigh", "rician"):
            raise ValueError("fading must be none, rayleigh or rician")
        if fading != "none" and model != "sinr":
            raise ValueError("fading requires the sinr channel model")
        if rician_k < 0:
            raise ValueError("rician_k cannot be negative")

        self.phy, self.model = phy, model
        self.fading_model = fading
        self.rician_k = float(rician_k)
        self.pos = np.asarray(pos, dtype=float)
        N = len(self.pos)
        self.N = N
        self.D = np.linalg.norm(self.pos[:, None, :] - self.pos[None, :, :], axis=2)
        Dm = np.maximum(self.D, phy.d0)
        pl = fspl_db(phy.d0, phy.f_hz) + 10 * phy.n * np.log10(Dm / phy.d0)
        if phy.sigma_db > 0:
            if rng is None:
                rng = np.random.default_rng(0)
            X = np.triu(rng.normal(0.0, phy.sigma_db, (N, N)), 1)
            pl = pl + X + X.T            # symmetric shadowing
        self.P = phy.pt_dbm + phy.gt_db + phy.gr_db - pl
        np.fill_diagonal(self.P, -np.inf)

        # Block fading: one reciprocal fading sample per link per channel snapshot.
        self.fading_gain = np.ones((N, N), dtype=float)

        if fading != "none":
            fading_rng = np.random.default_rng(fading_seed)

            if fading == "rayleigh":
                raw_gain = fading_rng.exponential(1.0, size=(N, N))
            else:
                k = self.rician_k
                sigma = np.sqrt(1.0 / (2.0 * (k + 1.0)))
                mean = np.sqrt(k / (k + 1.0))
                real = fading_rng.normal(mean, sigma, size=(N, N))
                imag = fading_rng.normal(0.0, sigma, size=(N, N))
                raw_gain = real * real + imag * imag

            upper = np.triu(raw_gain, 1)
            self.fading_gain = upper + upper.T
            np.fill_diagonal(self.fading_gain, 1.0)

        self.P_effective = self.P.copy()

        if fading != "none":
            safe_gain = np.maximum(self.fading_gain, np.finfo(float).tiny)
            self.P_effective += 10.0 * np.log10(safe_gain)

        np.fill_diagonal(self.P_effective, -np.inf)

        self.lin = np.where(
            np.isfinite(self.P_effective),
            10 ** (self.P_effective / 10),
            0.0,
        )
        self.noise_lin = 10 ** (phy.noise_dbm / 10)
        self.Rc = max_range(phy)
        self.Ri = phy.ri_factor * self.Rc
        if model == "disk":
            self.comm = (self.D <= self.Rc) & ~np.eye(N, dtype=bool)
        else:
            assert phy.beta_db <= phy.sens_dbm - phy.noise_dbm, "beta too high: no link can ever decode"
            self.comm = (self.P_effective >= phy.sens_dbm)

    # ---- reception rule -------------------------------------------------
    def success(self, tx: int, rx: int, txset) -> bool:
        """Does tx -> rx get through while every node in txset transmits?"""
        if rx in txset:                       # half duplex
            return False
        if self.model == "disk":
            for k in txset:
                if k != tx and self.D[k, rx] <= self.Ri:
                    return False
            return True
        intf = 0.0
        for k in txset:
            if k != tx:
                intf += self.lin[k, rx]
        if self.fading_model != "none":
            if self.P_effective[tx, rx] < self.phy.sens_dbm:
                return False

        sinr_db = self.P_effective[tx, rx] - 10 * np.log10(self.noise_lin + intf)
        return bool(sinr_db >= self.phy.beta_db)

    def link_conflict(self, i: int, pi: int, k: int, pk: int) -> bool:
        """Can links i->pi and k->pk NOT share a slot (pairwise test)?"""
        if len({i, pi, k, pk}) < 4:          # shared endpoint (incl. half duplex)
            return True
        both = {i, k}
        return (not self.success(i, pi, both)) or (not self.success(k, pk, both))
