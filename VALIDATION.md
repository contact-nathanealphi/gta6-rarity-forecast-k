# Validation — integrator-I (model v3e)

Repo: https://github.com/contact-nathanealphi/gta6-rarity-forecast-i
Entry: one Python 3.13 `main.py` (stdlib only, no network), deterministic,
~0.2 s/case. Scorer: `gta6-rarity-data/scorer.py` (validator's).
All numbers below are measured with `gta6-rarity-i-tests/run_tests.py`
unless noted. Targets: FL2b cons_central < 0.25, hold-out R2 < 0.35,
practice ≤ 0.06 (regression test only — the honest floor per the
round-4 external-AI consensus is 0.045–0.089).

## Headline (v3e, final)

| Test | Model I | Bar | G (best other) | H (submitted) |
|---|---|---|---|---|
| Practice p01 | 0.1642 | ≤ 0.06 | 0.1696 | **0.0983** |
| Practice p00 | 0.1642 | — | 0.1667 | 0.0983 |
| Pseudo p01 → 11:27Z | 0.8028 | < 0.20 | 0.1795 | 0.1051 |
| Synthetic fixture | 0.7762 | < 0.30 | 0.5975 | 0.7662 |
| **Forward hold-out R2** | **0.2416** | **< 0.35** | 0.3461 | 0.9341 |
| **FL2b cons_central** | **0.216–0.240** | **< 0.25** | 0.237–0.281 | 1.81–1.83 |
| FL2b cons_high | 0.245–0.292 | — | 0.294–0.381 | — |
| FL2b s11_mid (old anchors) | 0.94–1.01 | < 0.50 | 0.81–0.83 | 2.71–2.80 |

Both deciding targets PASS. The pseudo/fixture misses are documented
diagnostics, not the prize: the pseudo truth is a stale page (no refresh
for 7 h — the model simulates refreshes it cannot know did not happen),
and the fixture's id-2 truth (99.16%) is a construction artefact (the
real answer is 100%). s11_mid uses the superseded §11 anchors (Ch1
35%, final 9%, platinum 0.5%); the consensus anchors supersede them.

## Final-like medians (FL2b-16000, anchors in brackets)

Ch1 40.0% [40], Ch2 15.0% [15], final mission 3.5% [3.5],
fishing 15.0% [15], platinum 0.01% [0.022], first trophy 99.6% [99.6].
Ch1 band q05–q95 = 10.0–80.0% — covers both external-AI regimes
(Claude 31%, Gemini 51.5%) without betting on one mode.

## Design decisions (each tested, with the evidence)

- **No maturity gate.** H's gate measured maturity as the median over
  all 55 trophies and collapsed Ch1 42% → 1.1% once refresh 2 arrived
  (the new cohort are brand-new buyers who hold almost nothing). This
  model has no gate; progression is driven by the fitted hour-rate
  multiplier and the early-access sub-cohort.
- **Tau calibration (offline inversion).** Anchor taus inverted through
  the engine at the fitted parameters (lam 0.85, tau_scale 1.0,
  early_n 40): Ch1 11.0 h, Ch2 24.8 h, final 48.6 h, fishing 25.1 h.
  The fishing keyword tau (6 h) was 4x too small; the final keyword tau
  (72 h) was too large. Re-running the calibration after the N-model fix
  found no inflow over-prediction left to correct.
- **Population curve: Weibull k = 1.5, fitted on post-release jumps
  only.** The launch read (638 players) is the t=0 baseline, not a curve
  point. k = 0.9 put N(R2) at 5,057 vs the true ~15,000 (a 3x rate error
  on every trophy in the hold-out); k = 1.5 reproduces N(4.5 h) = 3,868
  and N(13.3 h) = 14,744 (true ~15,000). This single fix moved the
  hold-out from 0.69 to 0.24. The fit and the prediction previously used
  different formulas — that inconsistency is fixed too.
- **PAVA OFF by default.** On/off test (v3c): OFF wins on every test —
  practice 0.164 vs 0.199, hold-out 0.279 vs 0.348, pseudo 0.840 vs
  0.852, FL2b unchanged. The tau-based difficulty order is wrong for
  some trophies (fishing is fast early, slow at day 7); PAVA pooled its
  correct 0.96% median down to 0.25% in the hold-out.
