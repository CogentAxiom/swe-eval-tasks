# Post-mortem: the October CRR book and the 2026-11-17 cold-snap dispatch

For the power desk. All figures are $/MWh unless stated. `docs/METHODOLOGY.md` (v3.2) and
`docs/DISPATCH_RULES.md` (v1.4) were treated as authoritative; every fix below moves the code to what
those documents say. Nothing is keyed to a date, path, hour, element or number in `data/`.

## Where things stand

| Item | Status |
|---|---|
| November valuation | Written to `out/valuation_2026-11.csv`, with all five valuation fixes in. |
| Engine vs Market Risk, October H-1026 | Nine of ten paths agree to the cent. **P07 disagrees: the engine (5.10) is right and Risk (7.94) is wrong.** Details in section 3. |
| Shadow dispatch for 2026-11-17 | Rewritten as the security-constrained dispatch of `DISPATCH_RULES` section 6 and written to `out/dispatch_2026-11-17.csv`. No load is shed on the day. |
| Backtest on 2026-11-10 | **FAILS.** 19 of 24 hours reproduce PGO's prices at all 8 points to the cent. Hours 8, 9, 17, 18 and 19 do not. Sections 6 and 7 say why. **The desk should not treat the model as having passed the rules' test.** |

---

## 1. Valuation: five root causes

Found by reading `gridbook/valuation.py`, `weather.py` and `network.py` against the methodology, then
reconciling to Risk. The one thing that exposed the first cause immediately is the methodology's own
worked example (section 10): the old engine gave 2.785 for `S(BASE)` of P01 in September where the
document has 10.615.

### V1. The network adjustment had the wrong sign (`network.path_factor`)

- **Symptom.** Every congestion term N(s) was negated. September P01 came out 2.79 against the
  documented 10.62. Base-scenario spreads on October's Metro-sink paths were far too low (P01 BASE 1.94;
  correct 12.46).
- **What was wrong.** `path_factor` returned `SF(sink) - SF(source)`. Section 6: a point's congestion price is
  `-sum SF*mu`, so a path (sink minus source) is worth `SF(source) - SF(sink)`.
- **Fix.** `SF(source) - SF(sink)`. The worked example now returns 10.615 / 10.62.

### V2. Wind was read at 10 m, not at hub height (`weather.base_bias`)

