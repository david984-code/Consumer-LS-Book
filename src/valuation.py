"""Systematic value signal: is each name cheap or expensive vs its OWN history?

Sector-appropriate blend, each z-scored against the name's own ~5y history so
"cheap relative to how it usually trades" -> positive (a long bias):

  * Capital-intensive sectors (airlines, casinos, hotels) -> EV/EBIT.
    EBIT = operating income (universally tagged in XBRL, unlike D&A/EBITDA);
    EV = market cap + total debt - cash, so it accounts for leverage and
    profitability, which plain price-to-sales ignores.
  * Rideshare -> price-to-sales. Earnings/EBIT there swing negative, which
    breaks an EV/EBIT history, so a sales multiple is the robust choice.

Anything that can't build a clean EV/EBIT history falls back to P/S. Free data:
price from yfinance, fundamentals from SEC XBRL.
"""

from __future__ import annotations

import pandas as pd
import requests

import config

from .data import cache
from .data.net import network_retry
from .data.prices import fetch as fetch_prices

_HEADERS = {"User-Agent": "consumer-ls-book research (set SEC_UA)"}

_REV = ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues")
_EBIT = ("OperatingIncomeLoss",)
_CASH = ("CashAndCashEquivalentsAtCarryingValue",)
_DEBT_LT = ("LongTermDebtNoncurrent", "LongTermDebt", "LongTermDebtAndCapitalLeaseObligations")
_DEBT_CUR = ("LongTermDebtCurrent", "DebtCurrent")
_SHARES_INSTANT = ("CommonStockSharesOutstanding",)
_SHARES_FLOW = ("WeightedAverageNumberOfDilutedSharesOutstanding",)

_PS_SECTORS = {"rideshare"}  # sales-multiple sectors; the rest use EV/EBIT


@network_retry
def _units(cik: int, concept: str, unit: str = "USD") -> list[dict]:
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{concept}.json"
    r = requests.get(url, headers=_HEADERS, timeout=30)
    if r.status_code != 200:
        return []
    return r.json().get("units", {}).get(unit, [])


def _toq(s: pd.Series) -> pd.Series:
    return pd.Series(s.to_numpy(), index=pd.PeriodIndex(pd.DatetimeIndex(s.index), freq="Q"))


def _flow_quarterly(cik: int, concepts: tuple[str, ...], unit: str = "USD") -> pd.Series:
    """Complete quarterly FLOW series (revenue, EBIT, ...). Q4 isn't filed
    standalone (it's in the 10-K), so derive it as annual - 9-month-YTD."""
    qtr: dict = {}
    ytd9: dict = {}
    annual: dict = {}
    for concept in concepts:
        for u in _units(cik, concept, unit):
            if "start" not in u or "end" not in u:
                continue
            end = pd.Timestamp(u["end"])
            days = (end - pd.Timestamp(u["start"])).days
            val = float(u["val"])
            if 80 <= days <= 100:
                qtr.setdefault(end, val)
            elif 260 <= days <= 285:
                ytd9.setdefault(end, val)
            elif 350 <= days <= 380:
                annual.setdefault(end, val)
    for end, val in annual.items():
        sep = pd.Timestamp(end.year, 9, 30)
        if end.month == 12 and end not in qtr and sep in ytd9:
            qtr[end] = val - ytd9[sep]
    if not qtr:
        return pd.Series(dtype=float)
    return pd.Series(qtr).sort_index().resample("QE").last()


def _instant_quarterly(cik: int, concepts: tuple[str, ...], unit: str = "USD") -> pd.Series:
    """Quarterly INSTANT series (balance-sheet items: cash, debt, shares).
    Carry the last reported value forward to each quarter end."""
    vals: dict = {}
    for concept in concepts:
        for u in _units(cik, concept, unit):
            if "start" in u or "end" not in u:
                continue
            vals.setdefault(pd.Timestamp(u["end"]), float(u["val"]))
    if not vals:
        return pd.Series(dtype=float)
    return pd.Series(vals).sort_index().resample("QE").last().ffill()


def _quarterly_revenue(cik: int) -> pd.Series:
    """Back-compat shim (used by backtest): complete quarterly revenue."""
    return _flow_quarterly(cik, _REV)


def _zscore(ratio: pd.Series, min_obs: int = 8) -> float | None:
    ratio = ratio.dropna()
    if len(ratio) < min_obs:
        return None
    return round(-float((ratio.iloc[-1] - ratio.mean()) / ratio.std(ddof=1)), 2)


def _ps_score(cik: int, px: pd.Series) -> float | None:
    ttm = _toq(_flow_quarterly(cik, _REV).rolling(4).sum().dropna())
    return _zscore((px / ttm).dropna())


def _ev_ebit_score(cik: int, px: pd.Series) -> float | None:
    ebit = _toq(_flow_quarterly(cik, _EBIT).rolling(4).sum())  # TTM EBIT
    shares = _instant_quarterly(cik, _SHARES_INSTANT, "shares")
    if len(shares) < 8:
        shares = _flow_quarterly(cik, _SHARES_FLOW, "shares")  # weighted-avg proxy
    if shares.empty or ebit.empty:
        return None
    shares = _toq(shares)
    debt_lt = _toq(_instant_quarterly(cik, _DEBT_LT))
    debt_cur = _toq(_instant_quarterly(cik, _DEBT_CUR))
    cash = _toq(_instant_quarterly(cik, _CASH))
    mktcap = (px * shares).dropna()
    debt = debt_lt.add(debt_cur, fill_value=0.0)
    ev = mktcap.add(debt.reindex(mktcap.index).fillna(0.0), fill_value=0.0)
    ev = ev.sub(cash.reindex(mktcap.index).fillna(0.0), fill_value=0.0)
    ratio = (ev / ebit)[ebit > 0]  # EV/EBIT only meaningful when EBIT > 0
    return _zscore(ratio)


def value_detail(force: bool = False) -> dict[str, tuple[float, str]]:
    """{name: (score, metric_used)}. Positive score = cheap vs its own history."""
    px_all = fetch_prices(force=force).resample("QE").last()
    px_all.index = pd.PeriodIndex(pd.DatetimeIndex(px_all.index).tz_localize(None), freq="Q")
    out: dict[str, tuple[float, str]] = {}
    for name, cik in config.CIK.items():
        if name not in px_all:
            continue
        px = px_all[name]
        sector = config.UNIVERSE[name][0]
        score, metric = None, "P/S"
        if sector not in _PS_SECTORS:
            score = _ev_ebit_score(cik, px)
            metric = "EV/EBIT"
        if score is None:
            score, metric = _ps_score(cik, px), "P/S"
        if score is not None:
            out[name] = (score, metric)
    return out


def value_scores(force: bool = False) -> dict[str, float]:
    """{name: value_score} -- the float the book consumes."""
    return {k: v[0] for k, v in value_detail(force=force).items()}


def cached_scores(force: bool = False) -> dict[str, float]:
    """value_scores() with a 24h CSV cache (XBRL is slow)."""
    if not force and cache.is_fresh("value_scores"):
        s = cache.load("value_scores")["score"]
        return {str(k): float(v) for k, v in s.items()}
    scores = value_scores(force=force)
    cache.save("value_scores", pd.Series(scores, name="score").to_frame())
    return scores


if __name__ == "__main__":
    for name, (s, metric) in sorted(value_detail(force=True).items(), key=lambda x: -x[1][0]):
        tag = "CHEAP" if s > 0.5 else ("rich" if s < -0.5 else "")
        print(f"  {name:5} {metric:8} value {s:+.2f}  {tag}")
