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
# YOUR FUNDAMENTAL VIEWS -- this is where your own research lives, and it is what
# ACTUALLY drives the book. Scale: -2 strong short .. 0 no view .. +2 strong long.
# The demand radar only SIZES these views (trims/adds); it can NEVER flip your
# direction. A name with no view here is idea-generation only, not a position.
# The alt-data informs the discretionary book -- it does not replace it.
# ---------------------------------------------------------------------------
THESES: dict[str, float] = {
    # Longs you believe in (conviction -2..+2 -- tune these to your real conviction).
    "UBER": 2.0,  # strong long: undervalued, ~$70 downside floor
    "CELH": 1.0,  # long: energy-drink growth (verify organic vs Alani Nu)
    "MNST": 1.0,  # long: energy-drink quality incumbent
    "DASH": 1.0,  # long: delivery
    "NCLH": 1.0,  # long: cruise
    # "MAR": -1.0,  # short thesis (overvalued) -- DEFERRED: can't short in the
    # beneficiary paper account (no borrow). Re-add once on a shortable account.
}

# Concentration caps (fraction of gross). No single name above MAX_NAME, no single
# subsector above MAX_SUBSECTOR -- so the book stays diversified once it has several
# views. Rule of thumb: name cap ~= 2-3x equal-weight; tighten as coverage grows.
# (With only one or two theses the caps can't bind and are relaxed -- the book says so.)
MAX_NAME = 0.10
MAX_SUBSECTOR = 0.30

# Hedge instrument. The ideal (equal-weight, no mega-cap distortion) wasn't
# executable: RSPD/RSPS and even RSP all got "not available to borrow" in the sim.
# Only the mega-ETFs borrow, so we use SPY -- a broad market-beta hedge. SPY is
# tech-heavy (~30%) but DIFFUSELY so (~7% Amazon), far less lopsided than XLY's ~37%
# in Amazon+Tesla. Tradeoff: hedges market beta, not the consumer sector. If SPY
# can't be borrowed either, BUY an inverse ETF (e.g. SH) instead -- no borrow needed.
HEDGE_DEFAULT = "SPY"
HEDGE_BY_SUBSECTOR: dict[str, str] = {}
HEDGE_TICKERS = ("SPY",)


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
}
