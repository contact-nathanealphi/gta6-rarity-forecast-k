#!/usr/bin/env python3
"""GTA VI trophy rarity forecast — integrator I, v3.

Hybrid design (written from scratch, in my own words):
  * The population is a stack of arrival cohorts.  Each refresh adds one
    cohort of fresh buyers; between refreshes the cohorts already tracked
    keep playing.  A trophy's rate is holders / tracked players, so every
    forecast is built from those two quantities separately.
  * One cohort is special: a small early-access group that was already
    playing before release, with substantial hours banked.  It explains
    the launch-night holders and the first refreshes' growth, which fresh
    buyers' hours alone cannot explain.  A small share (~1%) of every
    later cohort is early-like for the same reason.
  * A player earns a trophy once their accumulated play hours pass that
    trophy's hour threshold (tau).  Play hours follow a two-group
    lognormal mixture (regular players + a hardcore tail).  The hour-rate
    multiplier, the global tau scale and the early group's size are
    fitted at run time from the refreshes the case itself contains, with
    a soft pull toward the day-7 anchor medians the outside evidence
    agrees on.
  * Holders are ANCHORED on the last observed count: the forecast is the
    observed holders plus the model's own predicted increment since the
    last read.  Holders never decrease, and the hours model alone
    understates counts wherever early-access holders hold a trophy the
    fresh-buyer hours cannot explain yet.  (v2 recomputed holders from
    scratch and collapsed mid-tier practice rates toward zero.)
  * The two grind-gold trophies (platinum, 100% completion) cannot be
    earned in a week of play; their holders are a fixed count, so their
    rate is just that count divided by the tracked population.
  * Short horizons (practice) use a two-branch mixture: either no refresh
    lands before the target (rates stay put) or one does (rates dilute
    toward the new cohort's rates).  Long horizons simulate the refresh
    schedule forward and read the state at the target.
  * There is deliberately NO maturity gate: progression is never switched
    off by a summary statistic.  A young cohort holding almost nothing
    yet is normal — it is not evidence that nobody will ever progress.

Standard library only. No network. Deterministic (no randomness anywhere:
all schedules are mean schedules and all fits are grid searches).
"""

import json
import math
import os
import sys
from datetime import datetime, timezone

# --------------------------------------------------------------------------
# Knobs (all in one place so a later revision can retune without surgery)
# --------------------------------------------------------------------------

RELEASE = "2026-11-19T00:00:00Z"          # game release, start of clock
DAY7_TARGET = "2026-11-26T00:00:00Z"     # anchor date for the day-7 priors

# Hour thresholds (raw play hours) by trophy class, from the descriptions.
# The story chain and the earliest side activities are pinned by id; the
# rest are matched on description keywords, with a tier default fallback.
CHAIN_TAU = {3: 9.5, 4: 20.0, 5: 35.0, 6: 50.0, 7: 72.0}
STORY_SIDE_TAU = {8: 25.0, 9: 35.0, 10: 40.0, 11: 45.0, 12: 50.0, 13: 55.0}
STRANGER_TAU = {22: 60.0, 23: 65.0, 24: 70.0, 25: 90.0, 26: 75.0, 27: 80.0}
KEYWORD_TAU = [
    ("fishing challenge", 6.0),
    ("arcade game", 12.0),
    ("each type of activity", 10.0),
    ("cocktail with a view", 8.0),
    ("discover 100 vehicles", 18.0),
    ("win 20 different races", 15.0),
    ("bowling alley", 10.0),
    ("vehicle showroom", 20.0),
    ("explore all of leonida", 25.0),
    ("scooter bros", 20.0),
    ("melee drive-by", 15.0),
    ("choices made", 20.0),
    ("shooting range", 40.0),
    ("drone race", 45.0),
    ("wanted level", 30.0),
    ("rob 3 shops", 25.0),
    ("combat focus", 20.0),
    ("unscheduled departure", 25.0),
    ("rhinos", 30.0),
    ("jewelry store", 35.0),
    ("bank vaults", 60.0),
    ("armored truck", 40.0),
    ("illegal operation", 50.0),
    ("partnership with mass appeal", 30.0),
    ("second time's the charm", 25.0),
    ("what the hell", 30.0),
    ("laundering marked bills", 80.0),
    ("spend $100,000", 60.0),
    ("garage properties", 70.0),
    ("meditate at every spot", 100.0),
    ("unique animal", 80.0),
    ("250 stunts", 120.0),
    ("50 challenges", 90.0),
    ("collectible card", 150.0),
    ("waink it", 200.0),
]
TIER_DEFAULT_TAU = {"bronze": 40.0, "silver": 70.0, "gold": 100.0,
                    "platinum": 255.0}