- **Symptom.** In November the wind term vanished. WEST and PANHANDLE had 10 m winds of 4.2 and 3.8 m/s,
  below their `wind_ref` of 7.5 and 8.0, so the term was zero, while the 100 m winds were 11.6 and 12.4 m/s
  (November's outlook has `temp_100m` above `temp_2m` in every region, the inversion the methodology warns about).
  So `w0(WEST)` was +0.70 instead of -5.86 and `w0(PANHANDLE)` +0.60 instead of -9.08, and paths sourced in
  those regions (P02, P04, P05, P08, P10) were undervalued by 6.56 (WEST) and 9.68 (PANHANDLE).
- **Why October did not show it.** October's 100 m winds (7.1, 7.6) are below the reference winds, so the
  wind term is zero either way. This cause cannot be seen in Risk's revaluation; it only bites in November.
- **What was wrong.** `dec(row["wind_10m"])`. Section 4.1: the wind term uses `wind_100m`; `wind_10m` is not used.
- **Fix.** Use `wind_100m`.

### V3. The knockout inversion was never implemented (`weather.scenario_bias`)

- **Symptom.** This is what Risk saw. In H-1026 the engine had Metro-sink paths gaining (P01 +9.14,
  P02 +9.01, P03 +5.27, P10 +7.30) where they lose (-13.85, -7.53, -20.13, -7.86).
- **What was wrong.** Every affected region took the demand curve `w0 + beta*I`. METRO in H-1026 got
  +9.00 x 0.80 = +7.20; section 4.2(b) says a hurricane or freeze with `D >= 0.15` gives `w0 - lambda*D`
  = -55.00 x 0.38 = -20.90, a 28.10 swing on every path into (or out of) Metro. SOUTH (D = 0.09) is below
  the threshold and correctly stays on the demand curve.
- **Fix.** `weather.knocked_out_regions(event)` (hurricane or freeze, `outage >= 0.15`, inclusive, heat never)
  and the inversion in `scenario_bias`. In November this knocks out NORTH in the freeze F-1126 (D = 0.24)
  and nothing else (PANHANDLE 0.05, SOUTH 0.06 and METRO 0.04 in TS-1126 are below the threshold).

### V4. The import collapse was never implemented (`valuation._network_adjustment`)

- **Symptom.** After V1 to V3 the engine was still off Risk's H-1026 numbers on eight paths: P01 +5.41,
  P02 +4.42, P10 +4.36, P03 +2.44, P06 -2.44, P08 -0.99, P04 -0.92, P05 -0.85 (P07 and P09 happened to agree;
  see section 3 for what that means). METRO_IMPORT was still binding in H-1026 with `q = 0.55`.
- **What was wrong.** `q(c, s)` was always the constraint's `binding_probability`. Section 6: a constraint
  whose `import_region` is a region the scenario knocks out has `q = 0` in that scenario.
- **Fix.** `_network_adjustment` skips constraints whose `import_region` is in the scenario's knocked-out set.
  In November this zeroes NORTH_IMPORT (import region NORTH) in F-1126. A heat event never collapses an
  import constraint, whatever its outage fraction.

### V5. Options were floored on the expected value, not per scenario (`valuation.value_paths`)

- **Symptom.** Options were undervalued whenever some scenarios were out of the money and others in.
  October P03 (OPT) came out 0.00; correct is 5.03 (BASE +6.708 at 0.75; H-1026 -20.134 at 0.25;
  the expectation is -0.0025, so `max(0, E[S])` is 0, but `E[max(0, S)]` is 5.03).
- **What was wrong.** `v = max(0, sum p*S)` for `OPT`. Section 8: `V = sum p_s * max(0, S(s))`.
- **Fix.** Per-scenario floor. This changes no November number (every November option has a positive
  spread in every scenario), so it is a latent bug that November does not expose.

Also: a value that rounds to zero from below printed as `-0.00`; it now prints `0.00`. Rounding (half away
from zero, at the end, full precision in `Decimal`) was already right.

### What each fix did to November (applied in this order, each on top of the last)

| Path | Type | Old engine | + V1 sign | + V2 hub wind | + V3 knockout | + V4 collapse (= final; V5 adds nothing) |
|---|---|---:|---:|---:|---:|---:|
| P01 | OBL | 5.66 | -2.15 | -2.15 | 0.96 | **1.75** |
| P02 | OBL | -0.51 | 13.58 | 20.14 | 20.14 | **20.18** |
| P03 | OPT | 1.32 | 4.67 | 4.67 | 4.67 | **4.65** |
| P04 | OBL | -2.98 | 21.32 | 31.00 | 27.89 | **27.18** |
| P05 | OPT | 0.00 | 19.12 | 25.68 | 22.57 | **21.88** |
| P06 | OBL | -0.12 | -3.47 | -3.47 | -3.47 | **-3.45** |
| P07 | OBL | 1.73 | -8.81 | -8.81 | -5.70 | **-4.95** |
| P08 | OPT | 0.60 | 7.88 | 14.44 | 14.44 | **14.50** |
| P09 | OBL | -1.47 | 12.94 | 12.94 | 9.83 | **9.02** |
| P10 | OPT | 0.00 | 15.48 | 25.16 | 25.16 | **25.18** |

---

## 2. Valuation: how the fixes were checked

- Methodology section 10 worked example: P01, September: `S(BASE)` = 10.615, value 10.62.
- Every value for all four months (08 to 11) was recomputed by a separate script written from the
  methodology text only (exact `Fraction` arithmetic straight from the CSVs, nothing imported from
  `gridbook`). All 40 values match the engine's output.
- October H-1026, engine vs Risk (below).

---

## 3. Reconciliation with Market Risk (October, scenario H-1026)

| Path | Old engine | Fixed engine | Risk |
|---|---:|---:|---:|
| P01 | 9.14 | -13.850 | -13.85 |
| P02 | 9.01 | -7.530 | -7.53 |
| P03 | 5.27 | -20.134 | -20.13 |
| P04 | 0.35 | 8.474 | 8.47 |
| P05 | -0.05 | 6.704 | 6.70 |
| P06 | -3.77 | 21.634 | 21.63 |
| **P07** | 2.98 | **5.100** | **7.94** |
| P08 | 4.79 | 10.520 | 10.52 |
| P09 | -4.99 | -4.434 | -4.43 |
| P10 | 7.30 | -7.860 | -7.86 |

Nine paths agree. The 0.004 differences are Risk rounding to the cent; the engine carries full precision.

**P07 (PGO_HUB_NORTH to PGO_HUB_SOUTH) still disagrees, by 2.84. The engine is right and Risk's 7.94 is wrong.**

- Methodology section 6: a constraint whose `import_region` is a region the scenario knocks out has `q(c, s) = 0`
  in that scenario. METRO_IMPORT's `import_region` is METRO; H-1026 is a hurricane with `D(METRO) = 0.38 >= 0.15`.
  So METRO_IMPORT does not bind in H-1026, for every path.
- Engine P07 in H-1026: baseline 1.70 + weather 3.76 (SOUTH 4.5 x 0.28 + 7.00 x 0.50 = 4.76 against
  NORTH 5.0 x 0.20 = 1.00) + network -0.36 (PAN_NORTH: (-0.20 - 0) x 4.50 x 0.40; WEST_EXPORT: -0.12 - (-0.12) = 0;
  METRO_IMPORT zeroed) = **5.10**.
- Risk's 7.94 is exactly the engine's 5.100 plus METRO_IMPORT left binding at its 0.55 probability:
  (0.18 - (-0.25)) x 12.00 x 0.55 = 2.838, and 5.100 + 2.838 = 7.938, which rounds to 7.94. So Risk
  did not apply the collapse to this path.
- Risk did apply it to P04, P05 and P08, which also have no Metro leg: their numbers match the collapsed
  values (8.47, 6.70, 10.52) and not the uncollapsed ones (7.55, 5.85, 9.53). The paths with a Metro leg
  (P01, P02, P03, P06, P10) are collapsed too. P09 does not discriminate (its METRO_IMPORT factor is zero).
  So P07 is the one path where Risk is inconsistent with its own method. The collapse is a property of the
  scenario and the constraint, not of whether a path touches Metro. The Metro-loss story is unaffected:
  P07 is not a Metro path.

---

## 4. Dispatch: root causes

### D1. There was no network in the dispatch (`dispatch.dispatch_day`)

- **Symptom.** The shadow dispatch stacked units in merit order against total load and ignored every
  element. On 2026-11-17 it loaded NORTH_IMPORT above the SCADA limit in 18 hours (06:00 to 23:00), worst
  939 MW against 760 MW at 17:00.
- **Fix.** Each hour is now the linear program of section 6, solved with `gridbook/lp.py`: minimize unit
  cost plus $9,000/MWh of shed load, subject to the balance, `0 <= g <= availability`, `0 <= s <= load`,
  and `-limit <= flow <= +limit` for every monitored element, with
  `flow = sum SF(c,n) * (generation + shed - load)` and the reference bus `PGO_HUB_SOUTH`. Both directions are
  constrained. `plan[h]["shed"]` has an entry for every load node (zero when nothing is shed).

### D2. The "limits" were the weather vendor's advisory ratings (`feeds.line_limits`)

- **Symptom.** `line_limits` returned 1450 / 1350 / 1500 MW (NORTH_IMPORT / WEST_EXPORT / METRO_SOUTH) for
  every hour. PGO's operators were holding NORTH_IMPORT to 820 MW (600 from 17:00) on the 10th and 900 MW (760
  from 06:00) on the 17th, with WEST_EXPORT at 1000 and METRO_SOUTH at 1100; the vendor's file knows nothing of
  ice or contingencies.
