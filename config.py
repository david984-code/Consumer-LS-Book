"""The Consumer L/S book: turn the four subsector readers' live signals into a
single demand scorecard and a market-neutral long/short tilt.

This is a CONVICTION / sizing tool that informs a discretionary book -- it does not
trade by itself. Two ideas drive it:
  * Each name gets a current "demand temperature" from its subsector's free-data
    signal (how hot/cold real-world demand is running vs its own seasonal trend).
  * We trust that signal only as much as it has earned -- the per-name `trust`
    weight encodes the coverage-matching finding (TSA reads Southwest, not Delta's
    international flights; NYC trips read Uber Mobility, not Lyft).
"""

from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
OUTPUT_DIR = ROOT_DIR / "outputs"
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
CACHE_TTL_HOURS = 24.0

# name -> (subsector, signal source, trust 0..1 from the readers' validated fit).
# trust is high where the free signal directly measures the name's activity.
UNIVERSE: dict[str, tuple[str, str, float]] = {
    # Rideshare -- NYC TLC dispatched trips (Uber Mobility nowcast validated; Lyft null)
    "UBER": ("rideshare", "nyc_uber", 0.90),
    "LYFT": ("rideshare", "nyc_lyft", 0.20),
    # Airlines -- TSA throughput (domestic carriers strong; intl-mix diluted)
    "LUV": ("airlines", "tsa", 0.90),
    "JBLU": ("airlines", "tsa", 0.90),
    "ALK": ("airlines", "tsa", 0.80),
    "DAL": ("airlines", "tsa", 0.45),
    "AAL": ("airlines", "tsa", 0.45),
    "UAL": ("airlines", "tsa", 0.45),
    # Casinos -- Macau GGR (Macau-pure strong; US-heavy diluted)
    "LVS": ("casinos", "macau", 0.90),
    "MLCO": ("casinos", "macau", 0.70),
    "WYNN": ("casinos", "macau", 0.60),
    "MGM": ("casinos", "macau", 0.40),
}

# Each subsector's signal series -> the names whose demand it reads.
SIGNAL_NAMES: dict[str, list[str]] = {
    "nyc_uber": ["UBER"],
    "nyc_lyft": ["LYFT"],
    "tsa": ["LUV", "JBLU", "ALK", "DAL", "AAL", "UAL"],
    "macau": ["LVS", "MLCO", "WYNN", "MGM"],
}