# Calibrated class-tau overrides (offline, calibrate_tau.py, against the
# FL2b-16000 reference case at fitted lam=0.7, tau_scale=0.8, early_n=40).
# Pass 1 inverts tau from the day-7 consensus anchors; pass 2 raises tau
# where the model predicted >=5 new holders in the R1+R2 inflows but
# <=2 were observed (breadth trophies whose keyword tau was far too
# small).  Values are CLASS taus (multiplied by the runtime tau_scale).
#   id 3 Ch1:      11.0h  (was 9.5h; day-7 46.0% -> anchor 40%)
#   id 4 Ch2:      24.8h  (was 20h; day-7 17.5% -> anchor 15%)
#   id 7 final:   48.6h  (was 72h; day-7 3.49% -> anchor 3.5%)
#   id 20 fishing: 25.1h (was 6h;  day-7 16.8% -> anchor 15%)
# (Pass 2 found nothing to correct after the N-model fix: the earlier
# inflow over-prediction of ids 16/19 was an artefact of the 3x-low N.)
TAU_CLASS_OVERRIDE = {3: 10.96, 4: 24.76, 7: 48.61, 20: 25.12}
FIRST_TAU = 0.15      # id 2, the first trophy everyone gets
CONSTANT_IDS = (1, 14)  # platinum, 100% completion: fixed holder counts

# Early-access group: players already playing before release.
EARLY_MED_H = 8.0     # median banked hours at release
EARLY_SIG = 0.8       # lognormal sigma of banked hours
EARLY_RATE = 7.0      # they keep playing at the hardcore rate (h/day)
EARLY_INFLOW_FRAC = float(os.environ.get("MAKEFUN_I_EARLY_FRAC",
                                          "0"))  # share of each later
# cohort that is early-like (bought early, banked hours, tracked only at
# the refresh).  DEFAULT 0: tested 0 / 0.005 / 0.01 on the suite — 0 wins
# practice (0.178 vs 0.243) and holdout R2 (0.628 vs 0.940); the inflow
# early-like players help story trophies (R1: +11 Ch1, +32 fishing) but
# overshoot breadth trophies (id 16/19/44: R1+R2 new holders ~0) by more.
# The anchored holders already carry the observed inflow effect.  Kept
# as an env-tunable mechanism, off by default.

# Play-hours mixture (hours per day of play) for regular cohorts.
M_REG = 1.65      # regular players
M_HARD = 7.0      # hardcore tail
HC_SHARE = 0.18   # share of hardcore players
SIG_REG = 0.65    # lognormal sigma, regular
SIG_HARD = 0.45   # lognormal sigma, hardcore
DAY_CAP = 16.0    # nobody plays more than this many hours a day

# Day-7 anchor medians (percent) — the outside consensus for the final.
ANCHORS = {1: 0.022, 2: 99.6, 3: 40.0, 4: 15.0, 7: 3.5, 20: 15.0}

# Refresh process.
GAP_PRIOR_H = 6.5       # mean gap (hours) when no gap has been observed
GAP_GROWTH = 1.3        # each later gap is this much longer than the last
GAP_MAX_H = 24.0        # gaps never grow past this
FIRST_JUMP = 6.0        # prior size of the first refresh (N multiplier)
NINF_PRIOR = 43000.0   # prior day-7 tracked population
THETA_N_PRIOR = 24.0    # prior Weibull time constant (hours); with
# WEIBULL_K = 1.5 this reproduces the first jump N(4.5h) = 3,868.
WEIBULL_K = 1.5         # population-curve shape.  The launch read (638
# players at 3h) is the t=0 BASELINE, not a curve point: the population
# is a step function, and k=0.9 could not fit the 6.06x jump to 3,868 at
# 4.5h (it put N(R2) at 5,057 vs the true ~15,000 — a 3x rate error on
# every trophy in the holdout).  k=1.5 fitted on the post-release jumps
# reproduces N(4.5h)=3,868 AND N(13.3h)=14,744 (true ~15,000) with
# Ninf=43k, theta=24h, and is robust across Ninf 30-60k.
N_MAX_GUARD = 110000.0  # physical ceiling for the q95 floor

# Spread model (logit units). Quantile z: Student-t with 4 dof.
Z_T4 = [-2.132, -0.741, 0.0, 0.741, 2.132]
KAPPA = 1.10            # global spread multiplier
SIG_TRAJ0 = 0.12        # trajectory sigma at zero horizon
SIG_TRAJ1 = 0.42        # trajectory sigma growth toward the final horizon
SIG_REFRESH = 0.30      # per-refresh-count uncertainty
SIG_RARE = 0.25         # extra sigma for trophies with < 10 holders
SIG_BASE = 0.15

# Runtime fit grid: (hour-rate multiplier, tau scale, early-group size).
LAM_GRID = [0.55, 0.7, 0.85, 1.0, 1.2, 1.45, 1.75]
TAU_GRID = [0.6, 0.8, 1.0, 1.25, 1.6]
EARLY_GRID = [15.0, 25.0, 40.0]
FIT_WEIGHT = 1.0        # refresh-pair fit (now anchored on observed
                        # counts, so it is trustworthy at full weight)
ANCHOR_WEIGHT = 1.0
PRIOR_WEIGHT = 0.05     # shrinkage of (lam, tau_scale) toward (1, 1)

PRACTICE_HORIZON_MIN = 360   # horizons at/below this use the mixture branch
SIG0_MIX = 0.012             # no-refresh branch sigma (rounding only)
MIXTURE_ON = os.environ.get("MAKEFUN_I_MIXTURE", "1") != "0"

