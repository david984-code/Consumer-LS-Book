"""Order ticket: the book's weights -> dollars + shares per position, including the
sector hedges, at a chosen gross notional.

Prices are the latest close (you place against live quotes in your broker). This is
informational -- it NEVER sends orders. Run before each rebalance for fresh prices.

    python -m src.orders 100000      # size the book to a $100k long notional
"""

from __future__ import annotations

from .book import _hedge_weight, positions
from .data.prices import fetch as fetch_prices


def build_ticket(gross: float = 100_000.0, force: bool = False) -> list[dict]:
    """The order ticket as data: [{ticker, side BUY/SELL, shares, price}] for every
    single-name position plus the sector-hedge shorts. Prices are the last close."""
    pos = positions(force=force)
    if pos.empty:
        return []
    px = fetch_prices().iloc[-1]

    def row(ticker: str, w: float) -> dict:
        price = float(px.get(ticker, float("nan")))
        shares = int(round(abs(w) * gross / price)) if price == price and price else 0
        return {
            "ticker": ticker,
            "side": "BUY" if w > 0 else "SELL",
            "shares": shares,
            "price": round(price, 2) if price == price else None,
        }

    out = [row(str(r["name"]), float(r["weight"])) for _, r in pos.iterrows()]
    out += [
        row(str(etf), _hedge_weight(sleeve["weight"], sleeve["beta"]))
        for etf, sleeve in pos.groupby("hedge")
    ]
    return out


def order_ticket(gross: float = 100_000.0, force: bool = False) -> None:
    ticket = build_ticket(gross, force=force)
    print(f"ORDER TICKET  (book gross ${gross:,.0f}; prices = last close)")
    print("=" * 60)
    if not ticket:
        print("  No theses set in config.THESES.")
        return
    print(f"  {'ticker':7}{'side':12}{'shares':>9}{'price':>10}{'notional':>13}")
    for o in ticket:
        side = "BUY" if o["side"] == "BUY" else "SELL SHORT"
        price = o["price"]
        notional = (o["shares"] * price) if price else 0
        px_str = f"{price:.2f}" if price else "n/a"
        print(f"  {o['ticker']:7}{side:12}{o['shares']:>9,}{px_str:>10}{notional:>13,.0f}")
    print("  This is informational -- it never sends orders. paperMoney only.")


if __name__ == "__main__":
    import sys

    amount = float(sys.argv[1]) if len(sys.argv) > 1 else 100_000.0
    order_ticket(amount)
