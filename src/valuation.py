"""Systematic value signal: is each name cheap or expensive vs its own history?

value_score = -z( price / trailing-12m revenue ).  We z-score price-to-sales over
the name's own ~3-year history, so 'cheap relative to how it usually trades' ->
positive score (a long bias), 'expensive' -> negative. (Share count is treated as
roughly constant over the window, which cancels in the z-score.) Free data:
price from yfinance, revenue from SEC XBRL.
"""

from __future__ import annotations

import pandas as pd
import requests

import config

from .data import cache
from .data.net import network_retry
from .data.prices import fetch as fetch_prices

_HEADERS = {"User-Agent": "consumer-ls-book research (set SEC_UA)"}
_CONCEPTS = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax")


@network_retry
def _facts(cik: int) -> list[tuple[pd.Timestamp, int, float]]:
    """All USD revenue facts (end_date, duration_days, value) from both concepts."""
    out = []
    for concept in _CONCEPTS:
        url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{concept}.json"
        r = requests.get(url, headers=_HEADERS, timeout=30)
        if r.status_code != 200:
            continue
        for u in r.json().get("units", {}).get("USD", []):
            if "start" in u and "end" in u:
                end = pd.Timestamp(u["end"])
                days = (end - pd.Timestamp(u["start"])).days
                out.append((end, days, float(u["val"])))
    return out


def _quarterly_revenue(cik: int) -> pd.Series:
    """Complete quarterly revenue. Q4 isn't filed standalone (it's in the 10-K),
    so derive it as annual - 9-month-YTD for calendar-year filers."""
    qtr, ytd9, annual = {}, {}, {}
    for end, days, val in _facts(cik):
        if 80 <= days <= 100:
            qtr[end] = val  # Q1/Q2/Q3 (and any standalone Q4)
        elif 260 <= days <= 285:
            ytd9[end] = val
        elif 350 <= days <= 380:
            annual[end] = val
    for end, val in annual.items():
        sep = pd.Timestamp(end.year, 9, 30)
        if end.month == 12 and end not in qtr and sep in ytd9:
            qtr[end] = val - ytd9[sep]  # derived Q4
    if not qtr:
        return pd.Series(dtype=float)
    return pd.Series(qtr).sort_index().resample("QE").last()


def value_scores(force: bool = False) -> dict[str, float]:
    """{name: value_score}. Positive = cheap vs its own price/sales history."""
    px = fetch_prices(force=force).resample("QE").last()
    px.index = pd.PeriodIndex(pd.DatetimeIndex(px.index).tz_localize(None), freq="Q")
    out: dict[str, float] = {}
    for name, cik in config.CIK.items():
        if name not in px:
            continue
        ttm = _quarterly_revenue(cik).rolling(4).sum().dropna()
        ttm.index = pd.PeriodIndex(ttm.index, freq="Q")
        ps = (px[name] / ttm).dropna()  # aligns on quarterly period
        if len(ps) < 8:
            continue
        z = float((ps.iloc[-1] - ps.mean()) / ps.std(ddof=1))
        out[name] = round(-z, 2)  # cheap (low P/S vs history) -> positive
    return out


def cached_scores(force: bool = False) -> dict[str, float]:
    """value_scores() with a 24h CSV cache (XBRL is slow)."""
    if not force and cache.is_fresh("value_scores"):
        s = cache.load("value_scores")["score"]
        return {str(k): float(v) for k, v in s.items()}
    scores = value_scores(force=force)
    cache.save("value_scores", pd.Series(scores, name="score").to_frame())
    return scores


if __name__ == "__main__":
    for name, s in sorted(cached_scores(force=True).items(), key=lambda x: -x[1]):
        tag = "CHEAP" if s > 0.5 else ("rich" if s < -0.5 else "")
        print(f"  {name:5} value {s:+.2f}  {tag}")