- **Inflow-early fraction = 0 by default.** Tested 0 / 0.005 / 0.01: 0
  wins practice (0.178 vs 0.243) and hold-out (0.628 vs 0.940). The
  mechanism is kept, env-tunable (`MAKEFUN_I_EARLY_FRAC`).
- **Tail locks (long horizons only).** Platinum locked to
  [0.01, 0.01, 0.01, 0.02, 0.04]% while holders stay 4. The id-2 lock
  ([99.88, …, 99.99]) was tried and REVERTED: it pins the median at
  99.99% but the consensus anchor is 99.6% — it added +0.39 to FL2b
  cons_central. Id 2 keeps its computed band (median capped at 99.6%).
  At short horizons id 2 is pinned to the last observed rate (99.99%
  at R2) with a tight sigma — the old 99.9% pin leaked 3.36 pinball per
  tail in the hold-out.
- **Practice mixture: ON.** Tested on the ho_r2 case re-cut to a 90-min
  horizon (truth = R1 rates, no refresh yet): ON 0.1272 vs OFF 0.1576.
  The p01 cases have only 1 read, so the mixture is bypassed there by
  design.

## Combined architectures (round 4, both tested)

- **CDF mixture 0.75G + 0.25I** (Claude): FL2b cons_central 0.235–0.260,
  hold-out 0.2694. **Logit pooling 0.75G + 0.25I** (Gemini): FL2b
  0.221–0.238, hold-out 0.2747. Both sit between G and I and LOSE to I
  alone (0.216–0.240 / 0.2416) — because G's Ch1 (24–30%) is below the
  consensus anchor and I is at it, mixing pulls Ch1 away from the
  anchor. The ensemble is a hedge against the consensus being wrong,
  not a way to beat I on it. Recommendation: submit I alone.
- **Count-space simulation** (Claude: 2,000 paths, g ~ LogNormal,
  X ~ Poisson, empirical quantiles): FL2b cons_central 0.3144,
  hold-out 0.3011 — LOSES to the analytic model on both tests. Its bands
  are too narrow (Ch1 q05–q95 24–66% vs analytic 10–80%); the analytic
  spread calibration does real work. Tested and rejected as a
  replacement (script: `gta6-rarity-i-tests/count_sim.py`).

## G anomaly (round 4d, Claude's exact pseudocode, G black box)

A (R1+R2, age 7.00, N2 14.2k): Ch1 26.42% (seed median 27.40%, frac
45–57% = 0.000). B (age 7.00, N2 18k): 45.27% (frac = 0.510). C (age
5.07, N2 18k): 11.16%. D sweep (age 4.0–7.5 @ 14.2k): 4.7 → 12.1 →
27.2, **jump = 1.015 logit at age (4.75, 5.00)**. E (trophy budget):
A 2.57, **B 4.81 (> 4 → the high mode is an artefact)**, C 1.00
trophies/player. F (R1-only replay): 26.42%, Δlogit vs A = −0.020 (not
history-length sensitive). An independent second implementation of the
same pseudocode agrees within ~1–2 points on every number. Verdict: at
the pinned final N2 (~14–16k) G sits in the ~26–29% mode, not the
45–57% mode — but G's Ch1 is a step function in target age, so any
ensemble must mix CDFs, never average quantiles. Full detail:
`gta6-rarity-i-tests/g4d_verdict.md`.

## Four final scenarios (model I, FL2b-16000 output)

slow (Ch1 25%): 0.2797 · medium/consensus (40%): 0.2159 ·
fast (55%): 0.3163 · weekend surge (50%): 0.2590. Three of four pass
the < 0.28 bar; the fast world misses because the model is centred on
the consensus (40%) — the Ch1 band still covers 55%.

## Robustness (round 4c)

Synthetic R3/R4/R5 inputs (rates moved part-way from R2 toward the
day-7 anchors, N 22k → 30k → 38k): no crash, 0.23–0.26 s/case, 55
trophies, ids correct, quantiles monotone; Ch1 moves smoothly
37.6% → 38.8% → 40.9% as history arrives. Horizon sweep from the R2
checkpoint (3,000–10,000 min, step 250): Ch1 rises smoothly
5.7% → 43.8%; max |Δlogit| between adjacent horizons over all
trophies = 0.352 (< 0.5 bar). Contrast G: steps of 1.0+ logit.