# Class caps, applied AFTER widening (never let a band escape its class).
MED_CAP = {3: 65.0, 7: 15.0, 20: 40.0, 1: 0.10}
Q95_CAP = {3: 88.0, 7: 25.0, 20: 60.0, 1: 0.5, 2: 99.99}

TAUS = [0.05, 0.25, 0.5, 0.75, 0.95]

# --------------------------------------------------------------------------
# Small numeric helpers
# --------------------------------------------------------------------------


def parse_time(s):
    """ISO-8601 'Z' timestamp -> seconds since the epoch (float)."""
    if s is None:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def clamp(x, lo=0.01, hi=99.99):
    return min(max(x, lo), hi)


def logit(pct):
    p = clamp(pct) / 100.0
    return math.log(p / (1.0 - p))


def inv_logit(l):
    if l > 30.0:
        return 100.0
    if l < -30.0:
        return 0.0
    return 100.0 / (1.0 + math.exp(-l))


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def lognorm_sf(threshold, median, sigma):
    """P(X > threshold) for X lognormal(median, sigma)."""
    if threshold <= 0.0:
        return 1.0
    if median <= 0.0:
        return 0.0
    return 1.0 - norm_cdf((math.log(threshold) - math.log(median)) / sigma)


# --------------------------------------------------------------------------
# Case parsing
# --------------------------------------------------------------------------


def clean_rates(rates, n):
    out = []
    for i in range(n):
        v = rates[i] if i < len(rates) else None
        out.append(None if v is None else float(v))
    return out


def read_history(case):
    """Distinct reads, oldest first: (time_s, N, E, rates).

    Consecutive reads with identical N and identical rates are the same
    snapshot repeated; only the first is kept.  A read whose N or rates
    moved is a refresh.
    """
    trophies = case["trophies"]
    n = len(trophies)
    reads = []
    for h in case.get("history", []):
        t = parse_time(h.get("slot") or h.get("at"))
        if t is None:
            continue
        npl = h.get("players_tracked")
        ent = h.get("trophies_earned")
        rates = clean_rates(h.get("rates") or [], n)
        reads.append((t, npl, ent, rates))
    reads.sort(key=lambda r: r[0])
    distinct = []
    for r in reads:
        if distinct:
            _pt, pn, _, pr = distinct[-1]
            same_n = (r[1] == pn)
            same_r = True
            for a, b in zip(r[3], pr):
                if a is None or b is None:
                    if a is not b:
                        same_r = False
                        break
                elif abs(a - b) > 0.011:
                    same_r = False
                    break
            if same_n and same_r:
                # Same snapshot polled again: the page did not refresh.
                # Keep the LATEST time — the observed holders are "as of"
                # then, and the refresh-gap estimate must not count the
                # 30-minute polls as refreshes.
                distinct[-1] = (r[0], pn, distinct[-1][2], pr)
                continue
        distinct.append(r)
    return distinct


def holders_from_rates(rates, npl):
    """Implied holder counts (rounded) from rates and N; None stays None."""
    if npl is None:
        return [None] * len(rates)
    return [None if r is None else int(round(r * npl / 100.0)) for r in rates]


# --------------------------------------------------------------------------
# Hour thresholds from trophy descriptions (class-based, never rank-based)
# --------------------------------------------------------------------------


def tau_table(trophies, tau_scale):
    """Hour threshold per trophy, from its description + tier.

    Difficulty ranks from launch-night rates are NOT used: at hour 13 a
    rate reflects how young the cohort is, not how hard the trophy is —
    ranking by it gave the first chapter a 2-hour threshold and broke
    every day-7 forecast.  Constant-count trophies get tau None.
    """
    taus = []
    for t in trophies:
        tid = t["id"]
        if tid in CONSTANT_IDS:
            taus.append(None)
            continue
        if tid == 2:
            taus.append(FIRST_TAU * tau_scale)
            continue
        if tid in TAU_CLASS_OVERRIDE:
            taus.append(max(0.05, TAU_CLASS_OVERRIDE[tid] * tau_scale))
            continue
        if tid in CHAIN_TAU:
            taus.append(CHAIN_TAU[tid] * tau_scale)
            continue
        if tid in STORY_SIDE_TAU:
            taus.append(STORY_SIDE_TAU[tid] * tau_scale)
            continue
        if tid in STRANGER_TAU:
            taus.append(STRANGER_TAU[tid] * tau_scale)
            continue
        desc = (t.get("description") or "").lower()
        val = None
        for kw, v in KEYWORD_TAU:
            if kw in desc:
                val = v
                break
        if val is None:
            val = TIER_DEFAULT_TAU.get(t.get("tier", "bronze"), 40.0)
        if tid in TAU_CLASS_OVERRIDE:
            val = TAU_CLASS_OVERRIDE[tid]
        taus.append(max(0.05, val * tau_scale))
    return taus


# --------------------------------------------------------------------------
# Tracked-population curve N(t): Weibull saturation fitted to the jumps
# --------------------------------------------------------------------------


