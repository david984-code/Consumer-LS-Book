# Consumer L/S Book

Ties the four free-data subsector readers (rideshare, airlines, lodging, gaming)
into **one consumer demand scorecard and a market-neutral long/short tilt.**

It is a **conviction / sizing input to a discretionary book — not an autopilot.**

## How it works (plainly) — two separate layers

**The alt-data informs the discretionary view; it does not replace it.** A short-
term demand signal is *not* a valuation. So the book is thesis-anchored:

1. **Demand radar** (idea generation). For each subsector, read today's demand
   temperature from its free signal — how hot/cold demand is running vs its own
   seasonal trend (a z-score). `conviction = temperature × trust`, where `trust`
   (0–1) is how much that signal has *earned*: TSA reads Southwest (≈0.9) but
   barely Delta (0.45, its intl flights are invisible to TSA); NYC reads Uber
   (0.9) not Lyft (0.2). This is a **watchlist**, not positions.
2. **The book** (positions). Direction and conviction come from **your fundamental
   views** in `config.THESES` (−2 strong short … +2 strong long). Two systematic
   signals only **resize** each view — never flip it (bounded to ±50%):
   - **demand** (the radar above) — a confirming reading adds, a contradicting trims;
   - **value** — z-score of each name's price-to-sales vs its own ~5y history (price
     from yfinance, revenue from SEC XBRL with Q4 = annual − 9-month). *Cheap*
     confirms a long, *expensive* confirms a short.

   Then beta-neutralize with an SPY hedge.

```
sized(name)  = thesis × (1 ± up to 50% from demand + value)   # sign locked to thesis
weight(name) = sized / gross ;  + SPY hedge so net beta ≈ 0
```

So a deeply-undervalued high-conviction long like **UBER stays long** even when its
demand signal is soft — and because the value signal reads it **cheap**, valuation
*adds* to the long and offsets the soft demand. The earlier version wrongly
*shorted* Uber on a soft demand reading; that was the bug this design fixes.

## Example output (live, with UBER set to +2 strong long)

```
2) THE BOOK  (your THESES, sized by demand + value, beta-neutral)
  name   thesis  demand   value   sized  beta   weight
  UBER     +2.0   -0.24   +0.48   +2.17  1.36  +100.0%   <- soft demand trims, but cheap -> value adds
    + SPY hedge -136% -> net beta +0.00
```

(Add your other names to `config.THESES` and they join the book.)

## Run

```bash
uv run python -m src.book      # 1) demand radar  2) your thesis-anchored book
```

## What it deliberately does NOT do

- **No macro overlay.** Regime/rates are read judgmentally, not wired into sizing.
- **No backtested alpha claim.** The readers showed free data nowcasts *the print*
  well but systematic pairs don't pay cleanly — so this informs a human's
  conviction, it doesn't trade itself.

## Roadmap

1. ✅ Demand radar across all four subsectors (rideshare, airlines, gaming, hotels).
2. ✅ **Beta-neutralized** — each name's β vs SPY + an SPY hedge so net beta ≈ 0,
      with a full risk panel (gross / net-$ / net-β / max).
3. ✅ Lodging wired (hotels MAR/HLT/H) via accommodation employment (provisional).
4. ✅ **Thesis-anchored** — positions come from your fundamental views; the demand
      signal only resizes them (±50%), never flips direction. (Fixes the old bug of
      shorting an undervalued long like UBER on a soft demand quarter.)
5. ✅ **Valuation layer** — a systematic cheap/expensive signal: z-score each name's
      price-to-sales vs its own ~5y history (price from yfinance, revenue from SEC
      XBRL, Q4 = annual − 9-month). Resizes theses alongside demand — cheap confirms
      a long, expensive confirms a short — the "other level of research".
6. ✅ **Concentration caps** — water-fill so no name exceeds 25% and no subsector
      exceeds 40% of gross, redistributing to names with room. With too few views to
      diversify, the caps relax (and say so) rather than forcing the book to cash.
7. ✅ **Macro context panel** — a display-only regime read (yield curve, HY credit
      spread, unemployment, consumer sentiment, financial conditions from FRED),
      graded risk-on/off and averaged into a label. By design it **never touches
      sizing** — the systematic macro overlay was tested and disproven; macro is
      read judgmentally only.
8. ⬜ Bootstrap inference on the long-minus-short spread vs a control benchmark.

## Part of a series

The four readers this book consumes:
[gig](https://github.com/david984-code/Consumer-Gig-Nowcast) ·
[airlines](https://github.com/david984-code/Airlines-Alt-Data-Nowcast) ·
[lodging](https://github.com/david984-code/hospitality-alt-data-dashboard) ·
[gaming](https://github.com/david984-code/Macau-Gaming-Nowcast).
