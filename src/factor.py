"""Factor-exposure report -- is the book actually idiosyncratic?

The RSPD/RSPS hedge neutralizes consumer-SECTOR beta, but a name can still carry
factor risk the hedge doesn't catch -- e.g. NCLH (cruise) moves with OIL, which no
consumer ETF offsets. This regresses the whole book's daily returns (longs + single
short + the sector hedges) on factor proxies and shows the residual exposures, plus
which name drives each, so you can see the unhedged bets and decide whether to cover
them. Free data (yfinance).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .book import _hedge_weight, positions
from .data.prices import fetch as fetch_prices

_FACTORS = {
    "SPY": "market",
    "USO": "oil",
    "TLT": "rates (long bond)",
    "IWM": "small-cap",
}


def _net_weights(pos: pd.DataFrame) -> dict[str, float]:
    """Full book weights: single names + the sector-hedge shorts."""
    w: dict[str, float] = {str(r["name"]): float(r["weight"]) for _, r in pos.iterrows()}
    for etf, sleeve in pos.groupby("hedge"):
        w[str(etf)] = w.get(str(etf), 0.0) + _hedge_weight(sleeve["weight"], sleeve["beta"])
    return w


def _beta(y: np.ndarray, x: np.ndarray) -> float:
    xc = x - x.mean()
    denom = float((xc * xc).sum())
    return float(((y - y.mean()) * xc).sum() / denom) if denom else 0.0


def exposures(force: bool = False) -> dict:
    import yfinance as yf

    pos = positions(force=force)
    if pos.empty:
        return {}
    w = _net_weights(pos)
    bret = fetch_prices().pct_change()  # already includes SPY (+ universe + hedges)
    extra = [f for f in _FACTORS if f not in bret.columns]
    fac = yf.download(extra, period="1y", progress=False, auto_adjust=True)["Close"]
    df = pd.concat([bret, fac.pct_change()], axis=1).dropna()
    book = np.asarray(sum(df[k] * w[k] for k in w if k in df.columns))
    spy = df["SPY"].to_numpy()

    # Raw market beta, then NEUTRALIZE market and measure the residual exposures
    # (avoids the SPY/IWM/oil collinearity that makes a joint regression unstable).
    mbeta = _beta(book, spy)
    resid = book - mbeta * spy
    factor_beta = {"SPY": round(mbeta, 2)}
    for f in ("USO", "TLT", "IWM"):
        factor_beta[f] = round(_beta(resid, df[f].to_numpy()), 2)

    # per-name oil contribution: each name's market-neutral oil beta x its weight
    oil = df["USO"].to_numpy()
    oil_contrib = {}
    for _, r in pos.iterrows():
        n = str(r["name"])
        if n in df.columns:
            nm = df[n].to_numpy()
            nr = nm - _beta(nm, spy) * spy
            oil_contrib[n] = round(_beta(nr, oil) * float(r["weight"]), 3)
    return {"factor_beta": factor_beta, "oil_contrib": oil_contrib}


def print_report(force: bool = False) -> None:
    e = exposures(force=force)
    print("BOOK FACTOR EXPOSURES  (residual, after the consumer-sector hedge)")
    print("=" * 64)
    if not e:
        print("  No positions.")
        return
    for f, label in _FACTORS.items():
        b = e["factor_beta"][f]
        thr = 0.15 if f == "SPY" else 0.10
        flag = ""
        if abs(b) >= thr:
            flag = "  <-- residual market" if f == "SPY" else "  <-- unhedged factor bet"
        print(f"  {label:18}({f})  beta {b:+.2f}{flag}")
    print("-" * 64)
    oil_b = e["factor_beta"]["USO"]
    top = sorted(e["oil_contrib"].items(), key=lambda kv: -abs(kv[1]))[:3]
    drivers = ", ".join(f"{n} {c:+.2f}" for n, c in top)
    hurt = (
        "an oil SPIKE hurts you"
        if oil_b < 0
        else ("an oil DROP hurts you" if oil_b > 0 else "~neutral")
    )
    print(f"  net oil beta {oil_b:+.2f} -> {hurt}; mostly from {drivers}")
    print("  These are bets the consumer hedge does NOT cover. Cover with a paired")
    print("  short (e.g. another cruise name) / an oil hedge, or just size for them.")


if __name__ == "__main__":
    print_report(force=True)
