"""Order ticket: the book's weights -> dollars + shares per position, including the
sector hedges, at a chosen gross notional.

Prices are the latest close (you place against live quotes in your broker). This is
informational -- it NEVER sends orders. Run before each rebalance for fresh prices.

    python -m src.orders 100000      # size the book to a $100k long notional
"""

from __future__ import annotations

from .book import _hedge_weight, positions
from .data.prices import fetch as fetch_prices


def order_ticket(gross: float = 100_000.0, force: bool = False) -> None:
    pos = positions(force=force)
    print(f"ORDER TICKET  (book gross ${gross:,.0f}; prices = last close)")
    print("=" * 64)
    if pos.empty:
        print("  No theses set in config.THESES.")
        return
    px = fetch_prices().iloc[-1]
    print(f"  {'ticker':7}{'side':6}{'weight':>8}{'notional':>12}{'price':>9}{'shares':>9}")

    def line(ticker: str, w: float) -> None:
        price = float(px.get(ticker, float("nan")))
        dollars = w * gross
        shares = int(round(dollars / price)) if price == price and price else 0
        side = "LONG" if w > 0 else "SHORT"
        px_str = f"{price:.2f}" if price == price else "n/a"
        print(f"  {ticker:7}{side:6}{w:>+8.1%}{abs(dollars):>12,.0f}{px_str:>9}{abs(shares):>9,}")

    for _, r in pos.iterrows():
        line(str(r["name"]), float(r["weight"]))
    print("  " + "-" * 56)
    for etf, sleeve in pos.groupby("hedge"):
        line(str(etf), _hedge_weight(sleeve["weight"], sleeve["beta"]))

    longs = float(pos[pos["weight"] > 0]["weight"].sum()) * gross
    shorts = float(pos[pos["weight"] < 0]["weight"].abs().sum()) * gross
    print(f"\n  single-name: ${longs:,.0f} long / ${shorts:,.0f} short, + sector-hedge")
    print("  shorts (RSPD/RSPS) on top. Net market + sector exposure ~ 0. paperMoney only.")


if __name__ == "__main__":
    import sys

    amount = float(sys.argv[1]) if len(sys.argv) > 1 else 100_000.0
    order_ticket(amount)
