"""Live free-data signals for each subsector, summed to calendar quarters.

Compact re-use of the four readers' data sources -- only what's needed to read the
*current* demand temperature, not the full reader pipelines.
"""

from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET
from io import StringIO

import pandas as pd
import requests

from . import cache
from .net import network_retry

_UA = {"User-Agent": "Mozilla/5.0 (consumer-ls-book research)"}


def _reindex_q(q: pd.Series | pd.DataFrame) -> None:
    q.index = pd.PeriodIndex(q.index).to_timestamp(how="end").normalize()


def _q_series(s: pd.Series) -> pd.Series:
    """Sum a monthly Series to complete calendar quarters."""
    period = pd.DatetimeIndex(s.index).to_period("Q")
    counts = s.notna().groupby(period).sum()
    q = s.groupby(period).sum(min_count=1)
    q = q[counts == 3]
    _reindex_q(q)
    return q


def _q_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Sum a monthly DataFrame to complete calendar quarters (all columns present)."""
    period = pd.DatetimeIndex(df.index).to_period("Q")
    counts = df.notna().groupby(period).sum()
    q = df.groupby(period).sum(min_count=1)
    q = q[(counts == 3).all(axis=1)]
    _reindex_q(q)
    return q


@network_retry
def _get(url: str, **kw) -> requests.Response:
    r = requests.get(url, headers=_UA, timeout=60, **kw)
    r.raise_for_status()
    return r


def nyc_trips(force: bool = False) -> pd.DataFrame:
    """NYC TLC dispatched trips per quarter, columns UBER / LYFT."""
    if not force and cache.is_fresh("nyc"):
        return cache.load("nyc")
    url = "https://data.cityofnewyork.us/resource/2v9c-2k7f.json"
    params = {
        "$select": "base_name,year,month,sum(total_dispatched_trips) as trips",
        "$where": "upper(base_name) like '%UBER%' OR upper(base_name) like '%LYFT%'",
        "$group": "base_name,year,month",
        "$limit": 50000,
    }
    raw = pd.DataFrame(_get(url, params=params).json())
    raw["company"] = (
        raw["base_name"]
        .str.upper()
        .map(lambda s: "UBER" if "UBER" in s else ("LYFT" if "LYFT" in s else None))
    )
    raw = raw.dropna(subset=["company"])
    for c in ("year", "month", "trips"):
        raw[c] = pd.to_numeric(raw[c], errors="coerce")
    raw["date"] = pd.to_datetime(dict(year=raw.year, month=raw.month, day=1))
    monthly = raw.groupby(["date", "company"])["trips"].sum().unstack("company")
    q = _q_frame(monthly)
    cache.save("nyc", q)
    return q


def tsa(force: bool = False) -> pd.Series:
    """TSA throughput per quarter."""
    if not force and cache.is_fresh("tsa"):
        return cache.load("tsa")["pax"]
    base = "https://www.tsa.gov/travel/passenger-volumes"
    cur = dt.date.today().year
    frames = []
    for y in range(2019, cur + 1):
        try:
            t = pd.read_html(StringIO(_get(base if y == cur else f"{base}/{y}").text))[0]
            t.columns = ["date", "pax"]
            t["date"] = pd.to_datetime(t["date"])
            frames.append(t.assign(pax=pd.to_numeric(t["pax"], errors="coerce")).dropna())
        except Exception as exc:  # noqa: BLE001
            print(f"[tsa] {y}: {exc}")
    daily = pd.concat(frames).drop_duplicates("date").set_index("date")["pax"]
    q = _q_series(daily.resample("MS").sum())
    cache.save("tsa", q.to_frame("pax"))
    return q


def macau(force: bool = False) -> pd.Series:
    """Macau monthly Gross Gaming Revenue per quarter (MOP million)."""
    if not force and cache.is_fresh("macau"):
        return cache.load("macau")["ggr"]
    months = {
        m: i
        for i, m in enumerate(
            [
                "Jan",
                "Feb",
                "Mar",
                "Apr",
                "May",
                "Jun",
                "Jul",
                "Aug",
                "Sep",
                "Oct",
                "Nov",
                "Dec",
            ],
            start=1,
        )
    }
    data = {}
    for y in range(2010, dt.date.today().year + 1):
        u = f"https://www.dicj.gov.mo/web/en/information/DadosEstat_mensal/{y}/report_en.xml"
        r = requests.get(u, headers=_UA, timeout=30)
        if r.status_code != 200:
            continue
        for rec in ET.fromstring(r.content).iter("RECORD"):
            d = [x.text for x in rec.findall("DATA")]
            if len(d) >= 2 and d[0] in months and d[1]:
                try:
                    data[pd.Timestamp(y, months[d[0]], 1)] = float(d[1].replace(",", ""))
                except ValueError:
                    continue
    q = _q_series(pd.Series(data).sort_index())
    cache.save("macau", q.to_frame("ggr"))
    return q


def accommodation(force: bool = False) -> pd.Series:
    """US accommodation-sector employment per quarter (FRED CES7072100001).

    A hotel-specific demand proxy (hotels staff to occupancy). Provisional -- the
    franchisors' real metric is RevPAR, which the dedicated lodging reader handles.
    """
    if not force and cache.is_fresh("accom"):
        return cache.load("accom")["jobs"]
    text = _get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=CES7072100001").text
    df = pd.read_csv(StringIO(text))
    df.columns = ["date", "jobs"]
    df["date"] = pd.to_datetime(df["date"])
    df["jobs"] = pd.to_numeric(df["jobs"], errors="coerce")
    q = _q_series(df.dropna().set_index("date")["jobs"])
    cache.save("accom", q.to_frame("jobs"))
    return q
