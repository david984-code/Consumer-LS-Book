"""Daily READ-ONLY report for the consumer L/S book (paper account).

Connects to the running IB Gateway (port 4002), snapshots NAV + positions, appends
NAV to a local history log, and prints day P&L, cumulative return, net-$ exposure
(the neutrality check), Sharpe, and beta-to-SPY -- benchmarked against cash, not the
index (a market-neutral book should clear the risk-free rate at ~0 market beta).

Read-only: it NEVER places or cancels orders. Run it on a schedule once the gateway
auto-restarts hands-free.

    python -m src.report
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

import config

_PORT = 4002
_NAV_LOG = config.OUTPUT_DIR / "nav_history.csv"  # gitignored (outputs/)


def _connect():
    try:
        import ib_async as api
    except ImportError:
        import ib_insync as api  # type: ignore[no-redef]
    ib = api.IB()
    ib.connect("127.0.0.1", _PORT, clientId=19, timeout=10)
    accts = list(ib.managedAccounts())
    if not accts or not all(a.startswith("DU") for a in accts):
        ib.disconnect()
        raise SystemExit(f"REFUSING: account(s) {accts} are not paper (DU). Read-only abort.")
    return ib


def _snapshot(ib) -> tuple[float, list[dict]]:
    nav = 0.0
    for row in ib.accountSummary():
        if row.tag == "NetLiquidation" and row.currency == "USD":
            nav = float(row.value)
    pos = [
        {
            "sym": p.contract.symbol,
            "qty": int(p.position),
            "mv": float(p.marketValue),
            "pnl": float(p.unrealizedPNL),
        }
        for p in ib.portfolio()
    ]
    return nav, pos


def _log_nav(today: dt.date, nav: float) -> pd.DataFrame:
    cols = ["date", "nav"]
    hist = (
        pd.read_csv(_NAV_LOG, parse_dates=["date"])
        if _NAV_LOG.exists()
        else pd.DataFrame(columns=cols)
    )
    hist = hist[hist["date"] != pd.Timestamp(today)]  # replace today's row if re-run
    row = pd.DataFrame([{"date": pd.Timestamp(today), "nav": nav}])
    hist = pd.concat([hist, row], ignore_index=True).sort_values("date").reset_index(drop=True)
    hist.to_csv(_NAV_LOG, index=False)
    return hist


def _spy_beta(hist: pd.DataFrame) -> float | None:
    import yfinance as yf

    spy = yf.download(
        "SPY", start=str(hist["date"].iloc[0].date()), progress=False, auto_adjust=True
    )["Close"]
    book = hist.set_index("date")["nav"].pct_change()
    df = pd.concat([book.rename("b"), spy.pct_change().rename("s")], axis=1).dropna()
    if len(df) < 15:
        return None
    var = float(df["s"].var())
    return round(float(df["b"].cov(df["s"]) / var), 2) if var else None


def _metrics(hist: pd.DataFrame) -> dict:
    nav = hist["nav"].to_numpy()
    rets = pd.Series(nav).pct_change().dropna()
    sharpe = None
    if len(rets) >= 5 and rets.std() > 0:
        sharpe = round(float(rets.mean() / rets.std() * (252**0.5)), 2)
    return {
        "days": len(hist),
        "day_pnl": float(nav[-1] - nav[-2]) if len(nav) > 1 else 0.0,
        "cum_pct": float(nav[-1] / nav[0] - 1) * 100 if len(nav) > 1 else 0.0,
        "sharpe": sharpe,
        "spy_beta": _spy_beta(hist) if len(hist) >= 15 else None,
    }


def _print(nav: float, pos: list[dict], m: dict) -> None:
    longs = [p for p in pos if p["qty"] > 0]
    shorts = [p for p in pos if p["qty"] < 0]
    net = sum(p["mv"] for p in pos)
    print(f"CONSUMER L/S BOOK -- DAILY REPORT  ({dt.date.today()})")
    print("=" * 60)
    sharpe_s = (
        m["sharpe"] if m["sharpe"] is not None else f"n/a (need {max(0, 6 - m['days'])}+ more days)"
    )
    beta_s = m["spy_beta"] if m["spy_beta"] is not None else "n/a (need ~15+ days)"
    print(f"  NAV        ${nav:,.0f}   day {m['day_pnl']:+,.0f}   cumulative {m['cum_pct']:+.2f}%")
    print(f"  net-$ expo {net:+,.0f}  ({net / nav * 100:+.0f}%)  <- target ~0 (neutrality)")
    print(f"  Sharpe     {sharpe_s}")
    print(f"  SPY beta   {beta_s}  <- target ~0")
    print(f"  positions  {len(pos)}  ({len(longs)} long / {len(shorts)} short)")
    top = sorted(pos, key=lambda p: -p["pnl"])
    print("  best:  " + ", ".join(f"{p['sym']} {p['pnl']:+,.0f}" for p in top[:3]))
    print("  worst: " + ", ".join(f"{p['sym']} {p['pnl']:+,.0f}" for p in top[-3:]))
    print("  Benchmark: cash (risk-free). A neutral book should beat T-bills at SPY beta ~0.")


def report() -> dict:
    ib = _connect()
    try:
        nav, pos = _snapshot(ib)
    finally:
        ib.disconnect()
    hist = _log_nav(dt.date.today(), nav)
    m = _metrics(hist)
    _print(nav, pos, m)
    return {"nav": nav, **m}


if __name__ == "__main__":
    report()
