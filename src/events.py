"""Events calendar for the book -- the known one-day movers to size around.

For every name you hold, the next earnings date (the biggest scheduled catalyst),
sorted soonest-first and flagged if it's within two weeks. Earnings from yfinance;
investor days / conferences have no clean free feed, so check those manually.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

import config


def _next_earnings(tk) -> dt.date | None:
    try:
        cal = tk.calendar
        ed = cal.get("Earnings Date") if isinstance(cal, dict) else None
        d = (ed[0] if isinstance(ed, list) and ed else ed) if ed else None
        return pd.Timestamp(d).date() if d is not None else None
    except Exception:  # noqa: BLE001
        return None


def calendar() -> list[dict]:
    import yfinance as yf

    today = dt.date.today()
    rows = []
    for name, thesis in config.THESES.items():
        if not thesis:
            continue
        d = _next_earnings(yf.Ticker(name))
        days = (d - today).days if d else None
        rows.append(
            {"name": name, "side": "long" if thesis > 0 else "short", "date": d, "days": days}
        )
    rows.sort(key=lambda r: (r["date"] is None, r["date"] or dt.date.max))
    return rows


def print_calendar() -> None:
    print("BOOK EVENTS CALENDAR  (earnings = the scheduled one-day movers)")
    print("=" * 64)
    for r in calendar():
        d = r["date"]
        when = f"{d}  ({r['days']:+d}d)" if d and r["days"] is not None else "not announced"
        flag = (
            "  <-- within 2 weeks, size around it"
            if r["days"] is not None and 0 <= r["days"] <= 14
            else ""
        )
        past = (
            "  (last report; next not yet set)" if r["days"] is not None and r["days"] < 0 else ""
        )
        print(f"  {r['name']:5} {r['side']:5}  earnings {when}{flag}{past}")
    print("-" * 64)
    print("  Conferences / investor days / analyst days: check manually -- no clean")
    print("  free feed. Earnings dates flip to 'last report' until the next is set.")


if __name__ == "__main__":
    print_calendar()