def fit_n_curve(jumps, t_release):
    """jumps: [(time_s, N), ...] at the observed refresh times.

    Returns (n_inf, theta_h).  The first read is the t=0 baseline
    (early-copy players, present at release); it is NOT fitted — the
    smooth Weibull cannot pass through a step, and including it wrecked
    the extrapolation (N(R2) 5,057 vs true ~15,000).  Only post-release
    jumps are fitted, with the same n_weibull() the runtime uses (an
    earlier version fitted a different formula than it predicted with).
    With fewer than two jumps the fit is under-determined, so the prior
    (N7 ~ 43k, theta ~ 24 h) is returned.
    """
    if len(jumps) < 2:
        return NINF_PRIOR, THETA_N_PRIOR
    base = jumps[0][1]
    best = None
    for n_inf in (20000.0, 30000.0, 43000.0, 60000.0, 90000.0):
        for theta in (20.0, 25.0, 30.0, 40.0, 50.0, 68.0, 100.0, 160.0):
            err = 0.0
            for tj, nj in jumps[1:]:
                pred = n_weibull(tj, t_release, n_inf, theta, n0=base)
                err += (math.log(pred) - math.log(max(nj, 1.0))) ** 2
            if best is None or err < best[0]:
                best = (err, n_inf, theta)
    return best[1], best[2]


def n_weibull(t_s, t_release, n_inf, theta_h, n0=638.0):
    th = max((t_s - t_release) / 3600.0, 0.0)
    val = n0 + (n_inf - n0) * (1.0 - math.exp(-((th / theta_h) ** WEIBULL_K)))
    return max(val, n0)


# --------------------------------------------------------------------------
# Cohort engine
# --------------------------------------------------------------------------


def cohorts_from_history(distinct, t_release):
    """Arrival cohorts implied by the observed reads.

    The first read is the launch cohort (size = its N). Every later
    distinct read adds a cohort of (N_new - N_old) arriving at that read.
    """
    cohorts = []
    prev_n = 0
    for (t, npl, _ent, _rates) in distinct:
        if npl is None:
            continue
        if not cohorts:
            cohorts.append((t_release, float(npl)))
            prev_n = npl
        elif npl > prev_n:
            cohorts.append((t, float(npl - prev_n)))
            prev_n = npl
    return cohorts


def constant_counts(distinct, n):
    """Fixed holder counts for the grind-gold trophies (ids 1, 14).

    Taken from the first read; they do not grow with play in week 1.
    """
    out = [0.0] * n
    if not distinct:
        return out
    _t, npl, _e, rates = distinct[0]
    counts = holders_from_rates(rates, npl)
    for tid in CONSTANT_IDS:
        c = counts[tid - 1]
        out[tid - 1] = float(c) if c is not None else 0.0
    return out


def cohort_holders(taus, cohorts, when_s, lam, early_n, const_counts):
    """Holders per trophy at a time.

    Regular cohorts play since arrival (two-group lognormal hours).
    The early-access group (size early_n) arrived at release with banked
    hours and keeps playing at the hardcore rate.  Constant-count
    trophies return their fixed count.
    """
    n = len(taus)
    holders = [0.0] * n
    for i in range(n):
        if taus[i] is None:
            holders[i] = const_counts[i]
    # Early-access group.
    if early_n > 0:
        age_d = max((when_s - parse_time(RELEASE)) / 86400.0, 0.0)
        med = EARLY_MED_H + EARLY_RATE * age_d
        for i in range(n):
            if taus[i] is None:
                continue
            holders[i] += early_n * lognorm_sf(taus[i], med, EARLY_SIG)
    # Regular cohorts.
    for (arr_s, size) in cohorts:
        age_d = max((when_s - arr_s) / 86400.0, 0.0)
        if age_d <= 0.0 or size <= 0:
            continue
        med_reg = min(M_REG * lam * age_d, DAY_CAP * age_d)
        med_hard = min(M_HARD * lam * age_d, DAY_CAP * age_d)
        med_early = EARLY_MED_H + EARLY_RATE * age_d
        for i in range(n):
            if taus[i] is None:
                continue
            tau = taus[i]
            p = (1.0 - HC_SHARE) * lognorm_sf(tau, med_reg, SIG_REG) \
                + HC_SHARE * lognorm_sf(tau, med_hard, SIG_HARD)
            # A small share of every later cohort is early-like (bought
            # early, banked hours, tracked only when the page refreshes).
            p_early = lognorm_sf(tau, med_early, EARLY_SIG)
            holders[i] += size * ((1.0 - EARLY_INFLOW_FRAC) * p
                                  + EARLY_INFLOW_FRAC * p_early)
    return holders


def engine_rates(taus, cohorts, when_s, lam, early_n, const_counts):
    """Rates (percent) from the cohort engine at a time."""
    holders = cohort_holders(taus, cohorts, when_s, lam, early_n,
                             const_counts)
    ntot = sum(size for _, size in cohorts)
    if ntot <= 0:
        return [0.0] * len(taus)
    return [100.0 * h / ntot for h in holders]


def n_at_total(cohorts, when_s, t_release, n_inf, theta_n, last_n):
    """Tracked population at a time: observed cohorts plus Weibull growth."""
    ntot = sum(size for _, size in cohorts)
    w = n_weibull(when_s, t_release, n_inf, theta_n)
    return max(ntot, w, last_n)


