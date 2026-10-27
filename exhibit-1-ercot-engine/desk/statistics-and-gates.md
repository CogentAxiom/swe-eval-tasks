# Deep dive: the statistics and the gates

Every model in the engine is a hypothesis until a test it can fail says otherwise. This page lists the estimators that
produce the engine's numbers, the tests that decide whether a number may be used, and the gates that promote or demote a
component, each with the parameters the code uses. It sits under every chapter of the [desk tour](README.md); the
solvers and the bid math are in the [exhibit README](../README.md#under-the-hood-solvers-pipelines-and-invariants).
Figures are from the engine's artifacts in late October 2026. The math is the code's math; the code stays private.

## The evidence ladder

Every number carries the rung it earned:

1. **External oracle.** Realized day-ahead settlement, and ERCOT's own settlement reports.
2. **Falsification.** A walk-forward test the component can fail, against the incumbent or a naive baseline.
3. **Invariants.** Identities that must hold: put-call parity, the sign of the congestion identity, the calendar.
4. **Same-author re-derivation.** In the engine's words, "tautological — not verification". It never counts.

## Estimators: how each number is made

| Estimator | Where | What it does |
|---|---|---|
| Constraint-space value | S12, S16, S12e | `path_value = −Σ_c [SF(sink,c) − SF(source,c)] · E[shadow price(c)]`, the expected shadow price being how often a family binds times how hard. 1,967 constraint families stand in for 1.2 million node pairs |
| Hierarchical severity baseline | `severity.py` | `esp = w · mean(same calendar month) + (1 − w) · mean(all months)`, with `w = n / (n + K)` written on every row as a column. Months since ERCOT's real-time co-optimization are weighted up. The rare-basis rule averages a family over every month, binding or not, so a family that bound once in three years is not priced as if it binds every month. K and the era weight are levers the governor tunes |
| Monotone calibration | S08 | An isotonic map from composed value to realized settlement, per time-of-use block: it fixes the scale without disturbing the rank. Conformal residual bands (P05, P95) carry the distribution sizing needs |
| Quantile forecasts | S08b, S12f | LightGBM quantile models (P05, P25, P50, P75, P95) for each node's day-ahead basis, trained only on months strictly before each validation month, with a conformal coverage check on held-out months. A path's calibrated value is the difference of its two nodes' medians |
| Scenario algebra | S16, S12g | `m_r = 1 + Σ_e p_e (mult_e − 1)` per region and `value = Σ_r contrib_r · m_r`. Every live what-if re-prices through that dot product, and its residual against full recomputation is regression-checked at exactly zero |
| Clearing distribution | S09b, S13 | `P(clear | b) = w · F_path(b) + (1 − w) · F_family(b)` with `w = n_path / (n_path + 6)`, and the bid `b* = argmax_b P(C ≤ b) · (V − E[C | C ≤ b])` ([details](../README.md#s09-to-s13-the-bid-as-a-decision-under-a-clearing-distribution)) |
| Option value | S08c, S13 | `E[max(0, X + δ)]` on the hourly spread distribution, re-centred to the month's forecast level, with an exact equal-count quantile-grid estimator ([details](../README.md#s08c-options-on-the-hourly-positive-part-re-centred-exactly)) |
| Hidden-load forecast | S70b | A family of damped-trend forecasts of weather-normalized load growth by zone (window, horizon and damping are its parameters). At each origin the method is chosen by nested walk-forward selection on errors that were knowable then. P10, P50 and P90 come from empirical standardized errors. ERCOT's Batch Zero large-load cohorts enter as hard monthly totals, weighted by a probability of clearing ERCOT's verification and spread by a slip kernel and a ramp |
| Variance decomposition | S21 | Sequential η²: season, then time of use, then fuel mix, then the residual. Fuel mix comes last on purpose, so its share is a floor |

## Tests: what a number must survive

| Test | Where | The rule |
|---|---|---|
| Walk-forward skill | S49, Kronos lanes | `skill = 1 − MAE / MAE_naive ≥ 0.10` on three 14-day walk-forward folds, per corridor and time-of-use block. The naive forecast is the same weekday's mean over the trailing four weeks. An engine that fails stays on screen with its failing score and emits nothing |
| Lead-by-lead scoring | S49 | Every corridor engine is also scored at each lead of the forward run against two baselines, climatology and persistence |
| Brier skill | S57, S60, S97 | A conditioned probability must beat flat climatology by Brier score. For a climate cell that means 74 to 75 years of hindcasts, region by region and month by month. For the sub-seasonal outbreak model it means a skill of at least 0.10 over 29 winters |
| False-discovery control | macro scan, S57, S50 | Benjamini–Hochberg across every cell tested together. The 75-year macro scan ran 2,304 tests and kept 48 survivors that also held their sign with \|r\| ≥ 0.2 in both halves of the record, against about 3 expected by chance |
| Block bootstrap | S57 | Trends in extremes (hot tail, cold tail, intra-month variance, mean) are tested against a fixed 1951–1980 baseline, with year-block bootstrap p-values that respect autocorrelation, then FDR-controlled across cells |
| Split-half stability | S57, S68, S46d | A relationship must hold with the same sign in both halves of its record. An elasticity whose halves disagree is refused |
| Beta-Binomial shrinkage | S58, S58b, S40, S59 | Discovery screens rank on probability, not expected value. P(month pays ≥ entry) is shrunk toward the pool (κ = 2) and reported with a 90% interval, and the award model uses κ = 5. One Uri month cannot make a path look reliable |
| Placebo and sign tests | S51d, S51e | A pre-registered gate. A feature set must beat the incumbent in enough months by a binomial sign test, and its mean lift must clear the 95th percentile of a placebo null built by permuting the feature across paths within each month |
| Event studies | S36, S56 | Falsification by event: for 10 nuclear derations, the plant node's basis moved the expected way 8 times, but only 1 cleared two standard deviations, so the effect stays descriptive |
| Invariants | S12b, S01c, S16 | Put-call parity within an auction (at least 99% of pairs within $0.01, or the clearing data is declared corrupt); the congestion-identity sign; all 60 months of the TOU calendar against ERCOT's workbooks; the scenario dot product against full recomputation |
| Settlement oracle | S31 | Per-holder P&L reconciles to ERCOT's settlement report: 1.2% in the Hurricane Beryl month, $55 on $3.47M in October 2025 |

## Gates: who may change what

- **Tiered autonomy.** Tier a, bounded reversible reweights: automatic, and a card notifies. Tier b, component swaps
  under strong gates: automatic after a visible veto window. Tier c, thin-sample gates or anything that rewrites
  history: a person must check it. Bid submission is human, always.
- **The governor (S55).** A CUSUM changepoint detector with reference value 0.5σ and decision limit 4σ runs on 24
  walk-forward error and metric streams, each accumulated as of first sight. Detection starts at 8 observations. A
  spike of |z| ≥ 3 that reverts is an outlier, routed to the tail layer only: reweighting the mean on a Beryl would make
  the model worse 51 weeks a year. A shift sustained for three windows is a regime break, and it opens a card with the
  evidence, a proposed action, its blast radius and its tier. A hand-set number left unchanged for three months gets a
  card asking that it be fitted or retired.
- **The lever gate.** Bounded levers move only when a challenger value beats the incumbent's replayed rank correlation
  by at least 0.005 on every one of 14 auctions: selected on all but the latest month, then confirmed on that untouched
  month. Each move is written to the lever file with its receipt.
- **The promotions ledger.** Every gate-controlled trust flag is snapshotted each night, and every flip is appended,
  never rewritten: 6,193 promotion and demotion events so far.

## Leakage: measured, not asserted

- **Two clocks.** An auction closes during the month before delivery; a month is settled only after it ends. Every
  as-of feature set states which clock it runs on. The skill-conditioned flow lane built 2,117,829 as-of features under
  that contract before testing any of them.
- **Hindsight as a number.** The dark-value screen (S58b) is rebuilt as of each auction, over 48 delivery months from
  July 2022, using only settlement months complete before that auction. It is scored against what each month then
  paid, and the full-history rank is scored on the same targets, so the leakage is measured.
- **Scored only if it existed.** The prediction ledger (S97) refuses to score a call issued inside its own month, and
  it scores a hidden-load forecast only from a vintage dated before the bid close. The engine scoreboard (S99s) counts a
  forecast only if the vintage archive shows its file written at or before the close.
- **Past origins see only their past.** The hidden-load forecaster re-scores every past bid close against that origin's
  own fit, with every input dated before the bid-close day. An append-only lever history pins the settings each origin
  actually used. A poisoning test, which changes the data after an origin and checks nothing moves, holds it there.

## What the machinery found

- **The physics, confirmed on 1.9 million node-days (S50).** A basis blowout is a day when a node's basis leaves its
  trailing 90-day median by more than max(4σ, $8), with the trailing statistics shifted a day so nothing peeks. Eight
  candidate indicators were tested on the same day and at leads of 1, 3, 7 and 14 days, 42 tests in all, under a bar
  of lift above 1.2 at FDR q < 0.05 in training and lift above 1 out of sample. The one that passes is the physical
  one: constraint pressure inside the node's own shift-factor exposure, as a same-day now-cast, at a lift of 1.35
  (q = 0.0018) and 1.22 out of sample. It drives a watch list, never a price.
- **Others' behavior is predictable (S51e).** Holder-skill-conditioned flow, read only from what was public before
  each auction, predicts how crowded a path will be in the next auction beyond persistence. Over 12 of 12 months the
  hypothesis set lifts the rank correlation by +0.022 (bids) and +0.024 (MW), with a sign-test p of 0.0005 and above
  the placebo. The strongest single feature lifts it by +0.083 and +0.087. 10 of 44 pre-registered sets clear. A
  pass can earn a participant-screen factor, never a place in the value model.
- **A null kept on record (S51d).** The same flows do not improve the value replay: 0 of 40 feature sets cleared. They
  are real, and already priced.
- **Cheap entries tested for reality (S58).** A feasibility gate checks whether a penny entry was ever available. In
  the September 2026 auction only 0.27% of 10,000 gated rows were penny-feasible, and none of the 164 cleanest top
  rows were. So the as-of screen re-prices entry at its constraint neighborhood's cleared level and recomputes the
  payout probability against that entry.
- **Exposure per unit of crowd (S12c).** `event_beta(node) = Σ_c |SF(node,c)| · scenario severity(c)` and
  `periphery = event_beta / (1 + holders at the node)`: resource nodes outside a crowded load zone that carry the same
  event exposure at uncrowded prices.
- **What weather does not explain (S17).** Each family's residual against its own calendar climatology is correlated
  with the candidate library and classed: explained by a named feature (which earns its own weight), needs a news tag
  (routed to dated-event tagging), or well forecast. When the atlas was built, 272 families needed a news tag and none
  was explained by monthly weather, which is why weather enters only through scenarios.