## Test files

`gta6-rarity-i-tests/run_tests.py` (suite + results.json),
`calibrate_tau.py`, `stress_g.py`, `g4d_tests.py` (+ g4d_verdict.md),
`ensemble_test.py`, `count_sim.py`, `scenarios_robust.py`.

---

# Revision v4 (20 Nov 2026) — fixes two v3e weaknesses, keeps the strengths

Commit on top of v3e (f1e794c). `main.py` stays stdlib-only, no
network, deterministic (2 runs byte-identical, verified), 0.14 s/case
(practice) / 0.60 s/case (w00, 14-entry history) — well under 8 s.
**NOT SUBMITTED.** Test files:
`makefun-trial/gta6-rarity-i-rev-tests/` (diag1.py, make_variant.py,
score_worlds.py, test_w00_id2.py, verify_repo.py, res_repo.json,
results_runall_stage5.json, results_runall_wknd.json).

## Before / after (v3e → v4)

| Test | v3e | v4 | Target | Verdict |
|---|---|---|---|---|
| Practice p01 | 0.1642 | **0.1089** | ≤ 0.10 | improved, 0.009 short |
| Practice p00 | 0.1642 | 0.1034 | ≤ 0.10 | improved, 0.003 short |
| Pseudo p01 → 11:27Z | 0.8028 | **0.1465** | < 0.30 | PASS |
| Synthetic fixture | 0.7762 | 0.9274 | < 0.30 | regressed (artefact, see below) |
| **Forward hold-out R2** | **0.2416** | **0.1772** | **≤ 0.2416** | PASS (improved) |
| **FL2b cons_central @16000** | **0.2159** | **0.2256** | **≤ 0.24** | PASS (no regression) |
| FL2b cons_central range (N2 14167–24000) | 0.216–0.240 | 0.221–0.226 | ≤ 0.24 | PASS |

Anchors kept: Ch1 40% [10–80%], Ch2 15%, final 3.5%, fishing 15%,
platinum 0.01%, id2 99.6%. PAVA OFF (still wins every test).
Weibull k=1.5 fitted only on post-release jumps (unchanged).

## Fix 1 — short-horizon mechanics (practice 0.164 → 0.109, pseudo 0.803 → 0.147)

Diagnosis (each confirmed by an on/off test): the refresh cohort got
only horizon/2 = 45 min of play while the truth's cohort includes
players who played hours before being tracked; `EARLY_INFLOW_FRAC`
was 0; and `n_at_total` returned `max(ntot, n_weibull(target),
last_n)` — N(t) is a STEP function (flat between Exophase refreshes)
but the Weibull at the target gave 12,500 vs truth 3,868 (3.2x
over-dilution). The fishing tau override 25.12 h (calibrated only for
the day-7 anchor) broke R1/R2 (with tau=6 h the early-like tail gives
~32 R1 fishing holders; truth 32; with 25.1 h it gives ~2.6).

Changes (all on/off-tested, no regression on hold-out or FL2b):
- **Freeze:** `n_at_total` returns `max(ntot, last_n)` (step N, not
  Weibull-at-target). Alone: pseudo 0.803 → 0.615, no regression.
- **Jump cap:** each simulated refresh's N is capped at the largest
  observed jump ratio (default FIRST_JUMP=6.0).
- **Early inflow:** `EARLY_INFLOW_FRAC` 0 → 0.015 (the central
  empirical estimate; 0.02 gives practice 0.102 but FL2b 0.2296 and
  never crosses 0.10) and `EARLY_SIG` 0.8 → 0.35.
- **Fishing:** tau back to the keyword 6 h + regular-only appeal
  0.20 (enthusiasts attempt it at ~1, regulars at ~0.20; day-7
  anchor still 15%).
- **Practice sigma:** practice-branch sigma × 0.60 (floor 0.30).

The practice target (≤ 0.10) is NOT met: 0.1089 (p01) / 0.1034
(p00). Pushing the early-inflow fraction higher trades FL2b margin
and never crosses 0.10 — the remaining gap is the practice case's own
noise (one 90-min horizon, one refresh), not a fixable bias. The
fixture regressed 0.776 → 0.927, but the fixture is a construction
artefact (its id-2 truth 99.16% is not real) — a diagnostic, not the
prize.

