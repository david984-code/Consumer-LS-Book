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

import numpy as np
import pandas as pd

import config

from . import macro
from .data.prices import betas
from .signals import current_signals
from .valuation import cached_scores

_GAIN_DEMAND = 0.35  # how far the demand signal can resize a thesis
_GAIN_VALUE = 0.35  # how far the valuation signal can resize a thesis
_CATALYST_CAP = 0.50  # total resize bounded to +-50% so it never flips direction


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


def _apply_caps(
    weight: pd.Series, subsector: pd.Series, name_cap: float, sub_cap: float
) -> pd.Series:
    """Water-fill weights so no name exceeds name_cap and no subsector exceeds
    sub_cap (as a fraction of gross), redistributing freed weight to names with
    room. With too few names/subsectors to satisfy the caps, they relax so the
    book stays fully grossed."""
    w = weight.astype(float).to_numpy().copy()
    sub = subsector.reindex(weight.index).to_numpy()
    tot = float(np.abs(w).sum())
    if tot == 0:
        return weight
    sign = np.where(w >= 0, 1.0, -1.0)
    a = np.abs(w) / tot  # gross 1
    subs = list(dict.fromkeys(sub))
    for _ in range(2000):
        for s in subs:
            m = sub == s
            ss = a[m].sum()
            if ss > sub_cap + 1e-12:
                a[m] *= sub_cap / ss
        a = np.minimum(a, name_cap)
        deficit = 1.0 - a.sum()
        if deficit <= 1e-9:
            break
        room = np.maximum(name_cap - a, 0.0)
        if room.sum() <= 1e-9:
            break  # fully capped given the names available
        a = a + deficit * room / room.sum()
    g = a.sum()
    if g > 1e-9:
        a = a / g  # rescale to full gross (relaxes caps only if they can't bind)
    return pd.Series(a * sign, index=weight.index).round(3)


def _resize(thesis: float, demand: float, value: float) -> float:
    """Resize a thesis by the demand + valuation catalysts, clamped so the sign
    never flips. A catalyst that *confirms* the thesis adds; one that contradicts
    trims. (Cheap confirms a long / expensive confirms a short.)"""
    sign = 1 if thesis > 0 else -1
    raw = (_GAIN_DEMAND * demand + _GAIN_VALUE * value) * sign
    mult = 1 + max(-_CATALYST_CAP, min(_CATALYST_CAP, raw))
    return thesis * mult


def positions(force: bool = False) -> pd.DataFrame:
    """The book: thesis-anchored, demand-sized, with betas attached."""
    radar = demand_radar(force=force)
    demand = dict(zip(radar["name"], radar["conviction"], strict=True))
    value = cached_scores(force=force)
    b = betas(force=force)
    rows = []
    for name, thesis in config.THESES.items():
        if not thesis:
            continue
        d, v = float(demand.get(name, 0.0)), float(value.get(name, 0.0))
        rows.append(
            {
                "name": name,
                "thesis": thesis,
                "demand": round(d, 2),
                "value": round(v, 2),
                "sized": round(_resize(thesis, d, v), 2),
                "beta": round(b.get(name, 1.0), 2),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["subsector"] = [config.UNIVERSE[n][0] for n in df["name"]]
    capped = _apply_caps(
        pd.Series(df["sized"].to_numpy(), index=df["name"]),
        pd.Series(df["subsector"].to_numpy(), index=df["name"]),
        config.MAX_NAME,
        config.MAX_SUBSECTOR,
    )
    df["weight"] = df["name"].map(capped)
    return df.sort_values("weight", ascending=False).reset_index(drop=True)


def build(force: bool = False) -> dict:
    radar = demand_radar(force=force)
    pos = positions(force=force)
    book: dict = {"as_of": radar["as_of"].max()}
    if not pos.empty:
        spy = _spy_hedge(pos["weight"], pos["beta"])
        net_beta = float((pos["weight"] * pos["beta"]).sum())
        sub_exp = pos.groupby("subsector")["weight"].apply(lambda s: float(s.abs().sum()))
        relaxed = bool(
            pos["weight"].abs().max() > config.MAX_NAME + 1e-3
            or sub_exp.max() > config.MAX_SUBSECTOR + 1e-3
        )
        book.update(
            gross_pct=round(float(pos["weight"].abs().sum()) * 100, 0),
            net_dollar_pct=round(float(pos["weight"].sum()) * 100, 1),
            spy_hedge_pct=round(spy * 100, 1),
            net_beta_after_hedge=round(net_beta + spy, 2),
            max_position_pct=round(float(pos["weight"].abs().max()) * 100, 1),
            subsector_exposure={k: round(v * 100, 1) for k, v in sub_exp.items()},
            caps_relaxed=relaxed,
            positions=dict(zip(pos["name"], pos["weight"], strict=True)),
        )
    _print(radar, pos, book)
    try:
        macro.print_panel()  # informational only -- never feeds back into sizing
    except Exception as exc:  # noqa: BLE001
        print(f"\n3) MACRO CONTEXT unavailable ({exc})")
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
    print("\n2) THE BOOK  (your THESES, sized by demand + value, beta-neutral)")
    print("=" * 68)
    if pos.empty:
        print("  No views set. Add your fundamental views in config.THESES.")
        return
    print(f"  {'name':5}{'thesis':>8}{'demand':>8}{'value':>8}{'sized':>8}{'beta':>6}{'weight':>9}")
    for _, r in pos.iterrows():
        print(
            f"  {r['name']:5}{r['thesis']:>+8.1f}{r['demand']:>+8.2f}{r['value']:>+8.2f}"
            f"{r['sized']:>+8.2f}{r['beta']:>6.2f}{r['weight']:>+9.1%}"
        )
    print("-" * 68)
    print(
        f"    + SPY hedge {book['spy_hedge_pct']:+.0f}% -> "
        f"net beta {book['net_beta_after_hedge']:+.2f}"
    )
    print(
        f"  RISK: gross {book['gross_pct']:.0f}%, net-$ {book['net_dollar_pct']:+.0f}%, "
        f"net-beta {book['net_beta_after_hedge']:+.2f}, max {book['max_position_pct']:.0f}% "
        f"(cap {config.MAX_NAME:.0%})"
    )
    exp = ", ".join(f"{k} {v:.0f}%" for k, v in book["subsector_exposure"].items())
    print(f"  SUBSECTOR (cap {config.MAX_SUBSECTOR:.0%}): {exp}")
    if book["caps_relaxed"]:
        print("  * caps relaxed -- too few views to diversify; add more theses to bind them.")
    print("  Your thesis sets direction; demand + valuation only resize it (never")
    print("  flip). UBER stays long: soft demand trims, but it's cheap -> value adds.")


if __name__ == "__main__":
    build()
