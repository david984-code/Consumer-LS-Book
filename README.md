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
   views** in `config.THESES` (−2 strong short … +2 strong long). The demand
   radar only **resizes** each view (a confirming signal adds, a contradicting one
   trims) within ±50% — **it can never flip your direction.** Then beta-neutralize
   with an SPY hedge.

```
sized(name)  = thesis × (1 ± up to 50% from the demand catalyst)   # sign locked to thesis
weight(name) = sized / gross ;  + SPY hedge so net beta ≈ 0
```

So a deeply-undervalued high-conviction long like **UBER stays long** even when
its demand signal is soft — the soft quarter merely trims the position. The
earlier version wrongly *shorted* Uber on a soft demand reading; that was the bug
this design fixes.

## Example output (live, with UBER set to +2 strong long)

```
2) THE BOOK  (your THESES, sized by demand, beta-neutral)
  name   thesis  demand   sized  beta   weight
  UBER     +2.0   -0.24   +1.81  1.19  +100.0%   <- stays LONG; soft demand only trims +2.0 -> +1.81
    + SPY hedge -119% -> net beta +0.00
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
5. ⬜ **Valuation layer** — pull a cheap/expensive signal (EV/EBITDA, FCF yield vs
      history/peers) so the book has a systematic *value* anchor alongside your
      manual theses — the "other level of research".
6. ⬜ Per-subsector concentration caps; a macro context panel (informational only).
7. ⬜ Bootstrap inference on the long-minus-short spread vs a control benchmark.

## Part of a series

The four readers this book consumes:
[gig](https://github.com/david984-code/Consumer-Gig-Nowcast) ·
[airlines](https://github.com/david984-code/Airlines-Alt-Data-Nowcast) ·
[lodging](https://github.com/david984-code/hospitality-alt-data-dashboard) ·
[gaming](https://github.com/david984-code/Macau-Gaming-Nowcast).
