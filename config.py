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
    # Hotels -- accommodation employment (PROVISIONAL proxy; the dedicated lodging
    # reader's RevPAR signal is the validated version to swap in). Modest trust.
    "MAR": ("hotels", "lodging", 0.45),
    "HLT": ("hotels", "lodging", 0.45),
    "H": ("hotels", "lodging", 0.45),
    # Beverages -- growth/functional and mega-cap staples are DIFFERENT comp groups,
    # so they get separate subsectors: the book never pairs a growth long vs a staple
    # short by accident, and the per-subsector cap treats each sleeve on its own.
    # No free demand reader yet -> sized on THESIS + VALUE only (catalyst defaults 0).
    "CELH": ("bev-growth", "none", 0.0),
    "MNST": ("bev-growth", "none", 0.0),
    "KO": ("bev-staples", "none", 0.0),
    "PEP": ("bev-staples", "none", 0.0),
    "KDP": ("bev-staples", "none", 0.0),
    # Delivery / cruise -- discretionary, no demand reader (thesis + value only)
    "DASH": ("delivery", "none", 0.0),
    "NCLH": ("cruise", "none", 0.0),
    # Fitness / e-commerce -- consumer discretionary, hedge with RSPD
    "LTH": ("fitness", "none", 0.0),
    "AMZN": ("ecommerce", "none", 0.0),
    # Tech sleeve -- OUTSIDE consumer; hedged vs equal-weight tech (RSPT). TSM is a
    # foreign filer (20-F / IFRS) so the value layer can't score it -> thesis-only.
    "MSFT": ("tech", "none", 0.0),
    "TSM": ("tech", "none", 0.0),
}

# Each subsector's signal series -> the names whose demand it reads.
SIGNAL_NAMES: dict[str, list[str]] = {
    "nyc_uber": ["UBER"],
    "nyc_lyft": ["LYFT"],
    "tsa": ["LUV", "JBLU", "ALK", "DAL", "AAL", "UAL"],
    "macau": ["LVS", "MLCO", "WYNN", "MGM"],
    "lodging": ["MAR", "HLT", "H"],
}

# ---------------------------------------------------------------------------
# YOUR FUNDAMENTAL VIEWS -- the book's actual positions. Scale: -2 strong short ..
# 0 no view .. +2 strong long. The demand radar only SIZES these (never flips them).
#
# PRIVACY: your real book is kept OUT of the public repo. Put your live positions in
# `theses_local.py` (gitignored); they override the empty default below. The public
# repo ships an empty book so your positions never appear on GitHub.
# ---------------------------------------------------------------------------
THESES: dict[str, float] = {}
try:
    from theses_local import THESES as _local_theses

    THESES = _local_theses  # private, gitignored override
except ImportError:
    pass

# Concentration caps (fraction of gross). No single name above MAX_NAME, no single
# subsector above MAX_SUBSECTOR -- so the book stays diversified once it has several
# views. Rule of thumb: name cap ~= 2-3x equal-weight; tighten as coverage grows.
# (With only one or two theses the caps can't bind and are relaxed -- the book says so.)
MAX_NAME = 0.20
MAX_SUBSECTOR = 0.30

# Dynamic sizing -- per-name overlays on the conviction weight (see book._dynamic_mults):
#  * vol scaling: size inversely to recent volatility (low-vol bigger, high-vol smaller)
#  * price bands: full weight near the floor, scaling to 0 (+ an alert) at the ceiling
#  * momentum gate: small until an uptrend confirms, then scale up
VOL_SCALING = True
# Price bands = your explicit value targets (buy toward the floor, trim toward the
# ceiling). Add a name here when you have a target. The book-wide value signal already
# does "buy cheap / trim expensive" everywhere; bands are for hard per-name levels.
PRICE_BANDS: dict[str, tuple[float, float]] = {"UBER": (70.0, 75.0)}
# Momentum gate = "minimal until an uptrend confirms" -- only for volatile names you
# want to scale INTO on confirmation (CELH). Don't gate names that are already extended.
MOMENTUM_GATED: set[str] = {"CELH"}

# Hedge: short an EQUAL-WEIGHT consumer index per sleeve, so there's no cap-weight
# mega-cap distortion (cap-weighted XLY is ~22% Amazon). Staples -> RSPS, the rest ->
# RSPD. On IBKR these are borrowable (the Schwab beneficiary sim couldn't lend them).
# If IBKR shows either as not-shortable, fall back to RSP (equal-weight S&P) or SPY.
HEDGE_DEFAULT = "RSPD"
# tech -> XLK (equal-weight RSPT wasn't borrowable; XLK is liquid + always shortable).
HEDGE_BY_SUBSECTOR = {"bev-growth": "RSPS", "bev-staples": "RSPS", "tech": "XLK"}
HEDGE_TICKERS = ("RSPD", "RSPS", "XLK")


def hedge_etf(subsector: str) -> str:
    return HEDGE_BY_SUBSECTOR.get(subsector, HEDGE_DEFAULT)


# SEC CIKs (for the XBRL revenue used by the valuation layer).
CIK: dict[str, int] = {
    "UBER": 1543151,
    "LYFT": 1759509,
    "LUV": 92380,
    "JBLU": 1158463,
    "ALK": 766421,
    "DAL": 27904,
    "AAL": 6201,
    "UAL": 100517,
    "LVS": 1300514,
    "MLCO": 1297996,
    "WYNN": 1174922,
    "MGM": 789570,
    "MAR": 1048286,
    "HLT": 1585689,
    "H": 1468174,
    "CELH": 1341766,
    "MNST": 865752,
    "KO": 21344,
    "PEP": 77476,
    "KDP": 1418135,
    "DASH": 1792789,
    "NCLH": 1513761,
    "LTH": 1869198,
    "AMZN": 1018724,
    "MSFT": 789019,
    "TSM": 1046179,  # foreign filer (20-F/IFRS) -- value layer won't resolve it
}
