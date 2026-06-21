"""Pre-trade short-safety scanner.

Being right on valuation isn't enough on the short side -- you get hurt by a
crowded short (squeeze), an imminent catalyst (earnings/investor day/M&A), or
simply shorting into strong upward momentum. For each name you're thinking of
shorting, this pulls those risks so you can decide whether the timing is sane.

Informational only -- it flags risk, it does not size anything. Free data
(yfinance: short interest, earnings date, headlines; prices for momentum).
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

import config

from .data.prices import fetch as fetch_prices


def _momentum(close: pd.Series) -> dict:
    c = close.dropna()
    last = float(c.iloc[-1])
    r6 = last / float(c.iloc[-126]) - 1 if len(c) > 126 else float("nan")
    r12 = last / float(c.iloc[-252]) - 1 if len(c) > 252 else float("nan")
    dma200 = float(c.tail(200).mean()) if len(c) >= 200 else float("nan")
    vol = float(c.pct_change().tail(63).std() * (252**0.5))
    return {"last": last, "r6": r6, "r12": r12, "above_200dma": last > dma200, "vol": vol}


def _short_interest(info: dict) -> tuple[float | None, float | None]:
    sp = info.get("shortPercentOfFloat")
    return (float(sp) if sp is not None else None, info.get("shortRatio"))  # %, days-to-cover


def _next_earnings(tk) -> dt.date | None:
    try:
        cal = tk.calendar
        ed = cal.get("Earnings Date") if isinstance(cal, dict) else None
        d = (ed[0] if isinstance(ed, list) and ed else ed) if ed is not None else None
        return d if isinstance(d, dt.date) else (pd.Timestamp(d).date() if d is not None else None)
    except Exception:  # noqa: BLE001
        return None


def _flags(
    short_pct: float | None, dtc: float | None, days_to_earn: int | None, m: dict
) -> list[str]:
    out = []
    if (short_pct is not None and short_pct > 0.15) or (dtc is not None and dtc > 5):
        out.append("SQUEEZE-RISK (crowded short)")
    if days_to_earn is not None and 0 <= days_to_earn <= 21:
        out.append(f"EVENT-RISK (earnings in {days_to_earn}d)")
    if m.get("above_200dma") and (m.get("r6") or 0) > 0.10:
        out.append("MOMENTUM-RISK (shorting into strength)")
    return out


def scan(tickers: list[str], force: bool = False) -> None:
    px = fetch_prices(force=force)
    today = dt.date.today()
    print("SHORT-SAFETY SCAN  (informational -- timing/risk check, not sizing)")
    print("=" * 72)
    for t in tickers:
        m = _momentum(px[t]) if t in px.columns else {}
        info: dict = {}
        tk = None
        try:
            import yfinance as yf

            tk = yf.Ticker(t)
            info = tk.info or {}
        except Exception:  # noqa: BLE001
            pass
        short_pct, dtc = _short_interest(info)
        earn = _next_earnings(tk) if tk is not None else None
        days_to_earn = (earn - today).days if earn else None
        news = []
        try:
            items = tk.news if tk is not None else []
            news = [n.get("title") or n.get("content", {}).get("title", "") for n in (items or [])]
        except Exception:  # noqa: BLE001
            pass
        flags = _flags(short_pct, dtc, days_to_earn, m)

        print(f"\n  {t}  ({config.UNIVERSE.get(t, ('?',))[0]})")
        si = f"{short_pct:.0%}" if short_pct is not None else "n/a"
        dt_c = f"{dtc:.1f}d" if dtc is not None else "n/a"
        print(f"    short interest {si} of float | days-to-cover {dt_c}")
        if m:
            print(
                f"    momentum: 6m {m['r6']:+.0%}, 12m {m['r12']:+.0%}, "
                f"{'ABOVE' if m['above_200dma'] else 'below'} 200dma | ann.vol {m['vol']:.0%}"
            )
        print(
            f"    next earnings: {earn if earn else 'n/a'}"
            f"{f' ({days_to_earn}d)' if days_to_earn is not None else ''}"
        )
        for h in [x for x in news[:4] if x]:
            clean = h.encode("ascii", "ignore").decode()[:78]  # Windows console is cp1252
            print(f"      news: {clean}")
        print(f"    >> {'  '.join(flags) if flags else 'no major short-side flags'}")
    print("\n  M&A / investor-day / conference checks: confirm manually -- no clean")
    print("  free feed. The headlines above are a first scan for anything brewing.")


def _book_shorts() -> list[str]:
    return [n for n, v in config.THESES.items() if v < 0]


if __name__ == "__main__":
    import sys

    names = sys.argv[1:] or _book_shorts()
    if not names:
        print("No short theses set. Pass tickers, e.g. python -m src.shorts MAR HLT")
    else:
        scan(names)