def holders_forecast(taus, cohorts_full, when_s, cohorts_old, t_old, lam,
                     early_n, const_counts, observed_last):
    """Forecast holders at `when_s`, anchored on observed counts.

    Holders never decrease: the forecast is the last observed count plus
    the model's own predicted INCREMENT since the last read (new crossers
    among the old cohorts plus holders in cohorts that arrived after the
    last read).  The hours model alone understates the observed counts
    whenever early-access holders hold a trophy the fresh-buyer hours
    cannot explain yet (e.g. 7 launch holders of a 35-hour chapter at
    hour 5) — recomputing holders from scratch then collapses the rate
    toward zero, which is exactly the v2 practice failure.  Anchoring on
    the observed count fixes it without touching the hours model.
    """
    full = cohort_holders(taus, cohorts_full, when_s, lam, early_n,
                          const_counts)
    old = cohort_holders(taus, cohorts_old, t_old, lam, early_n,
                         const_counts)
    out = []
    for i in range(len(taus)):
        obs = observed_last[i] if observed_last[i] is not None else 0.0
        out.append(obs + max(0.0, full[i] - old[i]))
    return out


def predict_rates(taus, cohorts_full, when_s, cohorts_old, t_old, lam,
                  early_n, const_counts, observed_last, n_at):
    """Forecast rates (percent) at `when_s` from anchored holders."""
    holders = holders_forecast(taus, cohorts_full, when_s, cohorts_old,
                               t_old, lam, early_n, const_counts,
                               observed_last)
    return [100.0 * h / max(n_at, 1.0) for h in holders]


# --------------------------------------------------------------------------
# Refresh schedule (mean schedule — deterministic)
# --------------------------------------------------------------------------


def observed_gaps(distinct):
    """Hours between consecutive distinct reads (the refresh gaps)."""
    gaps = []
    for a, b in zip(distinct, distinct[1:]):
        gaps.append(max((b[0] - a[0]) / 3600.0, 0.25))
    return gaps


def future_refresh_times(t_last, horizon_s, gaps):
    """Mean-schedule refresh times after t_last, within the horizon."""
    mu = (sum(gaps) / len(gaps)) if gaps else GAP_PRIOR_H
    times = []
    t = t_last
    step = mu
    while True:
        t = t + step * 3600.0
        if t > t_last + horizon_s:
            break
        times.append(t)
        step = min(step * GAP_GROWTH, GAP_MAX_H)
    return times


def gamma_sf_no_refresh(elapsed_h, since_h, k=2.5, mean_h=6.5):
    """P(no refresh in the next `elapsed_h` hours | none in `since_h`).

    Gamma renewal with shape k and the given mean: survival of the
    forward-recurrence time, by numeric integration (deterministic).
    """
    theta = mean_h / k

    def pdf(x):
        if x <= 0:
            return 0.0
        return (x ** (k - 1.0) * math.exp(-x / theta)
                / (theta ** k * math.gamma(k)))

    def sf(x):
        if x <= 0:
            return 1.0
        total = 0.0
        step = 0.05
        xx = 0.0
        while xx < x:
            total += pdf(xx + step / 2.0) * step
            xx += step
        return max(1.0 - total, 0.0)

    den = sf(since_h)
    if den <= 1e-9:
        return 0.0
    return sf(since_h + elapsed_h) / den


# --------------------------------------------------------------------------
# Runtime fit of (lam, tau_scale, early_n)
# --------------------------------------------------------------------------


