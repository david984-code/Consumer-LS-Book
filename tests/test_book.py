"""Unit tests for the L/S construction + temperature logic (no network)."""

import numpy as np
import pandas as pd

from src import book, signals


def test_weights_are_dollar_neutral_long_hot_short_cold():
    conv = pd.Series({"hot": 2.0, "mid": 0.0, "cold": -2.0})
    w = book._weights(conv)
    assert abs(w.sum()) < 1e-9  # net ~ zero (market-neutral)
    assert abs(w.abs().sum() - 1.0) < 1e-9  # gross 100%
    assert w["hot"] > 0 > w["cold"]  # long the hot, short the cold


def test_weights_lean_with_conviction_magnitude():
    # All positive convictions -> demeaning still produces longs and shorts.
    w = book._weights(pd.Series({"a": 3.0, "b": 1.0}))
    assert w["a"] > 0 > w["b"] and abs(w.sum()) < 1e-9


def test_temperature_zscores_latest_growth():
    idx = pd.date_range("2010-03-31", periods=24, freq="QE")
    seasonal = np.array([1.0, 1.3, 0.8, 1.1])[idx.quarter - 1]
    s = pd.Series(np.exp(0.02 * np.arange(24)) * seasonal, index=idx)
    t = signals._temperature(s)
    assert t and "z" in t and "as_of" in t
    assert abs(t["z"]) < 3  # a clean trend -> latest growth near the mean
