"""Current 'demand temperature' per subsector signal.

Temperature = the latest deseasonalized QoQ growth of the free-data signal,
z-scored against its own history. Positive = demand running hotter than its
seasonal trend; negative = cooling. Comparable across subsectors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .data import sources


def _deseasonalized_growth(s: pd.Series) -> pd.Series:
    s = s.dropna()
    if len(s) < 10:
        return pd.Series(dtype=float)
    y = np.log(s.to_numpy())
    q = pd.DatetimeIndex(s.index).quarter
    dummies = np.column_stack([(q == k).astype(float) for k in (2, 3, 4)])
    x = np.column_stack([np.ones(len(y)), np.arange(len(y)), dummies])
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    return pd.Series(np.diff(y - dummies @ beta[2:]), index=s.index[1:])


def _temperature(s: pd.Series) -> dict:
    """Latest deseasonalized growth, z-scored vs history."""
    g = _deseasonalized_growth(s)
    if len(g) < 8:
        return {}
    z = float((g.iloc[-1] - g.mean()) / g.std(ddof=1))
    return {
        "as_of": str(g.index[-1].date()),
        "latest_growth": float(g.iloc[-1]),
        "z": z,
    }


def current_signals(force: bool = False) -> dict[str, dict]:
    """{signal_key: temperature} for every subsector signal."""
    nyc = sources.nyc_trips(force=force)
    out = {
        "nyc_uber": _temperature(nyc["UBER"]),
        "nyc_lyft": _temperature(nyc["LYFT"]),
        "tsa": _temperature(sources.tsa(force=force)),
        "macau": _temperature(sources.macau(force=force)),
    }
    return {k: v for k, v in out.items() if v}


if __name__ == "__main__":
    for key, t in current_signals().items():
        print(
            f"{key:10} z={t['z']:+.2f}  (latest qtr growth {t['latest_growth']:+.1%}, {t['as_of']})"
        )
