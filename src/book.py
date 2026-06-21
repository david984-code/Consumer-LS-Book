"""Consumer demand scorecard -> a market-neutral long/short tilt.

conviction(name) = demand_temperature(subsector) x trust(name).  We demean
convictions across the universe so the book is long the *relatively* hottest
names and short the coldest -- net-zero by construction. Low-trust names (signals
that don't read that name well) get small positions automatically.

This is a conviction/sizing INPUT to a discretionary book, not an autopilot.
"""

from __future__ import annotations

import json

import pandas as pd

import config

from .signals import current_signals


def scorecard(force: bool = False) -> pd.DataFrame:
    sigs = current_signals(force=force)
    rows = []
    for name, (subsector, sig_key, trust) in config.UNIVERSE.items():
        t = sigs.get(sig_key)
        if not t:
            continue
        rows.append(
            {
                "name": name,
                "subsector": subsector,
                "signal": sig_key,
                "as_of": t["as_of"],
                "demand_z": round(t["z"], 2),
                "trust": trust,
                "conviction": round(t["z"] * trust, 2),
            }
        )
    df = pd.DataFrame(rows)
    df["weight"] = _weights(df["conviction"])
    return df.sort_values("weight", ascending=False).reset_index(drop=True)


def _weights(conviction: pd.Series) -> pd.Series:
    """Demean -> normalize to gross 100%: long hottest, short coldest, net ~0."""
    demeaned = conviction - conviction.mean()
    gross = demeaned.abs().sum() or 1.0
    return (demeaned / gross).round(3)


def build(force: bool = False) -> dict:
    df = scorecard(force=force)
    longs = df[df["weight"] > 0]
    shorts = df[df["weight"] < 0]
    book = {
        "as_of": df["as_of"].max(),
        "gross_pct": round(float(df["weight"].abs().sum()) * 100, 0),
        "net_pct": round(float(df["weight"].sum()) * 100, 1),
        "longs": dict(zip(longs["name"], longs["weight"], strict=True)),
        "shorts": dict(zip(shorts["name"], shorts["weight"], strict=True)),
    }
    _print(df, book)
    (config.OUTPUT_DIR / "book.json").write_text(json.dumps(book, indent=2))
    df.to_csv(config.OUTPUT_DIR / "scorecard.csv", index=False)
    return book


def _print(df: pd.DataFrame, book: dict) -> None:
    print(f"CONSUMER DEMAND SCORECARD  (as of {book['as_of']})")
    print("=" * 68)
    print(f"  {'name':5}{'subsector':11}{'demand z':>9}{'trust':>7}{'conviction':>12}{'weight':>9}")
    for _, r in df.iterrows():
        print(
            f"  {r['name']:5}{r['subsector']:11}{r['demand_z']:>9.2f}{r['trust']:>7.2f}"
            f"{r['conviction']:>12.2f}{r['weight']:>+9.1%}"
        )
    print("-" * 68)
    print(
        f"  PROPOSED L/S TILT (gross {book['gross_pct']:.0f}%, net {book['net_pct']:+.0f}%, "
        f"dollar-neutral):"
    )
    print(f"    LONG : {', '.join(f'{k} {v:+.0%}' for k, v in book['longs'].items())}")
    print(f"    SHORT: {', '.join(f'{k} {v:+.0%}' for k, v in book['shorts'].items())}")
    print("  Conviction input to a discretionary book -- not an autopilot. Macro is")
    print("  read judgmentally, not wired in. Beta-neutralization is a next step.")


if __name__ == "__main__":
    build()