- **What was wrong.** It read `ambient_adjusted_rating_mw`, which section 4 says is advisory and never a limit.
- **Fix.** `line_limits` returns SCADA's `post_contingency_limit_mw`, hour by hour, for monitored elements
  (those with shift factors) whose `status` is `IN`. Not returned: SOUTH_NORTH_2 (a single circuit, no shift
  factors, informational) and any monitored element that is `OUT` that hour. The vendor ratings are kept as
  `feeds.ambient_ratings`, reported but never used.

### D3. Wind availability followed the 10 m wind (`dispatch.availability`)

- **Symptom.** On the cold nights `wind_10m` is 2.2 m/s, below the 3.0 cut-in, so the old dispatch had the
  1,200 MW wind fleet at zero while `wind_100m` was 13.0 / 13.5 m/s (rated). By day it read 5.2 / 5.6 against 6.5 / 7.0
  at hub height.
- **Fix.** `wind_100m` through the fleet power curve. The 10 m reading is not used (section 3).

### D4. The "prices" were one number (`backtest.predicted_lmps`)

- **Symptom.** The model price was the offer of the marginal unit, identical at every node in the hour, so
  it could never show congestion.
- **Fix.** `dispatch.nodal_prices`: the model's price at a node is the change in the hour's optimal cost
  when that node's load is 1 MW higher (a node with no load gets 1 MW). It is a finite difference of the
  LP, not a dual, and that matters: PGO's 137.78 at hour 9 on the 10th is a blend of two offers over the
  one megawatt.

