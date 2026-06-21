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

    raw = yf.download(tickers, period="3y", progress=False, auto_adjust=True)
    close = raw["Close"][tickers]
    close.index = pd.to_datetime(close.index)
    return close.dropna(how="all")


def fetch(force: bool = False) -> pd.DataFrame:
    """Daily adjusted close for the universe + SPY (last 3 years)."""
    if not force and cache.is_fresh(_NAME):
        return cache.load(_NAME)
    tickers = [*config.UNIVERSE, "SPY"]
    close = _download(tickers)
    cache.save(_NAME, close)
    return close


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
