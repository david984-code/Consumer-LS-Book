"""Unit tests for the L/S construction + temperature logic (no network)."""

import numpy as np
import pandas as pd

from src import book, signals


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


def test_spy_hedge_zeroes_net_beta():
    # Long a high-beta name, short a low-beta one -> net long beta -> hedge < 0.
    w = pd.Series({"hi": 0.5, "lo": -0.5})
    b = pd.Series({"hi": 1.6, "lo": 0.8})
    hedge = book._spy_hedge(w, b)
    assert hedge < 0  # short SPY to offset the net-long beta
    assert abs((w * b).sum() + hedge) < 1e-9  # net beta + hedge == 0


def test_temperature_zscores_latest_growth():
    idx = pd.date_range("2010-03-31", periods=24, freq="QE")
    seasonal = np.array([1.0, 1.3, 0.8, 1.1])[idx.quarter - 1]
    s = pd.Series(np.exp(0.02 * np.arange(24)) * seasonal, index=idx)
    t = signals._temperature(s)
    assert t and "z" in t and "as_of" in t
    assert abs(t["z"]) < 3  # a clean trend -> latest growth near the mean