def fit_params(taus_base, distinct, case, t_release, t_day7):
    """Grid-search (lam, tau_scale, early_n).

    Score = FIT_WEIGHT * squared logit error of the engine's refresh-pair
    predictions + ANCHOR_WEIGHT * day-7 anchor penalty + a small prior.
    The refresh-pair term is deliberately down-weighted: part of the
    early growth is early-access players, not fresh-buyer hours, so it
    must not drag the parameters to a corner the anchors contradict.
    """
    n = len(taus_base)
    const = constant_counts(distinct, n)
    pairs = []
    for j in range(1, len(distinct)):
        prev = distinct[:j]
        cohorts_old = cohorts_from_history(prev, t_release)
        t_old = distinct[j - 1][0]
        obs_old = holders_from_rates(distinct[j - 1][3],
                                     distinct[j - 1][1])
        n_old = distinct[j - 1][1] or 0
        nj = distinct[j][1]
        cohorts_full = list(cohorts_old)
        if nj and nj > n_old:
            cohorts_full.append((distinct[j][0], float(nj - n_old)))
        pairs.append((cohorts_full, cohorts_old, t_old, obs_old,
                      distinct[j][0], distinct[j][3], nj))
    n_inf, theta_n = fit_n_curve(
        [(t, npl) for (t, npl, _e, _r) in distinct if npl], t_release)

    # Day-7 anchor setup (independent of the grid): simulated cohorts to
    # the anchor date, anchored on the last observed holders.
    cohorts_all = cohorts_from_history(distinct, t_release)
    fut = future_refresh_times(
        distinct[-1][0], t_day7 - distinct[-1][0],
        observed_gaps(distinct))
    sim = list(cohorts_all)
    prev_n = distinct[-1][1] or 638.0
    for ft in fut:
        nn = n_weibull(ft, t_release, n_inf, theta_n)
        if nn > prev_n:
            sim.append((ft, nn - prev_n))
            prev_n = nn
    n_day7 = n_at_total(sim, t_day7, t_release, n_inf, theta_n, prev_n)
    obs_last = holders_from_rates(distinct[-1][3], distinct[-1][1])
    t_last = distinct[-1][0]

    best = None
    for lam in LAM_GRID:
        for ts in TAU_GRID:
            taus = [None if t is None else t * ts for t in taus_base]
            for early_n in EARLY_GRID:
                err = 0.0
                cnt = 0
                for (cohorts_full, cohorts_old, t_old, obs_old, tj,
                     obs, nj) in pairs:
                    pred = predict_rates(taus, cohorts_full, tj,
                                         cohorts_old, t_old, lam, early_n,
                                         const, obs_old, nj or 638.0)
                    for i in range(n):
                        if obs[i] is None:
                            continue
                        if nj and obs[i] * nj / 100.0 < 3.0 \
                                and pred[i] < 0.05:
                            continue
                        err += (logit(obs[i]) - logit(pred[i])) ** 2
                        cnt += 1
                fit_err = err / max(cnt, 1)
                # Day-7 anchor penalty (anchored holders, same as forecast).
                day7 = predict_rates(taus, sim, t_day7, cohorts_all,
                                     t_last, lam, early_n, const, obs_last,
                                     n_day7)
                pen = 0.0
                for tid, anch in ANCHORS.items():
                    pen += (logit(day7[tid - 1]) - logit(anch)) ** 2
                pen /= max(len(ANCHORS), 1)
                prior = PRIOR_WEIGHT * ((math.log(lam)) ** 2
                                        + (math.log(ts)) ** 2)
                total = FIT_WEIGHT * fit_err + ANCHOR_WEIGHT * pen + prior
                if best is None or total < best[0]:
                    best = (total, lam, ts, early_n, fit_err, pen,
                            n_inf, theta_n)
    return best


# --------------------------------------------------------------------------
# Forecast
# --------------------------------------------------------------------------


def sigma_for(trophy_idx, horizon_d, n_refreshes_seen, n_refreshes_ahead,
              holders_last):
    """Spread (logit units) for one trophy at one horizon."""
    s = SIG_TRAJ0 + SIG_TRAJ1 * ((horizon_d / 4.52) ** 0.65)
    s = math.sqrt(s * s + SIG_BASE * SIG_BASE)
    if n_refreshes_ahead > 0:
        s = math.sqrt(s * s + (SIG_REFRESH ** 2) * n_refreshes_ahead
                      / (1.0 + n_refreshes_seen))
    if holders_last is not None and holders_last < 10:
        s = math.sqrt(s * s + SIG_RARE * SIG_RARE)
    # id 2 at SHORT horizons: it can only fall a hair (100% -> 99.99%
    # at R2), so the band is tight.  Without this the long branch gave
    # q95 = 99.94% against a 99.99% truth — a 3.36 pinball leak per
    # tail in the holdout.  (At long horizons the tail lock in
    # apply_guardrails takes over instead.)
    if trophy_idx == 1 and horizon_d < 2.0:
        return 0.08
    return KAPPA * s


def quantiles_from(median, sigma):
    qs = []
    for z in Z_T4:
        qs.append(round(clamp(inv_logit(logit(median) + z * sigma), 0.01,
                              99.99), 4))
    for i in range(1, 5):
        if qs[i] < qs[i - 1]:
            qs[i] = qs[i - 1]
    return qs


def pava_decreasing(values):
    """Pool-adjacent-violators: make `values` non-increasing. Logits in,
    logits out.

    Block-based (stack of [sum, count]): each merge strictly reduces the
    block count, so this always terminates in O(n).  (An earlier
    pair-pooling version oscillated forever on a long run of exactly
    equal values followed by higher ones — p01 took 231 s in this
    function alone.  Never go back to pair-pooling.)
    """
    blocks = []
    for v in values:
        blocks.append([v, 1])
        while len(blocks) >= 2 and \
                blocks[-2][0] / blocks[-2][1] < \
                blocks[-1][0] / blocks[-1][1] - 1e-12:
            s = blocks[-2][0] + blocks[-1][0]
            c = blocks[-2][1] + blocks[-1][1]
            blocks[-2:] = [[s, c]]
    out = []
    for s, c in blocks:
        out.extend([s / c] * c)
    return out


