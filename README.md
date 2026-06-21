# Consumer L/S Book

Ties the four free-data subsector readers (rideshare, airlines, lodging, gaming)
into **one consumer demand scorecard and a market-neutral long/short tilt.**

It is a **conviction / sizing input to a discretionary book — not an autopilot.**

## How it works (plainly)

1. For each subsector, read **today's demand temperature** from its free-data
   signal — how hot or cold real-world demand is running versus its own seasonal
   trend (a z-score: +2 = unusually hot, −2 = unusually cold).
2. Put every consumer stock on a **scorecard** with that temperature.
3. **Trust each signal only as much as it has earned.** A `trust` weight (0–1)
   encodes the readers' validated fit: TSA reads Southwest (≈1.0) but barely
   Delta (≈0.45, its international flights are invisible to TSA); NYC trips read
   Uber (0.9) but not Lyft (0.2, that bridge came up null).
4. `conviction = temperature × trust`. Demean across the universe → **long the
   relatively hottest names, short the coldest**, net-zero by construction.
   Low-trust names get small positions automatically.

```
conviction(name) = demand_temperature(subsector) × trust(name)
weight(name)     = (conviction − universe mean) / gross   # sum ≈ 0, dollar-neutral
```

## Example output (live)

```
name  subsector   demand z  trust  conviction   weight
LUV   airlines        +0.17   0.90        0.15   +11.6%   <- airlines running hot,
JBLU  airlines        +0.17   0.90        0.15   +11.6%      Southwest/JetBlue read best
DAL   airlines        +0.17   0.45        0.08    +5.4%   <- smaller (TSA misses intl)
LVS   casinos         -0.04   0.90       -0.04    -5.4%
UBER  rideshare       -0.26   0.90       -0.24   -23.2%   <- rideshare cooling, high trust
LONG : LUV, JBLU, ALK, DAL, AAL, UAL    SHORT: casinos, LYFT, UBER
```

## Run

```bash
uv run python -m src.signals   # the four live demand temperatures
uv run python -m src.book      # the scorecard + proposed L/S tilt
```

## What it deliberately does NOT do

- **No macro overlay.** Regime/rates are read judgmentally, not wired into sizing.
- **No backtested alpha claim.** The readers showed free data nowcasts *the print*
  well but systematic pairs don't pay cleanly — so this informs a human's
  conviction, it doesn't trade itself.

## Roadmap

1. ✅ Live scorecard + L/S tilt from 3 readers (rideshare, airlines, casinos).
2. ✅ **Beta-neutralized** — compute each name's β vs SPY, add an SPY hedge so the
      book's net beta ≈ 0 (it was secretly +0.17, long high-beta airlines → a hidden
      market bet; a −17% SPY hedge fixes it). Full risk panel (gross / net-$ / net-β / max).
3. ⬜ Wire in the **lodging** signal (the 4th reader) for hotels (MAR/HLT/H).
4. ⬜ Per-subsector concentration caps; a macro context panel (informational only).
5. ⬜ Bootstrap inference on the long-minus-short spread vs a control benchmark.

## Part of a series

The four readers this book consumes:
[gig](https://github.com/david984-code/Consumer-Gig-Nowcast) ·
[airlines](https://github.com/david984-code/Airlines-Alt-Data-Nowcast) ·
[lodging](https://github.com/david984-code/hospitality-alt-data-dashboard) ·
[gaming](https://github.com/david984-code/Macau-Gaming-Nowcast).
