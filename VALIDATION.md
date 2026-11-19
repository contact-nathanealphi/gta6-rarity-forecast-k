# Validation — model K (on the I v4 lineage)

Repo: https://github.com/contact-nathanealphi/gta6-rarity-forecast-k
Entry: one Python 3.13 `main.py` (stdlib only, no network), deterministic,
~0.15–0.25 s/case. Scorer: `gta6-rarity-data/scorer.py` (validator's).
Suite runner: `gta6-rarity-k-tests/run_suite.py` (practice, pseudo,
fixture, hold-out R2, FL2b scenarios, id2 decline, 16 worlds).
**NOT SUBMITTED.** Parent submits.

## Verdict: K PASSES — it beats I v4 on the deciding final tests

| Test | I v4 | K | Bar | Verdict |
|---|---|---|---|---|
| Practice p01 | 0.1089 | **0.1029** | (no bar; honest aim ~0.095) | improved |
| Practice p00 | 0.1034 | **0.1029** | — | improved |
| Pseudo p01 → 11:27Z | 0.1465 | 0.1513 | < 0.30 | slightly worse (see §4) |
| Synthetic fixture | 0.9274 | 0.9034 | (artefact, discounted) | improved |
| **Forward hold-out R2** | **0.1772** | **0.1757** | **≤ 0.19** | **PASS, improved** |
| **FL2b cons_central** | **0.2256** | **0.2242** | **≤ 0.24** | **PASS, improved** |
| FL2b cons_high | 0.2515 | 0.2529 | — | slightly worse (+0.0014) |
| **16 worlds mean** | **0.4240** | **0.4139** | **≤ 0.45** | **PASS, improved** |
| 16 worlds worst | 0.6211 (w15) | 0.6105 (w15) | — | improved |
| Worlds won vs I v4 | — | 14 / 16 | — | — |
| id2 decline (4 tests) | q50 99.6 | q50 99.6 | ≥ 99% | PASS |
| Determinism | yes | yes (p01 + hold-out, 2 runs byte-identical) | yes | PASS |
| Runtime | 0.14–0.24 s | 0.14–0.25 s | ≤ 8 s | PASS |
| Format | valid | valid | valid | PASS |

FL2b medians (anchors in brackets): Ch1 41.39% [40], Ch2 16.28% [15],
final 3.76% [3.5], fishing 15.26% [15], platinum 0.01% [0.022],
id2 99.6% [99.6]. Budget 4.53 trophies/player (bar < 5).

Practice medians that moved toward truth: Ch1 0.32% → 0.51%
(truth 0.49%); hold-out Ch1 0.49% → 0.60% (truth 0.73%),
fishing 1.56% → 1.84% (truth 1.89%).

## What changed (one mechanism only)

**Launch-day play-rate multiplier (BINGE).** In `cohort_holders`, the
regular cohorts' play-rate medians are multiplied by
`1 + (BINGE-1) * exp(-age_d / BINGE_TAU_D)` with BINGE = 2.0,
BINGE_TAU_D = 2.0 days — i.e. a cohort plays ~2x its steady rate on
arrival, fading to the steady rate over ~2 days. The day cap still
applies. Nothing else changed: taus, appeals, discovery, tail locks,
spreads, the runtime fit grid, and the mixture branch are I v4
untouched (diff vs I v4: +5/−2 lines).

Why it is the right mechanism: the steady daily rates (1.65 / 7 h/day)
cannot produce the holders the recorded refreshes already show. The
new cohort at refresh 2 gained +84 Chapter-1 holders where the steady
model gives ~+39; fishing's R1→R2 inflow is the same story. The
holders must come from launch-week buyers playing far more in their
first hours than their long-run average — the multiplier separates
"launch-week intensity" from the "steady-state rate", and the runtime
fit re-balances (lam, tau_scale, early_n) around it (on p01 the fit
moves to lam 0.7 / tau_scale 1.0 / early_n 40).

How it was tuned: grid over B ∈ {1.5, 2, 2.5, 3} × decay ∈ {0.5, 1, 2,
3} days, scored on the FULL suite (not practice alone). B=2 / tau=2d
is the peak: stronger or longer over-progresses young cohorts
(hold-out 0.197–0.206, fails the bar; id 9 "Break the Bank" is the
first victim) and a faster decay loses the practice gain.

## What was tried and REJECTED (each measured on the full suite)

- **Widening the banked-hours tail (EARLY_SIG 0.35 → 0.55/0.7/0.9,
  or a separate wider inflow tail):** practice improves at 0.9
  (0.0985) but hold-out collapses (0.20–0.36). A single lognormal tail
  cannot match the new-cohort pattern: it floods mid-tau trophies
  (id 9, id 48, id 45) that the truth barely moves. Rejected.
- **Per-trophy tau corrections (id 35 "discover 100 vehicles" 18h →
  8h; id 37 25h → 12h):** practice improves (0.1023) but hold-out
  worsens (0.180–0.182) — a tau fitted on refresh 1 does not transfer
  to refresh 2. Rejected.
- **Count-space / Poisson-median holder rounding:** the clean
  short-branch-only version is neutral (p01 0.1096 vs 0.1089); the
  global version's apparent practice gain (0.1041) came from a broken
  fit, not the rounding. Rejected (and the first implementation had a
  cap bug that collapsed FL2b Ch1 to 0.73% — caught by the suite,
  fixed, re-measured, still neutral).
- **Discovery delay 2.5d → 0/1.0d:** neutral on every test (0.1083 /
  0.1780). Rejected — keep v4's validated delay.
- **Anchor-weight reduction (flat 0.5, or adaptive 1/(1+n_pairs)):**
  hold-out 0.1772 → 0.1917 (fails the bar). The single refresh pair is
  too noisy to let the fit chase it. Rejected.
- **Sigma tightening (any): NOT tried and NOT allowed.** The parallel
  diagnosis proved it wrecks the final case (+25% H, +34% I on
  final-like worlds) and the practice target < 0.0569 is not honestly
  reachable (see below). Sigma is byte-identical to I v4.

## The practice target, honestly

Per the parallel diagnosis (`gta6-rarity-k-tests/practice-diagnosis.md`,
read in full before building): practice p01 < 0.0569 (top-20 cutoff)
is NOT honestly achievable with transfer to the final case — it needs
the refresh size g within ±10% of 6.06 AND the true new-cohort rates
AND sigma ≤ 0.28 AND near-certainty a refresh lands, none of which
follows from the 8 flat reads at the p01 checkpoint. The honest
expectation for lever 1 (better dilution median) was p01 ~0.095; K
reaches **0.1029** — about halfway from I v4's 0.1089, and the remaining
gap is the median error on a handful of mid-tier trophies (id 35, id 37,
id 8) whose true difficulty the tau table mis-ranks. No refresh-1
answer value is encoded in this file: no per-trophy new-cohort rate,
no 6.06 jump (the jump prior stays the round 6.0 inherited from I v4),
no sigma change. K's practice gain comes from the same mechanism that
improves the hold-out and the worlds, not from practice-specific
tuning.

## Remaining risks

1. **The gains are small and partly fit-driven.** Hold-out −0.0015,
   FL2b −0.0014, worlds −0.0101. On p01 part of the gain is a
   near-tie flip in the fit grid (two grid points score 2.3882 vs
   2.3886); on the real final case the tie could flip the other way.
   The worlds gain is broad-based (14/16 improve) but concentrated in
   the consensus world w00 (−0.0354) and the slow worlds; the
   refresh-fast/slow worlds w07/w08 worsen slightly (+0.017/+0.018).
2. **Pseudo regressed** (0.1465 → 0.1513): the binge raises
   young-cohort progression, which overshoots a stale page (no refresh
   for 7h). If the final history has a long flat stretch before the
   checkpoint, the same overshoot applies to the first simulated
   refresh — bounded, since the fit re-balances.
3. **FL2b cons_high regressed** (+0.0014): in the fast (Ch1 55%) world
   K sits slightly further from the anchor than I v4 (Ch1 41.4% vs
   40.9%). If the real day-7 Ch1 lands at the Gemini end (~51%), K
   pays a little more than I v4.
4. **Binge is a two-parameter fit on a small suite.** B and the decay
   were selected on 19 test numbers; the mechanism is structural
   (launch-week intensity is real), but the exact values (2.0, 2.0d)
   could be re-tuned if R3 lands before the Saturday submit window —
   re-run the suite with R3 in the hold-out first.
5. **id 9 "Break the Bank" is the canary:** it is the first trophy to
   over-predict when the binge is too strong (hold-out loss 1.16–1.31
   at B ≥ 2.5). If R3 shows id 9 flat again, consider capping the
   binge for story-side trophies — not implemented, needs R3 evidence.

## Test files

`gta6-rarity-k-tests/run_suite.py` (suite runner),
`grid_binge20t20_worlds.json` (K full suite),
`baseline_i4_worlds.json` (I v4 full suite, same runner),
`decompose.py` / `decompose2.py` (per-trophy practice + hold-out),
`instrument_p01.py` / `instrument_ho.py` / `instrument_fit.py`
(mechanism evidence), `make_variant*.py` + `variants/` (all rejected
variants, kept for audit).