### D5. The backtest passed when it should not have (`backtest.backtest_day`)

- **Symptom.** The old backtest reported PASS on 2026-11-10 with an LMP mean absolute error of $18.08 and 173
  of 192 node-hours more than $0.05 off. Its test was "no flow above the vendor rating", which D2 made
  impossible to fail.
- **Fix.** Section 7: the model passes only when its price is within $0.05 of PGO's at every Settlement
  Point in every hour, **and** the hours and elements it binds (flow within 0.5 MW of the SCADA limit) are the ones
  PGO published. `out/backtest_<day>_constraints.csv` carries the binding comparison (model and PGO flags,
  flow, limit, and both shadow prices); `_lines.csv` carries every element-hour. The model reads PGO's
  prices only to score; a test confirms its prediction is unchanged when the prices directory is deleted.

`gridbook/lp.py` is unchanged. It is a plain two-phase simplex with Bland's rule; I checked it against an
independent solver (see section 8) rather than assume it.

---

## 5. The 2026-11-17 dispatch

`out/dispatch_2026-11-17.csv`: 360 rows (10 units + 5 load nodes, 24 hours), production cost
$1,536,059.91, no load shed. NORTH_IMPORT is at its limit from 07:00 to 21:00 (760 MW; 900 MW before 06:00,
where it is not binding). Prices (model): $35 flat overnight, a North premium that peaks in hours 8 and 18 to
20 (LZ_NORTH $145 against PGO_HUB_SOUTH $55). SOUTH_NORTH_2 (OUT from 06:00) is informational, as the rules
say: its outage is already inside NORTH_IMPORT's 760 MW.

---

## 6. Backtest on 2026-11-10: FAIL, and exactly where

`python -m gridbook.cli backtest --data data --day 2026-11-10 --out out/backtest_2026-11-10.csv`:

> BACKTEST FAIL 2026-11-10: LMP MAE $9.66, max |error| $85.19; 38 node-hours off by more than $0.05
> (hours [8, 9, 17, 18, 19]); 3 binding mismatches (hours [8, 9, 17]); 0 limit overloads

