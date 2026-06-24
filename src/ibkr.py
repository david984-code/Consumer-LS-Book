"""Submit the book's order ticket to YOUR IBKR PAPER account, via IB Gateway.

YOU run this, on your machine, with IB Gateway open and logged in to PAPER mode.
The script connects to the local Gateway socket -- there are NO credentials in this
file; the Gateway holds your login. It never logs in for you.

Safeguards:
  * DRY RUN by default -- prints the orders and sends NOTHING. You must pass --send.
  * Refuses to trade any account whose id is not a paper id (paper ids start "DU").
  * Limit orders with a small buffer, GTC.

First:  pip install ib_async   (the maintained IBKR API client; ib_insync also works)

    python -m src.ibkr                      # DRY RUN: print orders, send nothing
    python -m src.ibkr --send               # transmit to the PAPER account
    python -m src.ibkr --send --gross 50000 --port 4002
"""

from __future__ import annotations

import sys

from .orders import build_ticket

_PAPER_PORT = 4002  # IB Gateway paper. (TWS paper = 7497.)
_BUFFER = 0.01  # limit-price buffer for fills: buys above, shorts below


def _api() -> tuple:
    try:
        import ib_async as api
    except ImportError:
        try:
            import ib_insync as api  # type: ignore[no-redef]
        except ImportError as exc:
            raise SystemExit("Install the API client first:  pip install ib_async") from exc
    return api.IB, api.Stock, api.LimitOrder


def submit(gross: float = 100_000.0, send: bool = False, port: int = _PAPER_PORT) -> None:
    ib_cls, stock_cls, limit_cls = _api()
    ib = ib_cls()
    ib.connect("127.0.0.1", port, clientId=17, timeout=10)
    try:
        accounts = list(ib.managedAccounts())
        # HARD GUARD: paper accounts start with "DU". Anything else -> abort, no orders.
        if not accounts or not all(a.startswith("DU") for a in accounts):
            raise SystemExit(
                f"REFUSING TO TRADE: account(s) {accounts} are not paper "
                "(paper ids start with 'DU'). Aborting -- nothing sent."
            )
        ticket = [o for o in build_ticket(gross) if o["price"] and o["shares"]]
        if not ticket:
            print("No theses set in config.THESES -- nothing to do.")
            return
        header = f"SENDING to PAPER {accounts}" if send else "DRY RUN -- nothing will be sent"
        print(f"{header}\n{'=' * 60}")
        for o in ticket:
            limit = round(
                o["price"] * (1 + _BUFFER) if o["side"] == "BUY" else o["price"] * (1 - _BUFFER), 2
            )
            print(f"  {o['side']:4} {o['shares']:>6,} {o['ticker']:6} LMT {limit:>9} GTC")
            if send:
                contract = stock_cls(o["ticker"], "SMART", "USD")
                ib.qualifyContracts(contract)
                ib.placeOrder(contract, limit_cls(o["side"], o["shares"], limit, tif="GTC"))
        print("-" * 60)
        if send:
            ib.sleep(2)
            print(f"  submitted {len(ticket)} orders to {accounts}. Review them in Gateway/TWS.")
        else:
            print("  DRY RUN complete. Re-run with --send to transmit to your PAPER account.")
    finally:
        ib.disconnect()


if __name__ == "__main__":
    a = sys.argv[1:]
    g = float(a[a.index("--gross") + 1]) if "--gross" in a else 100_000.0
    p = int(a[a.index("--port") + 1]) if "--port" in a else _PAPER_PORT
    submit(gross=g, send="--send" in a, port=p)