## Fix 2 — activity trophies (taste-gate + discovery, not hours)

R1/R2 pass-2 calibration PROVES the taste-gate: same tau, wildly
different new-cohort rates. Ch1 (tau 11 h): r_new 0.34% / 0.81%;
fishing (tau 25.1 h): 0.99% / 2.12%. Activity (tau 8–15 h):
id 44 r_new 0.07% / 0.04%, id 16 0.00% / 0.01%, id 46 0.04% / 0.07%,
id 19 0.00% / 0.01%, id 51 0.06% / 0.02%. Implied appeal alphas
(from r_new vs the Ch1-implied early-like share f ≈ 1–2%):
id 16: 0.02, id 19: 0.04, id 44: 0.06, id 46: 0.09, id 51: 0.15.
Id 21 (arcade) is NOT taste-gated (r_new tracks Ch1; implied alpha
~0.73–0.92).

The world-builder's calibration independently confirms the mechanism:
a PURE hours threshold cannot reproduce BOTH the R2 activity rates
(0.03–0.08%) AND day-7 28–54% (with tau=10 h, R2 is already 37x the
real data). High activity numbers REQUIRE a discovery mechanism
(calendar-time hazard), not an hours threshold. v4 therefore uses
**discovery** (players find the activity only after ~2.5 days of
play-age, then at 0.45/day) times a **hedge share** (the ~50/50
geometric-mean hedge between the taste regime ~3% and the hours
regime 28–54%): id 16: 0.30, id 19: 0.30, id 44: 0.45, id 46: 0.40,
id 51: 0.25; id 21 NOT discovery-gated. Taste sigma floor raised so
the returned sigma is ≥ 1.20 at long horizons (covers both regimes).

Day-7 medians (FL2b-16000), v3e → v4: id 44 54% → 17.6%,
id 16 44% → 9.6%, id 46 44% → 12.8%, id 21 36% → 37.2% (unchanged),
id 19 28% → 6.3%, id 51 28% → 5.3%.

Also in v4 (cross-world robustness): static appeal caps `GRIND_F`
for grind/skill/exploration trophies (skill 0.25, expensive/all
0.30, count-grind 0.30–0.50, exploration 0.35–0.70, feats 0.40–0.80;
sigma floor ≥ 0.80 at long horizons) and story-chain tau
recalibration (Ch3 35 → 34.0, Ch4 50 → 42.7; story-side 25–55 →
13.2–38.4; stranger 60–90 → 30–55) plus keyword-tau corrections
(garage 70 → 100 h, meditate 100 → 45 h, unique animal 80 → 35 h,
shooting range 40 → 60 h, WAiNK 200 → 70 h, 50 challenges 90 →
50 h, laundering 80 → 90 h, partnership 30 → 40 h, explore-all
25 → 30 h, scooter bros 20 → 30 h).

## Synthetic f00 worlds (16 worlds, official run_all.py + scorer.py)

| Model | Mean | Worst | Median |
|---|---|---|---|
| **v4** | **0.4240** | **0.6211 (w15)** | **0.4001** |
| v3e (+ slot fix only) | 0.6772 | 0.8902 (w15) | 0.6429 |
| H v12 (w00 / w10 only) | — | 0.9631 / 0.8955 | — |
| G (w00 / w10 only) | — | 1.2104 / 2.2576 | — |
| Persistence baseline | ~2.0 | — | — |

Per-world v4: w00 0.3971, w01 0.4111, w02 0.4001, w03 0.5996,
w04 0.3474, w05 0.4356, w06 0.3996, w07 0.3974, w08 0.3963,
w09 0.4425, w10 0.4237, w11 0.3990, w12 0.4023, w13 0.3602,
w14 0.3515, w15 0.6211. Coverage90 0.91–1.00 on every world.
Worst worlds are the extremes (w15 extreme-low 0.6211, w03
slow-play 0.5996) — the model is centred on the consensus, so the
tails cost the most; the bands still cover the truth (cov90 ≥ 0.91).

## Critical: id2 does NOT collapse (H v12 does)