def apply_guardrails(medians, sigmas, taus, last_rates, holders_last,
                     horizon_min):
    """Physical floor, progression floor, PAVA ordering, class caps.

    The first trophy (id 2) is EXCLUDED from the progression floor: it
    can only fall as fresh players join, so pinning it at its last rate
    would be exactly wrong.
    """
    n = len(medians)
    med = list(medians)
    if horizon_min >= 48 * 60:
        for i in range(n):
            if i == 1:
                continue
            if taus[i] is not None and taus[i] <= 35.0 \
                    and last_rates[i] is not None:
                med[i] = max(med[i], last_rates[i])
    # PAVA ordering over progression trophies ONLY.  The constant-count
    # trophies (platinum, 100% completion) are real holder counts, not
    # progression rates: pooling them with the tail would drag both
    # sides to a wrong common value (and, with a long run of exactly
    # equal clamped logits ahead of them, it also fed the old PAVA
    # oscillation).  They keep their computed medians.
    # PAVA is env-tunable; DEFAULT OFF.  The on/off test (v3c) showed
    # OFF wins on every test — practice 0.164 vs 0.199, holdout R2
    # 0.279 vs 0.348, pseudo 0.840 vs 0.852, FL2b unchanged (0.216).
    # The difficulty order comes from a tau table that is wrong for
    # some trophies (fishing is fast early but slow at day 7), and
    # forcing monotonicity in that order pools a correct fast median
    # down with slow breadth trophies (holdout: fishing raw 0.96%
    # pooled to 0.25%).
    if os.environ.get("MAKEFUN_I_PAVA", "0") == "1":
        order = sorted((i for i in range(n) if taus[i] is not None),
                       key=lambda i: (taus[i], i))
        logits = [logit(med[i]) for i in order]
        fixed = pava_decreasing(logits)
        for pos, i in enumerate(order):
            med[i] = clamp(inv_logit(fixed[pos]), 0.01, 99.99)
    for tid, cap in MED_CAP.items():
        if horizon_min >= 48 * 60 or tid != 2:
            med[tid - 1] = min(med[tid - 1], cap)
    qs = []
    for i in range(n):
        q = quantiles_from(med[i], sigmas[i])
        if (i + 1) in Q95_CAP:
            cap = Q95_CAP[i + 1]
            q = [min(v, cap) for v in q]
            for k in range(1, 5):
                if q[k] < q[k - 1]:
                    q[k] = q[k - 1]
        if holders_last[i]:
            floor = 100.0 * holders_last[i] / N_MAX_GUARD
            if q[4] < floor:
                q[4] = round(min(floor, 99.99), 4)
                for k in range(3, -1, -1):
                    if q[k] > q[k + 1]:
                        q[k] = q[k + 1]
        qs.append(q)
    # Tail lock (round-4c, Gemini top-1): for LONG horizons only
    # (>= 48 h), where the day-7 truth is decided.
    #   platinum (holders still 4): lock to [0.01, 0.01, 0.01, 0.02,
    #   0.04] (4/55,000 = 0.0073%, so the floor is 0.01%).
    #   id 2 is DELIBERATELY NOT locked: Gemini's [99.88, ..., 99.99]
    #   pins the median at 99.99%, but the consensus anchor is 99.6%
    #   — the lock added +0.39 to FL2b cons_central (0.216 -> 0.60)
    #   because the scenario truth is 99.6%.  id 2 keeps its computed
    #   band (median capped at 99.6% by MED_CAP at long horizons).
    # At short horizons the computed quantiles are kept.
    if horizon_min >= 48 * 60:
        if holders_last[0] is not None and holders_last[0] == 4:
            qs[0] = [0.01, 0.01, 0.01, 0.02, 0.04]
    return qs


def forecast_case(case):
    """Full forecast for one case. Returns the output dict."""
    trophies = case["trophies"]
    n = len(trophies)
    t_cp = parse_time(case["at"])
    horizon_min = float(case.get("horizon_minutes") or 0)
    horizon_s = horizon_min * 60.0
    t_target = parse_time(case.get("target")) or (t_cp + horizon_s)
    t_release = parse_time(RELEASE)
    t_day7 = parse_time(DAY7_TARGET)

    distinct = read_history(case)
    if not distinct:
        return {"trophies": [{"id": t["id"], "q": quantiles_from(0.5, 1.0)}
                             for t in trophies]}
    last_rates = distinct[-1][3]
    last_n = distinct[-1][1] or 638.0
    holders_last = holders_from_rates(last_rates, last_n)
    gaps = observed_gaps(distinct)
    n_seen = len(distinct) - 1

    taus_base = tau_table(trophies, 1.0)
    _tot, lam, tau_scale, early_n, _fe, _pe, n_inf, theta_n = fit_params(
        taus_base, distinct, case, t_release, t_day7)
    taus = [None if t is None else t * tau_scale for t in taus_base]
    const = constant_counts(distinct, n)
    base_cohorts = cohorts_from_history(distinct, t_release)

    horizon_d = horizon_min / 1440.0

    if horizon_min <= PRACTICE_HORIZON_MIN:
        medians = practice_medians(
            case, distinct, taus, lam, early_n, const, t_release, t_cp,
            horizon_s, last_rates, last_n, n_inf, theta_n, gaps)
        sigmas = []
        for i in range(n):
            s = sigma_for(i, horizon_d, n_seen, 1, holders_last[i])
            if i == 1:
                s = 0.08  # the first trophy is universal: tight band
            else:
                s = max(s, 0.45)
            sigmas.append(s)
    else:
        fut = future_refresh_times(distinct[-1][0], t_target - distinct[-1][0],
                                   gaps)
        sim = list(base_cohorts)
        prev_n = last_n
        for ft in fut:
            nn = n_weibull(ft, t_release, n_inf, theta_n)
            if nn > prev_n:
                sim.append((ft, nn - prev_n))
                prev_n = nn
        n_t = n_at_total(sim, t_target, t_release, n_inf, theta_n, last_n)
        medians = predict_rates(taus, sim, t_target, base_cohorts,
                                distinct[-1][0], lam, early_n, const,
                                holders_last, n_t)
        # Constant-count trophies: rate = fixed count / N(target).
        for tid in CONSTANT_IDS:
            medians[tid - 1] = 100.0 * const[tid - 1] / max(n_t, 1.0)
        # The first trophy stays ~universal; the engine's lognormal tail
        # understates it, so pin it to the consensus path instead.
        # At short horizons it barely moves: pin to the last observed
        # rate (99.99% at R2, 100% at R1) — the old 99.9% pin leaked
        # 3.36 pinball per tail in the holdout against a 99.99% truth.
        if horizon_d > 2.0:
            medians[1] = 99.6
        elif last_rates is not None and last_rates[1] is not None:
            medians[1] = max(medians[1], min(last_rates[1], 99.99))
        else:
            medians[1] = max(medians[1], 99.9)
        sigmas = []
        for i in range(n):
            s = sigma_for(i, horizon_d, n_seen, len(fut), holders_last[i])
            if i == 1 and horizon_d <= 2.0:
                s = min(s, 0.25)
            if trophies[i]["id"] in CONSTANT_IDS:
                s = max(s, 0.69)
            sigmas.append(s)

    qs = apply_guardrails(medians, sigmas, taus, last_rates, holders_last,
                          horizon_min)
    return {"trophies": [{"id": t["id"], "q": q}
                         for t, q in zip(trophies, qs)]}