152 node-hours (hours 0 to 7, 10 to 16 and 20 to 23, 8 points each) match PGO's published price to the cent
(largest unrounded difference $0.004). In hours 20 to 23 the binding comparison also reproduces PGO's
shadow prices on NORTH_IMPORT exactly (125.00, 22.58, 45.95, 45.95). The five hours that fail:

### Hours 8 and 9: PGO's prices need 900 MW less cheap supply than the as-of inputs show

| | Model | PGO |
|---|---|---|
| Hour 8 | 55.97 / 62.00 / 57.92 / 54.81 / 56.75 / 61.61 / 55.00 / 56.75 (METRO, NORTH, PANHANDLE, SOUTH, WEST, HUB_NORTH, HUB_SOUTH, HUB_WEST), NORTH_IMPORT binding at 820 MW | 140.00 at every point, nothing binding |
| Hour 9 | same pattern as hour 8 | 137.78 at every point, nothing binding |

Errors are -75.78 to -85.19. What the data pin down:

- 140.00 and 137.78 are the offers of N_PEAK and M_PEAK. Hour 9 is the blend `8/9 x 140 + 1/9 x 120 = 137.78`:
  M_PEAK has 1/9 MW of headroom left and N_PEAK serves the rest of the next megawatt.
- Re-running the model with a block of cheap supply removed reproduces all eight prices (to the cent) in hour 9 only when
  that block is **900.0 MW** (899.9 MW gives 135.78), and hour 8 for any block from about 685 to 900 MW. The same removal also
  drops NORTH_IMPORT to 505 MW (hour 8) and 568 MW (hour 9), well under the 820 limit, which is why PGO
  published no binding constraint in these hours.
- The only single unit in the fleet with a 900 MW rating is S_NUKE. Removing S_NUKE in hours 8 and 9 alone
  reproduces PGO exactly in both hours. Hours 7 and 10 do not match with S_NUKE out, so whatever it was
  began at hour 8 and had ended by hour 10. S_COAL plus W_GAS (900 MW) and S_GAS plus W_GAS (900 MW) also fit
  both hours, and 900 MW of extra load at LZ_METRO, LZ_SOUTH or LZ_WEST (and in hour 8 LZ_PANHANDLE too; not
  at LZ_NORTH) fits as well, so the prices fix the size, not the cause.
- **Cause, as far as the data allows:** about 900 MW of supply that the model counts as available was not
  available to PGO in hours 8 to 9, most plausibly a trip of the 900 MW nuclear unit (or an equivalent load surprise).
  Nothing in the load forecast, weather feed or SCADA records it: SCADA covers lines, not units, and the
  rules (section 3) have nuclear available at `pmax` in every hour. An as-of replay cannot see it, so this
  is not an engine error and I did not tune anything to hide it. Confirming it needs PGO's unit outage log
  for the 10th, which is not in the repository.

### Hours 17, 18 and 19: PGO's prices carry the pre-de-rate NORTH_IMPORT limit

| Hour | Model (SCADA limit 600 MW) | PGO | Binding |
|---|---|---|---|
| 17 | 48.00 / 62.00 / 52.52 / 45.29 / 49.81 / 61.10 / 45.74 / 49.81 | 55.00 at every point | model binds NORTH_IMPORT (shadow 22.58); PGO does not |
| 18, 19 | 67.50 / 145.00 / 92.50 / 52.50 / 77.50 / 140.00 / 55.00 / 77.50 | 55.97 / 62.00 / 57.92 / 54.81 / 56.75 / 61.61 / 55.00 / 56.75 | both bind; model shadow 125.00, PGO 9.72 |

Errors reach +83.00 (LZ_NORTH, hours 18 and 19); PGO_HUB_SOUTH, the reference bus, matches (55.00).

- SCADA's record for hour 17 and later carries the icing de-rate ("icing de-rate from 17:00"): NORTH_IMPORT
  600 MW, down from 820 MW.
