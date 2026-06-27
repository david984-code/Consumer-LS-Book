"""Thesis-anchored Consumer L/S book.

Two clearly separated layers:
  1. DEMAND RADAR -- which subsectors' demand is hot/cold right now (idea
     generation / timing). conviction = demand_temperature x trust.
  2. THE BOOK -- positions come from YOUR fundamental views (config.THESES). Demand
     + value only SIZE each view (never flip it), then a dynamic overlay (volatility
     scaling, price bands, momentum gates) adjusts weight, caps cap it, and each
     sleeve is beta-neutralized vs its own equal-weight sector ETF.

The alt-data informs the discretionary book; it does not replace it.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

import config

from . import macro
from .data.prices import fetch as fetch_prices
from .data.prices import hedge_betas
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


def _hedge_weight(weight: pd.Series, beta: pd.Series) -> float:
    """Hedge-ETF weight that zeroes a sleeve's net beta vs that ETF (ETF beta = 1)."""
    return round(-float((weight * beta).sum()), 3)


def _waterfill(a: np.ndarray, sub: np.ndarray, name_cap: float, sub_cap: float) -> np.ndarray:
    """Iterate subsector + name caps, redistributing freed weight to names with room."""
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
    return a


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
    # If the name cap can't even sum to full gross (too few names), it can't bind
    # without flattening conviction -- so relax entirely and keep conviction weights.
    if name_cap * len(a) < 1.0 - 1e-9:
        return pd.Series(a * sign, index=weight.index).round(3)
    a = _waterfill(a, sub, name_cap, sub_cap)
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


def _band_mult(price: float, floor: float, ceiling: float) -> float:
    """Full weight at/below the floor, scaling to 0 at/above the ceiling."""
    if price >= ceiling:
        return 0.0
    if price <= floor:
        return 1.0
    return (ceiling - price) / (ceiling - floor)


def _momentum_mult(close: pd.Series) -> float:
    """Small until an uptrend confirms (below 200dma), then scale up by 6m strength."""
    c = close.dropna()
    if len(c) < 200:
        return 1.0
    last, dma200 = float(c.iloc[-1]), float(c.tail(200).mean())
    if last < dma200:
        return 0.30  # no uptrend -> minimal
    r6 = last / float(c.iloc[-126]) - 1 if len(c) > 126 else 0.0
    return min(1.0, 0.5 + max(0.0, r6))  # uptrend -> 0.5..1.0 by momentum


def _dynamic_mults(names: list[str], force: bool = False) -> tuple[dict[str, float], list[str]]:
    """Per-name sizing overlay (vol scaling x price band x momentum gate) + alerts."""
    px = fetch_prices(force=force)
    rets = px.pct_change()
    have = [n for n in names if n in px.columns]
    vol = {n: float(rets[n].tail(63).std()) or 1e-9 for n in have}
    inv = {n: 1.0 / vol[n] for n in have}
    mean_inv = sum(inv.values()) / len(inv) if inv else 1.0
    mults: dict[str, float] = {}
    alerts: list[str] = []
    for n in names:
        vmult = (inv[n] / mean_inv) if (config.VOL_SCALING and n in inv) else 1.0
        bmult = 1.0
        if n in config.PRICE_BANDS and n in px.columns:
            last = float(px[n].dropna().iloc[-1])
            floor, ceiling = config.PRICE_BANDS[n]
            bmult = _band_mult(last, floor, ceiling)
            if last >= ceiling:
                alerts.append(
                    f"{n} ${last:.2f} broke the ${ceiling:.0f} ceiling -- zeroed, revisit"
                )
        mmult = _momentum_mult(px[n]) if (n in config.MOMENTUM_GATED and n in px.columns) else 1.0
        mults[n] = round(vmult * bmult * mmult, 2)
    return mults, alerts


def _position_row(name: str, thesis: float, demand: dict, value: dict, b: dict) -> dict:
    """Assemble one un-overlaid position row from thesis + demand + value + beta."""
    d, v = float(demand.get(name, 0.0)), float(value.get(name, 0.0))
    subsector = config.UNIVERSE[name][0]
    return {
        "name": name,
        "thesis": thesis,
        "demand": round(d, 2),
        "value": round(v, 2),
        "sized": round(_resize(thesis, d, v), 2),
        "beta": round(b.get(name, 1.0), 2),
        "subsector": subsector,
        "hedge": config.hedge_etf(subsector),
    }


def _apply_overlay_and_caps(df: pd.DataFrame, force: bool) -> pd.DataFrame:
    """Apply the dynamic overlay (vol x band x momentum) then the gross/name caps."""
    mults, alerts = _dynamic_mults(list(df["name"]), force=force)
    df["size_x"] = df["name"].map(lambda n: mults.get(n, 1.0))
    df["sized"] = (df["sized"] * df["size_x"]).round(2)
    df.attrs["alerts"] = alerts
    capped = _apply_caps(
        pd.Series(df["sized"].to_numpy(), index=df["name"]),
        pd.Series(df["subsector"].to_numpy(), index=df["name"]),
        config.MAX_NAME,
        config.MAX_SUBSECTOR,
    )
    df["weight"] = df["name"].map(capped)
    return df.sort_values("weight", ascending=False).reset_index(drop=True)


