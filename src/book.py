"""Thesis-anchored Consumer L/S book.

Two clearly separated layers:
  1. DEMAND RADAR -- which subsectors' demand is hot/cold right now (idea
     generation / timing). conviction = demand_temperature x trust.
  2. THE BOOK -- positions come from YOUR fundamental views (config.THESES). The
     demand radar only SIZES each view (a confirming signal adds, a contradicting
     one trims) within a bound, so it NEVER flips your direction. Then we
     beta-neutralize with an SPY hedge.

The alt-data informs the discretionary book; it does not replace it. A soft
demand quarter trims a high-conviction long like UBER -- it does not short it.
"""

from __future__ import annotations

import json

import pandas as pd

import config

from .data.prices import betas
from .signals import current_signals

_CATALYST_GAIN = 0.40  # how far the demand signal can resize a thesis
_CATALYST_CAP = 0.50  # ... bounded to +-50% so it never flips your direction


def demand_radar(force: bool = False) -> pd.DataFrame:
    """Per-name demand temperature (idea generation). Not positions."""
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
                "as_of": t["as_of"],
                "demand_z": round(t["z"], 2),
                "trust": trust,
                "conviction": round(t["z"] * trust, 2),
            }
        )
    return pd.DataFrame(rows).sort_values("conviction", ascending=False).reset_index(drop=True)


def _spy_hedge(weight: pd.Series, beta: pd.Series) -> float:
    """SPY weight that zeroes the book's net beta (SPY beta = 1)."""
    return round(-float((weight * beta).sum()), 3)


def _resize(thesis: float, catalyst: float) -> float:
    """Resize a thesis by the demand catalyst, clamped so the sign never flips."""
    aligned = catalyst * (1 if thesis > 0 else -1)  # >0 when demand confirms thesis
    mult = 1 + max(-_CATALYST_CAP, min(_CATALYST_CAP, _CATALYST_GAIN * aligned))
    return thesis * mult


def positions(force: bool = False) -> pd.DataFrame:
    """The book: thesis-anchored, demand-sized, with betas attached."""
    radar = demand_radar(force=force)
    catalysts = dict(zip(radar["name"], radar["conviction"], strict=True))
    b = betas(force=force)
    rows = []
    for name, thesis in config.THESES.items():
        if not thesis:
            continue
        catalyst = float(catalysts.get(name, 0.0))
        rows.append(
            {
                "name": name,
                "thesis": thesis,
                "demand_catalyst": round(catalyst, 2),
                "sized": round(_resize(thesis, catalyst), 2),
                "beta": round(b.get(name, 1.0), 2),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    gross = df["sized"].abs().sum() or 1.0
    df["weight"] = (df["sized"] / gross).round(3)
    return df.sort_values("weight", ascending=False).reset_index(drop=True)


def build(force: bool = False) -> dict:
    radar = demand_radar(force=force)
    pos = positions(force=force)
    book: dict = {"as_of": radar["as_of"].max()}
    if not pos.empty:
        spy = _spy_hedge(pos["weight"], pos["beta"])
        net_beta = float((pos["weight"] * pos["beta"]).sum())
        book.update(
            gross_pct=round(float(pos["weight"].abs().sum()) * 100, 0),
            net_dollar_pct=round(float(pos["weight"].sum()) * 100, 1),
            spy_hedge_pct=round(spy * 100, 1),
            net_beta_after_hedge=round(net_beta + spy, 2),
            max_position_pct=round(float(pos["weight"].abs().max()) * 100, 1),
            positions=dict(zip(pos["name"], pos["weight"], strict=True)),
        )
    _print(radar, pos, book)
    (config.OUTPUT_DIR / "book.json").write_text(json.dumps(book, indent=2))
    radar.to_csv(config.OUTPUT_DIR / "demand_radar.csv", index=False)
    return book


def _print(radar: pd.DataFrame, pos: pd.DataFrame, book: dict) -> None:
    print(f"1) DEMAND RADAR  (idea generation, as of {book['as_of']})")
    print("=" * 60)
    print(f"  {'name':5}{'subsector':11}{'demand z':>9}{'trust':>7}{'conviction':>12}")
    for _, r in radar.iterrows():
        print(
            f"  {r['name']:5}{r['subsector']:11}{r['demand_z']:>9.2f}"
            f"{r['trust']:>7.2f}{r['conviction']:>12.2f}"
        )
    print("\n2) THE BOOK  (your THESES, sized by demand, beta-neutral)")
    print("=" * 60)
    if pos.empty:
        print("  No views set. Add your fundamental views in config.THESES.")
        return
    print(f"  {'name':5}{'thesis':>8}{'demand':>8}{'sized':>8}{'beta':>6}{'weight':>9}")
    for _, r in pos.iterrows():
        print(
            f"  {r['name']:5}{r['thesis']:>+8.1f}{r['demand_catalyst']:>+8.2f}"
            f"{r['sized']:>+8.2f}{r['beta']:>6.2f}{r['weight']:>+9.1%}"
        )
    print("-" * 60)
    print(
        f"    + SPY hedge {book['spy_hedge_pct']:+.0f}% -> "
        f"net beta {book['net_beta_after_hedge']:+.2f}"
    )
    print(
        f"  RISK: gross {book['gross_pct']:.0f}%, net-$ {book['net_dollar_pct']:+.0f}%, "
        f"net-beta {book['net_beta_after_hedge']:+.2f}, max {book['max_position_pct']:.0f}%"
    )
    print("  Your thesis sets direction; demand only resizes it (never flips). UBER")
    print("  stays long on your view -- soft demand merely trims it.")


if __name__ == "__main__":
    build()