- Solving each of the three hours again with only NORTH_IMPORT's limit changed, PGO's prices appear for any
  limit of roughly 795 MW and up in hour 17, 645 to 925 in hour 18 and 685 to 955 in hour 19 (5 MW steps). The three ranges
  overlap at about **795 to 925 MW**, which holds the pre-de-rate 820. In hour 17 the unconstrained flow is
  792.5 MW, so any limit above that leaves the element not binding, as PGO shows. In hour 20 the matching range is
  570 to 640 MW, which holds 600.
- **Cause, as far as the data allows:** PGO's published prices for hours 17 to 19 behave as though NORTH_IMPORT were
  still at about 820 MW, and the 600 MW de-rate shows in PGO's prices from hour 20, three hours after SCADA's
  timestamp. The data cannot say whether PGO's market ran on a stale limit for three hours or SCADA's
  de-rate record is stamped early; either way the rules tell the model to use each hour's own SCADA record,
  which it does. I did not shift the de-rate to make the hours match.
- **Why it matters for the 17th.** The 17th's SCADA has a step at 06:00 (NORTH_IMPORT 900 to 760) and the same
  kind of "de-rate" text. If PGO is slow to price that step as well, the model's hours 7 and 8 (the first hours
  where 760 binds and 900 would not) are the exposed ones: at 900 MW the model would price hour 7 at $55 flat
  and hour 8 at $62 flat, against the $45.29 to $62.00 and $52.50 to $145.00 spreads it shows with 760. One day's evidence does not establish a lag, so
  the dispatch file follows the rules. The desk should look at those hours before trading them.

---

## 7. What the desk should and should not take from this

- November's valuation and the 11-17 dispatch are produced by code that follows the two authoritative documents.
- The backtest did **not** pass. Its failures are in five hours and are explained by two things the as-of
  inputs do not carry (a 900 MW supply or load difference in hours 8 to 9; the timing of the NORTH_IMPORT
  de-rate in hours 17 to 19), not by a dispatch or price-calculation fault I could find: the other 19 hours match to the
  cent, including every congested hour from 20 to 23.
- Whether that is good enough to trade on is the desk's call; the rules' own test says it is not a pass.

---

## 8. What I ran to verify, and the results

| Check | Result |
|---|---|
| `python -m unittest discover -s tests` | 33 tests, all pass. 22 are new: valuation (worked example, sign, hub-height wind, knockout threshold and heat, import collapse, option floor, no negative zero, Risk reconciliation) and dispatch (limit in both directions, shed at VOLL, OUT element has no limit, finite-difference price, node with no load, SCADA limits, 100 m wind, flows within limits on both days, backtest result by hour). Run against the original code they give 14 failures and 4 errors. |
| `value --month 2026-11` | Written. Matches the independent `Fraction` recomputation for all 40 path-months (08 to 11). |
| September P01 | 10.615 before rounding, 10.62 after, as in methodology section 10. |
| October H-1026 vs `risk/october_revaluation.csv` | 9 of 10 within 0.004 (their rounding); P07 differs by exactly 2.838 before their rounding, explained in section 3. |
| LP check | `lp.py` against SciPy/HiGHS (used only to check; not imported by the repo): every hour of both days plus all eight price perturbations per hour agree to 1.2e-10; several hundred random dispatch and general instances (including zero limits, zero costs, negative right-hand sides) agree to better than 1e-12 relative, and the returned dispatches respect balance, availability and limits. |
| `dispatch --day 2026-11-17` | Written, 360 rows, cost $1,536,059.91, no shed, every flow within its SCADA limit in both directions. |
| `backtest --day 2026-11-10` | Written (`out/backtest_2026-11-10.csv`, `_constraints.csv`, `_lines.csv`). FAIL: hours 8, 9, 17, 18, 19; binding mismatches in hours 8, 9, 17; no overloads. |
| Hypothesis runs for section 6 | Re-solved hours 7 to 10 and 17 to 20 with S_NUKE removed, other 900 MW blocks, extra load, and NORTH_IMPORT limits swept in 5 MW steps. These were diagnostics only; none of it is in the engine. |