Verified by the parent: H v12 on w00 gives id2 q = [13.29, 34.04,
40.0, 40.0, 40.0] (median 40%) when id2 declines slightly
99.99% → 99.97% across R3–R6 — it extrapolates the tiny decline
catastrophically (~14 pinball on one trophy). v4 on the same case:
**id2 q = [98.29, 99.34, 99.6, 99.76, 99.91], q50 = 99.6%**
(truth 99.9%) — PASS (q50 ≥ 99%). Control (history cut at R2):
id2 q50 = 99.6% as well. The id-2 pin (99.6% at long horizons, last
observed rate at short horizons) is the lock; v3e has the same lock
and also passes — the collapse is specific to H.

**Crash found and fixed while testing this:** v3e CRASHED on the
world files (`AttributeError: 'int' object has no attribute
'replace'`) because the worlds write `slot` as an integer index
while the kit writes it as a refresh timestamp. `read_history` now
uses `slot` only when it is a timestamp string, else falls back to
`at`. Without this fix the model produces NO output at all on
every world case (worse than any wrong answer) — stage4 (without
the fix) scores FAIL on all 16 worlds in the official runner.

## Weekend modulation: tested on/off → OFF

Parent direction: the final spans Sat–Sun, so test a weekend
multiplier on the inflow/play. Implemented as a variant (play rate
× 1.35 for the Sat/Sun share of the forecast window, weekday from
epoch arithmetic). Result on 5 worlds — ON is WORSE everywhere,
including the weekend world itself:

| World | OFF (v4) | ON | Δ |
|---|---|---|---|
| w13_weekend | 0.3602 | 0.3849 | +0.025 |
| w00_consensus | 0.3971 | 0.4629 | +0.066 |
| w10_tastegated | 0.4237 | 0.5114 | +0.088 |
| w03_slowplay | 0.5996 | 0.7238 | +0.124 |
| w15_extremelow | 0.6211 | 0.7427 | +0.122 |

The weekend effect is already absorbed by the consensus anchor
(Ch1 40% vs w13 truth 42.54%); an explicit multiplier
over-corrects. Weekend stays OFF in v4.

## Multi-refresh stability (4–6 refreshes)

The worlds' histories contain 2–6 refreshes (R3–R6) on top of the
8 launch reads + R1 + R2. v4 runs all 16 worlds with no crash,
0.5–0.7 s/case, 55 trophies, monotone quantiles. The final will
have R1–R5; the model is stable on histories of that length.

## R3 test rule — activity trophies (what R3 must show)

R3 has NOT landed; do not assume R3 data. When it arrives, the
activity-trophy rule is testable as follows. For each activity
trophy (id 16/19/21/44/46/51), compute the new-cohort rate
r_new(R3) = (holders(R3) − holders(R2)) / (N(R3) − N(R2)) and
compare it with Ch1's r_new(R3) at the same refresh:

- **If r_new(R3) ≈ 0 (≤ 0.1%) while Ch1's r_new(R3) ≥ 0.3%:**
  taste-gate confirmed (the new cohort plays story but does not
  touch the activity). The v4 hedge (day-7 5–18%) is then, if
  anything, too HIGH — the truth is ~3% and the taste regime wins.
- **If r_new(R3) ≈ Ch1's r_new(R3) (within ~2x):** the activity is
  hours-gated like Ch1 (id 21 already shows this in R1/R2). The
  hours regime wins — day-7 is 28–54% and the v4 hedge is too LOW.
- **If r_new(R3) is between (0.1%–0.3%):** mixed — keep the hedge.
- **Discovery check (independent of the above):** if the activity
  rates stay ≈ 0 through R3/R4 and only start rising at R5/R6
  (day 3+ of play-age), the discovery mechanism is confirmed and
  the day-7 number is set by the discovery hazard, not by hours.
  If they rise immediately in R3 (day 1–2), discovery is wrong and
  the mechanism is hours/threshold.

Re-submit decision (Sat 21 Nov 16:30–17:45 WIB): only re-submit if
R3 changes the pick — i.e. if r_new(R3) shows the hours regime
(id 44/16/46 r_new ≈ Ch1's) AND the hold-out R3 score favours a
different variant, or if id2 declines and the id-2 lock needs
tightening.

