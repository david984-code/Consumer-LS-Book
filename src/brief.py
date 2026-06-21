"""One-page research brief for any consumer name -- a starting scaffold, not a view.

For a ticker you're getting to know, pull the fundamentals in one place: what the
company does, valuation (P/E, EV/EBITDA, P/S), margins, growth, returns, momentum,
short interest, next earnings, and recent headlines. You bring the judgment; this
just saves you the hunt. Free data (yfinance).

    python -m src.brief CELH CAVA MNST
"""

from __future__ import annotations


def _ascii(s: str, n: int = 96) -> str:
    return s.encode("ascii", "ignore").decode().strip()[:n]


def _pct(x: object) -> str:
    return f"{float(x) * 100:+.0f}%" if isinstance(x, (int, float)) else "n/a"


def _mult(x: object) -> str:
    return f"{float(x):.1f}x" if isinstance(x, (int, float)) else "n/a"


def _bil(x: object) -> str:
    return f"${float(x) / 1e9:.1f}B" if isinstance(x, (int, float)) else "n/a"


def brief(ticker: str) -> None:
    import yfinance as yf

    tk = yf.Ticker(ticker)
    info = tk.info or {}
    print(f"\n{'=' * 72}\n{ticker}  {_ascii(info.get('longName', ''), 50)}")
    sector, industry = info.get("sector", "?"), info.get("industry", "?")
    print(f"  {sector} / {industry}  |  mktcap {_bil(info.get('marketCap'))}")
    summary = info.get("longBusinessSummary", "")
    if summary:
        print(f"  {_ascii(summary, 160)}...")

    print("\n  VALUATION")
    print(
        f"    P/E (fwd)   {_mult(info.get('forwardPE')):>8}   "
        f"EV/EBITDA {_mult(info.get('enterpriseToEbitda')):>8}   "
        f"P/S {_mult(info.get('priceToSalesTrailing12Months')):>8}"
    )
    print("\n  QUALITY / GROWTH")
    print(
        f"    gross mgn {_pct(info.get('grossMargins')):>7}   "
        f"op mgn {_pct(info.get('operatingMargins')):>7}   "
        f"ROE {_pct(info.get('returnOnEquity')):>7}"
    )
    print(
        f"    rev growth {_pct(info.get('revenueGrowth')):>6}   "
        f"earnings growth {_pct(info.get('earningsGrowth')):>6}   "
        f"net debt {_bil((info.get('totalDebt') or 0) - (info.get('totalCash') or 0))}"
    )

    # momentum + where price sits in its 52w range
    try:
        c = tk.history(period="1y")["Close"].dropna()
        last = float(c.iloc[-1])
        r6 = last / float(c.iloc[-126]) - 1 if len(c) > 126 else float("nan")
        dma200 = float(c.tail(200).mean()) if len(c) >= 200 else float("nan")
        lo, hi = float(c.min()), float(c.max())
        rng = (last - lo) / (hi - lo) * 100 if hi > lo else float("nan")
        print("\n  PRICE / MOMENTUM")
        print(
            f"    ${last:.2f}   6m {r6:+.0%}   {'ABOVE' if last > dma200 else 'below'} 200dma   "
            f"{rng:.0f}% of 52w range   beta {info.get('beta', 'n/a')}"
        )
    except Exception:  # noqa: BLE001
        pass

    sp = info.get("shortPercentOfFloat")
    print(
        f"\n  SHORT INTEREST  {_pct(sp) if sp is not None else 'n/a'} of float   "
        f"days-to-cover {info.get('shortRatio', 'n/a')}"
    )

    try:
        cal = tk.calendar
        ed = cal.get("Earnings Date") if isinstance(cal, dict) else None
        d = (ed[0] if isinstance(ed, list) and ed else ed) if ed else None
        print(f"  NEXT EARNINGS   {d if d else 'n/a'}")
    except Exception:  # noqa: BLE001
        pass

    try:
        heads = [n.get("title") or n.get("content", {}).get("title", "") for n in (tk.news or [])]
        if any(heads):
            print("  RECENT HEADLINES")
            for h in [x for x in heads[:4] if x]:
                print(f"    - {_ascii(h, 80)}")
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    import sys

    names = sys.argv[1:] or ["CELH", "CAVA"]
    for t in names:
        brief(t)