def positions(force: bool = False) -> pd.DataFrame:
    """The book: thesis-anchored, demand + value + dynamic-sized, betas attached."""
    radar = demand_radar(force=force)
    demand = dict(zip(radar["name"], radar["conviction"], strict=True))
    value = cached_scores(force=force)
    b = hedge_betas(force=force)
    rows = [
        _position_row(name, thesis, demand, value, b)
        for name, thesis in config.THESES.items()
        if thesis
    ]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return _apply_overlay_and_caps(df, force)


def _book_metrics(pos: pd.DataFrame) -> dict:
    """Risk/exposure summary for a non-empty positions frame."""
    # hedge each sleeve against its own equal-weight ETF (RSPD/RSPS)
    hedges = {
        str(etf): round(_hedge_weight(sleeve["weight"], sleeve["beta"]) * 100, 1)
        for etf, sleeve in pos.groupby("hedge")
    }
    sub_exp = pos.groupby("subsector")["weight"].apply(lambda s: float(s.abs().sum()))
    relaxed = bool(
        pos["weight"].abs().max() > config.MAX_NAME + 1e-3
        or sub_exp.max() > config.MAX_SUBSECTOR + 1e-3
    )
    return {
        "gross_pct": round(float(pos["weight"].abs().sum()) * 100, 0),
        "net_dollar_pct": round(float(pos["weight"].sum()) * 100, 1),
        "hedges_pct": hedges,  # {etf: short weight % that zeroes that sleeve's beta}
        "max_position_pct": round(float(pos["weight"].abs().max()) * 100, 1),
        "subsector_exposure": {k: round(v * 100, 1) for k, v in sub_exp.items()},
        "caps_relaxed": relaxed,
        "alerts": list(pos.attrs.get("alerts", [])),
        "positions": dict(zip(pos["name"], pos["weight"], strict=True)),
    }


def build(force: bool = False) -> dict:
    radar = demand_radar(force=force)
    pos = positions(force=force)
    book: dict = {"as_of": radar["as_of"].max()}
    if not pos.empty:
        book.update(_book_metrics(pos))
    _print(radar, pos, book)
    try:
        macro.print_panel()  # informational only -- never feeds back into sizing
    except Exception as exc:  # noqa: BLE001
        print(f"\n3) MACRO CONTEXT unavailable ({exc})")
    (config.OUTPUT_DIR / "book.json").write_text(json.dumps(book, indent=2))
    radar.to_csv(config.OUTPUT_DIR / "demand_radar.csv", index=False)
    return book


def _print_radar(radar: pd.DataFrame, as_of: object) -> None:
    print(f"1) DEMAND RADAR  (idea generation, as of {as_of})")
    print("=" * 60)
    print(f"  {'name':5}{'subsector':11}{'demand z':>9}{'trust':>7}{'conviction':>12}")
    for _, r in radar.iterrows():
        print(
            f"  {r['name']:5}{r['subsector']:11}{r['demand_z']:>9.2f}"
            f"{r['trust']:>7.2f}{r['conviction']:>12.2f}"
        )


def _print_positions(pos: pd.DataFrame) -> None:
    print(f"  {'name':5}{'thesis':>8}{'value':>8}{'size x':>8}{'beta':>6}{'hedge':>7}{'weight':>9}")
    for _, r in pos.iterrows():
        print(
            f"  {r['name']:5}{r['thesis']:>+8.1f}{r['value']:>+8.2f}{r['size_x']:>8.2f}"
            f"{r['beta']:>6.2f}{r['hedge']:>7}{r['weight']:>+9.1%}"
        )


def _print_risk(book: dict) -> None:
    for a in book.get("alerts", []):
        print(f"  ! ALERT: {a}")
    hedge_str = ", ".join(f"{etf} {w:+.0f}%" for etf, w in book["hedges_pct"].items())
    print(f"    + SECTOR HEDGE: {hedge_str}  (each zeroes its sleeve's beta vs that ETF)")
    print(
        f"  RISK: gross {book['gross_pct']:.0f}%, net-$ {book['net_dollar_pct']:+.0f}%, "
        f"max {book['max_position_pct']:.0f}% (cap {config.MAX_NAME:.0%})"
    )
    exp = ", ".join(f"{k} {v:.0f}%" for k, v in book["subsector_exposure"].items())
    print(f"  SUBSECTOR (cap {config.MAX_SUBSECTOR:.0%}): {exp}")
    if book["caps_relaxed"]:
        print("  * caps relaxed -- too few views to diversify; add more theses to bind them.")
    print("  Longs you believe in, each hedged vs the EQUAL-WEIGHT consumer sector")
    print("  (no Amazon distortion). The bet: your picks beat the average consumer name.")


def _print(radar: pd.DataFrame, pos: pd.DataFrame, book: dict) -> None:
    _print_radar(radar, book["as_of"])
    print("\n2) THE BOOK  (THESES x demand + value x dynamic sizing, sector-hedged)")
    print("=" * 76)
    if pos.empty:
        print("  No views set. Add your fundamental views in config.THESES.")
        return
    _print_positions(pos)
    print("-" * 76)
    _print_risk(book)


if __name__ == "__main__":
    build()
