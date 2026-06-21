"""Honest walk-forward test: do the SYSTEMATIC signals actually pay as L/S tilts?

For each signal (demand, value) we build a point-in-time cross-sectional long/short
portfolio every quarter -- long the names the signal likes, short the ones it
doesn't, dollar-neutral -- and measure the NEXT quarter's return. No look-ahead:
each quarter's signal uses only data available up to that quarter. Then we
block-bootstrap the mean spread for a confidence interval.

This is the check behind the thesis-anchored design. If a signal's spread can't be
distinguished from zero, it belongs as a conviction INPUT to a discretionary book
(which is how the book uses it) -- not as an autopilot.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import config

from . import signals
from .data import sources
from .data.prices import fetch as fetch_prices
from .valuation import _quarterly_revenue


def _quarterly_prices(force: bool = False) -> pd.DataFrame:
    px = fetch_prices(force=force).resample("QE").last()
    px.index = pd.PeriodIndex(pd.DatetimeIndex(px.index).tz_localize(None), freq="Q")
    return px[[c for c in config.UNIVERSE if c in px.columns]]


def _value_panel(px: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time value score per name per quarter (expanding-window z of P/S)."""
    cols = {}
    for name in px.columns:
        cik = config.CIK.get(name)
        if cik is None:
            continue
        ttm = _quarterly_revenue(cik).rolling(4).sum().dropna()
        ttm.index = pd.PeriodIndex(ttm.index, freq="Q")
        ps = (px[name] / ttm).dropna()
        if len(ps) < 12:
            continue
        # expanding z using only history up to each quarter (>=8 obs)
        mean = ps.expanding(8).mean()
        std = ps.expanding(8).std(ddof=1)
        cols[name] = -((ps - mean) / std)  # cheap vs own past -> positive
    return pd.DataFrame(cols)


def _demand_panel(force: bool = False) -> pd.DataFrame:
    """Point-in-time demand conviction per name per quarter (expanding temperature)."""
    nyc = sources.nyc_trips(force=force)
    series = {
        "nyc_uber": nyc["UBER"],
        "nyc_lyft": nyc["LYFT"],
        "tsa": sources.tsa(force=force),
        "macau": sources.macau(force=force),
        "lodging": sources.accommodation(force=force),
    }
    rows: dict = {}
    for key, raw in series.items():
        s = raw.dropna().sort_index()  # keep the datetime index for _temperature
        for i in range(18, len(s) + 1):  # need history for deseasonalize + z
            window = s.iloc[:i]
            t = signals._temperature(window)
            if not t:
                continue
            q = pd.Period(pd.Timestamp(window.index[-1]), freq="Q")
            for name in config.SIGNAL_NAMES.get(key, []):
                trust = config.UNIVERSE[name][2]
                rows.setdefault(q, {})[name] = t["z"] * trust
    return pd.DataFrame(rows).T.sort_index()


def _ls_spread(panel: pd.DataFrame, fwd: pd.DataFrame) -> pd.Series:
    """Dollar-neutral cross-sectional L/S forward return per quarter."""
    out = {}
    for q in panel.index:
        if q not in fwd.index:
            continue
        sig = panel.loc[q].dropna()
        r = fwd.loc[q].reindex(sig.index).dropna()
        sig = sig.reindex(r.index)
        if len(sig) < 3 or sig.std(ddof=0) == 0:
            continue
        w = sig - sig.mean()
        gross = w.abs().sum()
        if gross == 0:
            continue
        out[q] = float((w / gross * r).sum())
    return pd.Series(out).sort_index()


def _bootstrap(spread: pd.Series, block: int = 2, n: int = 5000) -> dict:
    """Block-bootstrap the mean quarterly spread -> 90% CI, p, hit rate (annualized)."""
    x = spread.to_numpy()
    k = len(x)
    if k < 6:
        return {"n": k, "insufficient": True}
    rng = np.random.default_rng(0)
    starts_n = int(np.ceil(k / block))
    means = np.empty(n)
    for b in range(n):
        starts = rng.integers(0, k - block + 1, size=starts_n)
        sample = np.concatenate([x[s : s + block] for s in starts])[:k]
        means[b] = sample.mean()
    lo, hi = np.percentile(means, [5, 95])
    return {
        "n": k,
        "mean_q": float(x.mean()),
        "ann_pct": float(x.mean() * 4 * 100),
        "ci90_ann_pct": (float(lo * 4 * 100), float(hi * 4 * 100)),
        "p_le_zero": float((means <= 0).mean()),
        "hit_rate": float((x > 0).mean()),
        "significant": bool(lo > 0 or hi < 0),
        "insufficient": False,
    }


def run(force: bool = False) -> dict:
    px = _quarterly_prices(force=force)
    fwd = px.pct_change().shift(-1)  # return from quarter t to t+1
    panels = {"demand": _demand_panel(force=force), "value": _value_panel(px)}
    results = {}
    print("WALK-FORWARD L/S SIGNAL TEST  (point-in-time, dollar-neutral, no look-ahead)")
    print("=" * 72)
    for tag, panel in panels.items():
        spread = _ls_spread(panel, fwd)
        res = _bootstrap(spread)
        results[tag] = res
        if res.get("insufficient"):
            print(f"  {tag:7}: only {res['n']} quarters -- too few to infer. (insufficient)")
            continue
        lo, hi = res["ci90_ann_pct"]
        verdict = "REAL EDGE" if res["significant"] else "not distinguishable from 0"
        print(
            f"  {tag:7}: {res['ann_pct']:+5.1f}%/yr  90% CI [{lo:+.1f}%, {hi:+.1f}%]  "
            f"hit {res['hit_rate']:.0%}  n={res['n']}  -> {verdict}"
        )
    print("-" * 72)
    print("  Spread indistinguishable from zero => the signal is a conviction INPUT,")
    print("  not a standalone strategy. That is exactly how the book uses it.")
    return results


if __name__ == "__main__":
    run()