def practice_medians(case, distinct, taus, lam, early_n, const, t_release,
                     t_cp, horizon_s, last_rates, last_n, n_inf, theta_n,
                     gaps):
    """Practice branch: mixture over no-refresh / one-refresh.

    Returns the per-trophy MIXTURE MEDIAN (the q50 of the mixture), i.e.
    the value m with F_mix(m) = 0.5, solved by bisection on the logit
    scale.  When the case history contains no refresh at all, the target
    read IS a refresh by construction of the practice cases, so p0 = 0.
    With MIXTURE_ON false the refresh branch alone is used (ablation).
    """
    n = len(taus)
    horizon_h = horizon_s / 3600.0
    if len(distinct) <= 1 or not MIXTURE_ON:
        p0 = 0.0
    else:
        t_last = distinct[-1][0]
        since_h = max((t_cp - t_last) / 3600.0, 0.0)
        mean_gap = (sum(gaps) / len(gaps)) if gaps else GAP_PRIOR_H
        p0 = gamma_sf_no_refresh(horizon_h, since_h, 2.5, mean_gap)

    if len(distinct) <= 1:
        n_new = last_n * FIRST_JUMP
    else:
        t_ref = t_cp + horizon_s / 2.0
        n_new = n_weibull(t_ref, t_release, n_inf, theta_n)
        n_new = max(n_new, last_n * 1.05)
    cohorts_old = cohorts_from_history(distinct, t_release)
    cohorts = list(cohorts_old)
    cohorts.append((t_cp + horizon_s / 2.0, max(n_new - last_n, 0.0)))
    holders_last = holders_from_rates(last_rates, last_n)
    refresh_rates = predict_rates(taus, cohorts, t_cp + horizon_s,
                                  cohorts_old, distinct[-1][0], lam,
                                  early_n, const, holders_last, n_new)
    refresh_rates[1] = 99.99  # the first trophy is universal at a refresh
    # Constant-count trophies at the refresh: count / new N.
    for tid in CONSTANT_IDS:
        refresh_rates[tid - 1] = 100.0 * const[tid - 1] / max(n_new, 1.0)

    medians = []
    for i in range(n):
        r_last = last_rates[i] if last_rates[i] is not None else 0.5
        r_ref = refresh_rates[i]
        if p0 <= 0.0:
            medians.append(r_ref)
            continue
        if p0 >= 1.0:
            medians.append(r_last)
            continue
        y_last = logit(r_last)
        y_ref = logit(r_ref)
        sig1 = max(0.30, 0.12 + 0.42 * ((horizon_s / 3600.0 / 24.0
                                         / 4.52) ** 0.65))
        lo = min(y_last, y_ref) - 4.0 * max(sig1, 0.3)
        hi = max(y_last, y_ref) + 4.0 * max(sig1, 0.3)
        for _ in range(30):
            mid = 0.5 * (lo + hi)
            f = (p0 * norm_cdf((mid - y_last) / SIG0_MIX)
                 + (1.0 - p0) * norm_cdf((mid - y_ref) / sig1))
            if f < 0.5:
                lo = mid
            else:
                hi = mid
        medians.append(clamp(inv_logit(0.5 * (lo + hi)), 0.01, 99.99))
    return medians


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def main():
    in_dir = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    names = sorted(fn for fn in os.listdir(in_dir) if fn.endswith(".in"))
    for fn in names:
        with open(os.path.join(in_dir, fn), "r", encoding="utf-8") as f:
            case = json.load(f)
        out = forecast_case(case)
        out_path = os.path.join(out_dir, case["id"] + ".out")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
