"""Unit tests for the L/S construction + temperature logic (no network)."""

import numpy as np
import pandas as pd

from src import backtest, book, brief, macro, shorts, signals


def test_catalysts_never_flip_a_thesis():
    # A strong long with the WORST possible demand AND valuation stays LONG.
    sized = book._resize(thesis=2.0, demand=-5.0, value=-5.0)
    assert sized > 0  # still a long -- catalysts cannot flip the thesis
    assert sized < 2.0  # but trimmed hard (to the -50% bound)


def test_catalysts_confirm_and_add_within_a_bound():
    base = 2.0
    hot = book._resize(base, demand=+1.0, value=+1.0)  # both confirm -> add
    cold = book._resize(base, demand=-1.0, value=-1.0)  # both contradict -> trim
    assert hot > base > cold > 0
    assert hot <= base * 1.5 and cold >= base * 0.5  # bounded to +-50%


def test_value_can_offset_soft_demand():
    # UBER case: soft demand but cheap valuation -> net roughly neutral / a small add.
    soft_only = book._resize(2.0, demand=-0.24, value=0.0)
    with_value = book._resize(2.0, demand=-0.24, value=+0.48)
    assert with_value > soft_only  # cheapness offsets the soft demand
    assert with_value > 2.0  # ... enough to add to the long here


def test_short_thesis_grows_when_demand_cold():
    # A short thesis confirmed by COLD demand gets bigger (more negative).
    assert book._resize(thesis=-2.0, demand=-1.0, value=0.0) < -2.0
    assert book._resize(thesis=-2.0, demand=+1.0, value=0.0) > -2.0  # hot trims a short


def test_caps_limit_a_dominant_name():
    w = pd.Series({"A": 0.8, "B": 0.05, "C": 0.05, "D": -0.05, "E": -0.05})
    sub = pd.Series(
        dict.fromkeys("ABCDE", "x") | {"A": "a", "B": "b", "C": "c", "D": "d", "E": "e"}
    )
    r = book._apply_caps(w, sub, 0.25, 0.40)
    assert r.abs().max() <= 0.25 + 1e-3  # no name over the 25% cap
    assert abs(r.abs().sum() - 1.0) < 1e-2  # still fully grossed
    assert r["A"] > 0 and r["D"] < 0  # signs preserved


def test_caps_limit_a_dominant_subsector():
    w = pd.Series({"A": 0.3, "B": 0.3, "C": 0.3, "D": -0.1, "E": -0.1, "F": -0.1, "G": -0.1})
    sub = pd.Series({"A": "air", "B": "air", "C": "air", "D": "g", "E": "h", "F": "r", "G": "s"})
    r = book._apply_caps(w, sub, 0.25, 0.40)
    assert r[["A", "B", "C"]].abs().sum() <= 0.40 + 1e-3  # subsector under its cap


def test_single_name_relaxes_to_full_gross():
    r = book._apply_caps(pd.Series({"UBER": 2.17}), pd.Series({"UBER": "rideshare"}), 0.25, 0.40)
    assert abs(r["UBER"] - 1.0) < 1e-6  # one view -> caps can't bind, stays 100%


def test_hedge_weight_zeroes_sleeve_beta():
    # A net-long-beta sleeve -> short the hedge ETF to offset it.
    w = pd.Series({"hi": 0.5, "lo": -0.5})
    b = pd.Series({"hi": 1.6, "lo": 0.8})
    hedge = book._hedge_weight(w, b)
    assert hedge < 0  # short the hedge ETF to offset the net-long beta
    assert abs((w * b).sum() + hedge) < 1e-9  # sleeve beta + hedge == 0


def test_ls_spread_is_dollar_neutral_and_directional():
    panel = pd.DataFrame({"A": [2.0], "B": [0.0], "C": [-2.0]})
    fwd = pd.DataFrame({"A": [0.10], "B": [0.0], "C": [-0.10]})
    sp = backtest._ls_spread(panel, fwd)
    assert sp.iloc[0] > 0  # long the liked (rose), short the disliked (fell) -> positive


def test_bootstrap_flags_a_clear_edge_and_clears_noise():
    edge = backtest._bootstrap(pd.Series([0.05] * 12), n=500)
    assert edge["significant"] and edge["ci90_ann_pct"][0] > 0
    noise = backtest._bootstrap(pd.Series([0.1, -0.1] * 8), n=500)
    assert not noise["significant"]  # zero-mean -> CI spans 0


def test_brief_formatters_handle_missing():
    assert brief._mult(14.4) == "14.4x" and brief._mult(None) == "n/a"
    assert brief._pct(0.5) == "+50%" and brief._pct(None) == "n/a"
    assert brief._bil(1e10) == "$10.0B" and brief._bil(None) == "n/a"


def test_short_scanner_flags():
    up = {"above_200dma": True, "r6": 0.30}
    assert any("MOMENTUM" in f for f in shorts._flags(0.03, 4.0, 44, up))  # uptrend
    assert any("SQUEEZE" in f for f in shorts._flags(0.20, 8.0, None, {}))  # crowded short
    assert any("EVENT" in f for f in shorts._flags(0.03, 2.0, 5, {}))  # earnings imminent
    clean = shorts._flags(0.03, 2.0, 60, {"above_200dma": False, "r6": -0.1})
    assert clean == []  # quiet name, no flags


def test_macro_label_thresholds():
    # Display-only regime labels: extremes read clearly, the middle reads neutral.
    assert macro._label(1.0) == "RISK-ON"
    assert macro._label(-1.0) == "RISK-OFF / late-cycle"
    assert macro._label(0.0) == "NEUTRAL / mid-cycle"


def test_temperature_zscores_latest_growth():
    idx = pd.date_range("2010-03-31", periods=24, freq="QE")
    seasonal = np.array([1.0, 1.3, 0.8, 1.1])[idx.quarter - 1]
    s = pd.Series(np.exp(0.02 * np.arange(24)) * seasonal, index=idx)
    t = signals._temperature(s)
    assert t and "z" in t and "as_of" in t
    assert abs(t["z"]) < 3  # a clean trend -> latest growth near the mean
