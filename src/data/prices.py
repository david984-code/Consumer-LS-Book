"""Daily prices and CAPM betas vs SPY for the universe (for beta-neutralization)."""

from __future__ import annotations

import numpy as np
import pandas as pd

import config

from . import cache
from .net import flaky_retry

_NAME = "prices"


@flaky_retry
def _download(tickers: list[str]) -> pd.DataFrame:
    import yfinance as yf

    raw = yf.download(tickers, period="5y", progress=False, auto_adjust=True)
    close = raw["Close"][tickers]
    close.index = pd.to_datetime(close.index)
    return close.dropna(how="all")


def fetch(force: bool = False) -> pd.DataFrame:
    """Daily adjusted close for the universe + SPY + hedge ETFs (last 5 years)."""
    if not force and cache.is_fresh(_NAME):
        return cache.load(_NAME)
    tickers = list(dict.fromkeys([*config.UNIVERSE, "SPY", *config.HEDGE_TICKERS]))
    close = _download(tickers)
    cache.save(_NAME, close)
    return close


def hedge_betas(force: bool = False) -> dict[str, float]:
    """Each name's beta vs the equal-weight consumer ETF it's hedged against
    (staples -> RSPS, the rest -> RSPD), so the hedge strips out sector beta."""
    rets = fetch(force=force).pct_change().dropna()
    out = {}
    for name, (subsector, *_rest) in config.UNIVERSE.items():
        etf = config.hedge_etf(subsector)
        if name in rets and etf in rets:
            bench = rets[etf].to_numpy()
            var = float(bench.var())
            cov = float(np.cov(rets[name].to_numpy(), bench)[0, 1])
            out[name] = round(cov / var, 2) if var else 1.0
    return out


def betas(force: bool = False) -> dict[str, float]:
    """Full-sample CAPM beta of each name vs SPY (daily returns)."""
    rets = fetch(force=force).pct_change().dropna()
    spy = rets["SPY"].to_numpy()
    var = float(spy.var())
    out = {}
    for name in config.UNIVERSE:
        if name in rets:
            cov = float(np.cov(rets[name].to_numpy(), spy)[0, 1])
            out[name] = round(cov / var, 2) if var else 1.0
    return out


if __name__ == "__main__":
    print(betas(force=True))
