"""Informational macro-regime panel -- DISPLAY ONLY.

By design this NEVER touches the book's sizing. The systematic macro-overlay
approach was tested and disproven (see the Economic-Regime project); macro is read
judgmentally, not wired in. This panel just lets a human eyeball where the cycle is
before reading the book. A few free FRED series, each graded risk-on (+1) /
neutral (0) / risk-off (-1), averaged into a context label.
"""

from __future__ import annotations

from io import StringIO

import pandas as pd
import requests

from .data.net import network_retry

_UA = {"User-Agent": "Mozilla/5.0 (consumer-ls-book research)"}


@network_retry
def _fred(series_id: str) -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    r = requests.get(url, headers=_UA, timeout=60)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text))
    df.columns = ["date", "v"]
    df["date"] = pd.to_datetime(df["date"])
    df["v"] = pd.to_numeric(df["v"], errors="coerce")
    return df.dropna().set_index("date")["v"]


def _label(score: float) -> str:
    if score >= 0.5:
        return "RISK-ON"
    if score >= 0.15:
        return "mildly risk-on"
    if score > -0.15:
        return "NEUTRAL / mid-cycle"
    if score > -0.5:
        return "cautious"
    return "RISK-OFF / late-cycle"


def _indicators() -> list[dict]:
    """Each: name, current read string, risk_on grade (+1/0/-1), note. Network."""
    out: list[dict] = []

    def add(name: str, read: str, grade: int, note: str) -> None:
        out.append({"name": name, "read": read, "grade": grade, "note": note})

    try:  # 10y-2y term spread: inverted = late-cycle
        s = _fred("T10Y2Y").iloc[-1]
        g = 1 if s > 0.5 else (0 if s >= 0 else -1)
        add("yield curve (10y-2y)", f"{s:+.2f}pp", g, "inverted" if s < 0 else "positive")
    except Exception:  # noqa: BLE001
        pass
    try:  # high-yield credit spread vs its trailing 1y median
        s = _fred("BAMLH0A0HYM2")
        cur, med = float(s.iloc[-1]), float(s.tail(252).median())
        g = 1 if cur < med * 0.9 else (-1 if cur > med * 1.1 else 0)
        add(
            "HY credit spread", f"{cur:.2f}%", g, "tight" if g > 0 else ("wide" if g < 0 else "avg")
        )
    except Exception:  # noqa: BLE001
        pass
    try:  # unemployment vs 12 months ago: rising = risk-off
        s = _fred("UNRATE")
        cur, yr = float(s.iloc[-1]), float(s.iloc[-13])
        g = -1 if cur - yr > 0.3 else (1 if cur - yr < -0.1 else 0)
        add(
            "unemployment",
            f"{cur:.1f}% ({cur - yr:+.1f}pp y/y)",
            g,
            "rising" if g < 0 else "stable/falling",
        )
    except Exception:  # noqa: BLE001
        pass
    try:  # consumer sentiment vs its trailing 1y median (consumer-specific)
        s = _fred("UMCSENT")
        cur, med = float(s.iloc[-1]), float(s.tail(12).median())
        g = 1 if cur > med * 1.03 else (-1 if cur < med * 0.97 else 0)
        add(
            "consumer sentiment",
            f"{cur:.0f}",
            g,
            "improving" if g > 0 else ("softening" if g < 0 else "flat"),
        )
    except Exception:  # noqa: BLE001
        pass
    try:  # national financial conditions: >0 = tight = risk-off
        s = _fred("NFCI").iloc[-1]
        g = 1 if s < -0.1 else (-1 if s > 0.1 else 0)
        add(
            "financial conditions",
            f"{s:+.2f}",
            g,
            "loose" if g > 0 else ("tight" if g < 0 else "neutral"),
        )
    except Exception:  # noqa: BLE001
        pass
    return out


def panel() -> dict:
    inds = _indicators()
    if not inds:
        return {}
    score = sum(i["grade"] for i in inds) / len(inds)
    return {"score": round(score, 2), "label": _label(score), "indicators": inds}


def print_panel() -> None:
    p = panel()
    print("\n3) MACRO CONTEXT  (informational only -- does NOT affect the book)")
    print("=" * 68)
    if not p:
        print("  macro panel unavailable (FRED fetch failed).")
        return
    for i in p["indicators"]:
        arrow = "+" if i["grade"] > 0 else ("-" if i["grade"] < 0 else "=")
        print(f"  [{arrow}] {i['name']:22}{i['read']:>20}   {i['note']}")
    print("-" * 68)
    print(f"  REGIME READ: {p['label']}  (risk-on score {p['score']:+.2f})")
    print("  For your judgment only -- the book is market-neutral by construction.")


if __name__ == "__main__":
    print_panel()
