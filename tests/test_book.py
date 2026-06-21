"""Unit tests for the L/S construction + temperature logic (no network)."""

import numpy as np
import pandas as pd

from src import book, signals


def test_demand_never_flips_a_thesis():
    # A strong long with the WORST possible (cold) demand stays LONG, just trimmed.
    sized = book._resize(thesis=2.0, catalyst=-5.0)
    assert sized > 0  # still a long -- demand cannot flip the thesis
    assert sized < 2.0  # but trimmed by the soft demand


def test_demand_confirms_and_adds_within_a_bound():
    base = 2.0
    hot = book._resize(base, catalyst=+1.0)  # confirming demand adds size
    cold = book._resize(base, catalyst=-1.0)  # contradicting trims
    assert hot > base > cold > 0
    assert hot <= base * 1.5 and cold >= base * 0.5  # bounded to +-50%


def test_short_thesis_grows_when_demand_cold():
    # A short thesis confirmed by COLD demand gets bigger (more negative).
    assert book._resize(thesis=-2.0, catalyst=-1.0) < -2.0
    assert book._resize(thesis=-2.0, catalyst=+1.0) > -2.0  # hot demand trims a short


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
