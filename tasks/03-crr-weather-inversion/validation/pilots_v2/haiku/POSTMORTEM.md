# Postmortem: October CRR book, November valuation, cold-snap shadow dispatch

Scope: `gridbook` at this repository root. The references are `docs/METHODOLOGY.md` (v3.2) and `docs/DISPATCH_RULES.md` (v1.4). Where the code disagreed with them, the code was changed. The docs and the feeds were not edited, and no date, path, hour or element is special-cased.

## Summary

- **Valuation.** Five defects. Three of them (knockout inversion, import collapse, sign) change October's realized spreads, and together they explain Risk's finding that Metro-sink paths were valued as gaining in H-1026. The option floor changes October values for P03 and P10 but not the spreads, and the 10 m wind matters only in November. After the fixes the engine reproduces Risk's H-1026 spreads on nine of ten paths to the cent. P07 still differs, and the engine is right there (section 3).
- **Dispatch.** Five defects. The dispatch ignored the network entirely, so it breached the NORTH_IMPORT limit in 10 hours on 2026-11-10 and 18 hours on 2026-11-17. It also read the 10 m wind, so the wind units produced nothing in the cold hours.
- **Backtest, 2026-11-10: FAILS.** 38 of 192 prices are more than $0.05 from PGO's, in hours 8, 9, 17, 18 and 19. The model binds NORTH_IMPORT in hours 8, 9 and 17 where PGO's list does not. Hours 17 to 19 come from one input conflict: SCADA's 600 MW limit against the 820 MW that PGO's own prices imply. Hours 8 and 9 cannot be reproduced by any network limit; PGO's $140 needs scarcity that the desk's feeds do not show.
- **Do not trade 2026-11-17 on the dispatch** until PGO confirms the NORTH_IMPORT de-rate timing (section 4.4).

## 1. Valuation: root causes

### 1.1 Knockout inversion missing (METHODOLOGY 4.2 b, c)

- **Symptom.** Metro-sink paths gained in H-1026. Old-engine H-1026 spreads against Risk's: P01 +9.14 (Risk -13.85), P02 +9.01 (-7.53), P03 +5.27 (-20.13), P10 +7.30 (-7.86).
- **Wrong.** `scenario_bias` applied the demand curve to every region the event touched. METRO's outage is 0.38, at or above the 0.15 threshold, so METRO's bias is w0 - lambda x D = 1.80 - 55 x 0.38 = -19.10. The code computed w0 + beta x I = 1.80 + 9 x 0.80 = 9.00: a 28.10 $/MWh error in METRO's bias, carried into every path that touches Metro.
- **Fix.** `weather.knocked_out_regions` (hurricane or freeze, outage at or above 0.15, inclusive). `scenario_bias` inverts those regions and leaves heat alone (4.2 c).

### 1.2 Import collapse missing (METHODOLOGY 6)

- **Symptom.** METRO_IMPORT's congestion stayed in the H-1026 spreads although 38% of Metro's load was out. Without the collapse the H-1026 spreads are higher by 5.41 on P01 (LZ_NORTH to LZ_METRO), 4.42 on P02, 2.44 on P03 and 4.36 on P10, and lower by 2.44 on P06.
- **Wrong.** `_network_adjustment` used the binding probability of every constraint in every scenario. Section 6 sets q(c,s) = 0 when the constraint's import region is knocked out in scenario s, for every path.
- **Fix.** `_network_adjustment` receives the scenario's knocked-out set and zeroes q for constraints whose `import_region` is in it.

### 1.3 Network sign reversed (METHODOLOGY 6)

- **Symptom.** Every congestion term had the wrong sign. The methodology's own worked example, September P01, gives 10.615, or 10.62; the old engine gave 2.79. In H-1026 the sign error moved P02 by 7.14, P04 by 9.05, P08 by 6.72 and P10 by 8.58.
- **Wrong.** `path_factor` returned SF(sink) - SF(source). Section 6 requires SF(source) - SF(sink): a point's congestion price is -SF x mu, and a path settles sink minus source.
- **Fix.** `path_factor` returns SF(source) - SF(sink).

### 1.4 Option floor applied to the expectation (METHODOLOGY 8)

- **Symptom.** October P03 (OPT) valued 0.00; the correct value is 5.03. P10 was 11.09 and is 13.05 (both with the other fixes applied). No September or November value changes, because no option's scenario spreads cross zero in those months.
- **Wrong.** V = max(0, sum of p x S). That is zero whenever the expected spread is negative, even when the option pays in the base scenario.
- **Fix.** V = sum of p x max(0, S), scenario by scenario.

### 1.5 Wind bias read the 10 m wind (METHODOLOGY 4.1)

- **Symptom.** On cold nights the 10 m wind is calm while the hub-height wind is strong. In 2026-11, WEST has 4.2 m/s at 10 m and 11.6 m/s at 100 m; PANHANDLE has 3.8 and 12.4. The old engine gave w0(WEST) = +0.70 and w0(PANHANDLE) = +0.60, with no wind term. The correct values are -5.86 and -9.08.
- **Effect.** November paths: P02 +6.56, P04 +9.68, P05 +6.56, P08 +6.56, P10 +9.68. October is unchanged, because both readings are below wind_ref.
- **Fix.** `base_bias` uses `wind_100m`.

## 2. Shadow dispatch: root causes

### 2.1 Merit-order stack ignored the network (DISPATCH_RULES 6)

- **Symptom.** The old dispatch breached NORTH_IMPORT. On 2026-11-10 it breached in hours 6, 8, 9, 17, 18, 19, 20, 21, 22 and 23 (10 hours). On 2026-11-17 it breached in hours 6 to 23 (18 hours). It also never shed load, since shed was always empty.
- **Wrong.** `dispatch_day` stacked the units in cost order against the load, with no flow limits.
- **Fix.** Each hour is the least-cost LP of section 6, solved with `gridbook/lp.py`: load balance, unit availability, shed between 0 and the node's load at $9,000/MWh, and -limit <= flow <= +limit for every monitored element, with flows from the shift factors.

### 2.2 Wind availability read the 10 m wind (DISPATCH_RULES 3)

- **Symptom.** W_WIND and P_WIND were both 0 MW in hours 0 to 7 on both days. The 10 m reading is 2.2 m/s, below cut-in. The 100 m wind of 10.5 to 11.0 m/s gives 583 and 444 MW.
- **Fix.** Availability follows `wind_100m` in the unit's region.

### 2.3 Line limits came from the weather vendor's advisory ratings (DISPATCH_RULES 4)

- **Symptom.** The NORTH_IMPORT limit was the ambient rating of 1,450 MW (2026-11-10, hour 0). SCADA's limit is 820 MW, dropping to 600 MW from 17:00 that day, and 900 MW, dropping to 760 MW from 06:00 on 2026-11-17. The icing de-rate was ignored, and no SCADA status was read at all: a monitored element that is OUT has no limit in that hour.
- **Fix.** `feeds.line_limits` reads SCADA's `post_contingency_limit_mw` for each monitored element (one with shift factors). It omits an element that is OUT in an hour, ignores single-circuit records, and raises if a monitored element has no usable record in an hour. The dispatch must not run with a constraint silently missing.

### 2.4 Model prices were the marginal unit's cost, identical at every node (DISPATCH_RULES 7)

- **Symptom.** All eight Settlement Points carried one price per hour, so congestion could not appear in any predicted price.
- **Fix.** The model price at each point is the change in the hour's LP optimum for 1 MW more load there, with everything else unchanged. A node with no forecast load gets the 1 MW.

### 2.5 Backtest pass test and binding comparison (DISPATCH_RULES 7, 8)

- **Symptom.** The old pass test was "no overloads", measured against the advisory ratings. Binding was never compared with PGO's published constraints. The binding file was named `_lines.csv` and carried the advisory ratings.
- **Fix.** The model passes only when every price is within $0.05 of PGO's and the set of (hour, element) pairs it binds equals PGO's published set. An element binds when |flow| is within 0.5 MW of its SCADA limit. The comparison is written to `out/backtest_<day>_constraints.csv`.

## 3. Engine against Risk, October: the one path that still disagrees

| Path | Risk H-1026 | Engine H-1026 | Difference |
|---|---:|---:|---:|
| P01 | -13.85 | -13.85 | 0.00 |
| P02 | -7.53 | -7.53 | 0.00 |
| P03 | -20.13 | -20.13 | 0.00 (rounding) |
| P04 | 8.47 | 8.47 | 0.00 (rounding) |
| P05 | 6.70 | 6.70 | 0.00 (rounding) |
| P06 | 21.63 | 21.63 | 0.00 (rounding) |
| **P07** | **7.94** | **5.10** | **+2.84** |
| P08 | 10.52 | 10.52 | 0.00 |
| P09 | -4.43 | -4.43 | 0.00 (rounding) |
| P10 | -7.86 | -7.86 | 0.00 |

The "rounding" entries differ by 0.004 or less, because the engine carries unrounded spreads and Risk reports cents.

**P07 (PGO_HUB_NORTH to PGO_HUB_SOUTH). The engine is right; Risk's figure does not hold under the methodology.**

- The gap is exactly METRO_IMPORT's term for P07: (SF(PGO_HUB_NORTH) - SF(PGO_HUB_SOUTH)) x 12.00 x 0.55 = (0.18 + 0.25) x 6.60 = 2.838.
- Section 6 zeroes a constraint whose import region is knocked out. METRO is knocked out in H-1026 (outage 0.38), and METRO_IMPORT's import region is METRO. That zeroing applies to every path, P07 included.
- Risk's own figures apply it everywhere except P07. Its P04 (8.47) and P05 (6.70) are paths with no Metro endpoint. Including METRO_IMPORT would put them at 7.55 and 5.85, so Risk excluded it there. P07 is the only path where Risk includes it.
- Risk should re-run P07 with the collapse. The engine stands at 5.10.

## 4. Backtest, 2026-11-10: what still fails and why

**Result: FAIL.** 38 of 192 prices are more than $0.05 from PGO's, in hours 8, 9, 17, 18 and 19. The largest error is $85.19 (hour 8, LZ_SOUTH: model 54.81, PGO 140.00). In hours 8, 9 and 17 the model binds NORTH_IMPORT and PGO's list does not. Hours 18 and 19 agree on binding. Hours 0 to 7, 10 to 16 and 20 to 23 match PGO to the cent, and their binding agrees.

### 4.1 Hours 8 and 9: scarcity that the desk's data does not show

- PGO prices every point at $140.00 (hour 8) and $137.78 (hour 9), with no constraint published.
- With no network limits at all, the model prices both hours at $62.00 and $55.00 respectively. The fleet on the forecast offers 4,161 MW at under $140 (N_GAS 400, M_GAS 500, M_PEAK 300, S_COAL 600, S_NUKE 900, S_GAS 600, W_GAS 300, the wind units at 311 and 250). Load is 3,480 MW in hour 8 and 3,261 MW in hour 9.
- A uniform price at $140 means the cheap capacity actually available was below the load actually served. That needs more than 681 MW of cheap capacity lost in hour 8, or more than 900 MW in hour 9, if load was as forecast. The feeds carry no realized load, no forced outages and no unit availability, so the data cannot show it.
- The model's NORTH_IMPORT binding in these hours follows from its own dispatch. No limit setting reproduces PGO's prices.
- **Cause: a data gap.** The desk needs PGO's realized load and unit outages for hours 8 and 9.

### 4.2 Hours 17 to 19: PGO's NORTH_IMPORT limit was not SCADA's 600 MW

- SCADA shows NORTH_IMPORT at 820 MW through hour 16, then 600 MW from 17:00 ("icing de-rate from 17:00"). The rules say to use each hour's own record, so the model uses 600. At 600 the model binds NORTH_IMPORT in hour 17 and prices LZ_SOUTH at $45.29; PGO prices every point at $55.00 with no binding constraint.
- The model reproduces PGO's prices and binding exactly with NORTH_IMPORT at a higher limit: hour 17 needs about 795 MW or more, hour 18 about 645 to 925 MW, and hour 19 about 685 to 955 MW. (These ranges come from a 5 MW sweep.) The value 820 lies in all three.
- A diagnostic run with NORTH_IMPORT at 820 MW in hours 17 to 19 only (the model unchanged) leaves the residuals in hours 8 and 9 alone.
- Hours 20 and 21 reproduce at 600 MW (hour 20 needs about 570 to 640 MW; hour 21 about 600 to 715 MW), and hours 22 and 23 match at 600 MW as well. PGO's enforced limit therefore appears to have been 820 MW through hour 19 and 600 MW from hour 20, three hours after SCADA's 17:00 stamp.
- **Cause: an input conflict.** SCADA and PGO's enforced limit disagree in hours 17 to 19. The model follows the rules, and I did not change them. PGO should confirm which limit applied in hours 17 to 19 and whether SCADA's de-rate stamp is correct.

### 4.3 Hours 18 and 20 have identical desk inputs

- Loads, wind at both heights and all three monitored limits are identical in hours 18 and 20. The model therefore gives the same answer for both (LZ_NORTH $145.00). PGO gave $62.00 in hour 18 and $145.00 in hour 20.
- This is the same finding as 4.2 seen from the other side. The difference that matters is the limit PGO enforced. Temperature is the only other difference between the two hours (-7 and -8 C in hour 18, -9 and -10 C in hour 20). The rules do not use temperature, and nothing in the data shows it affects PGO's prices.

### 4.4 Consequence for 2026-11-17

- The same SCADA feed sets NORTH_IMPORT at 900 MW in hours 0 to 5 and 760 MW from 06:00. The dispatch binds the 760 MW limit in hours 7 to 21, with no load shed.
- Sensitivity: production cost is $1,536,060 with the SCADA limits. It is $27k lower if NORTH_IMPORT is 820 MW in hours 6 to 20 ($1,508,821), and $37k lower with no de-rate ($1,498,909). Whether PGO enforces the de-rate on time moves the trade.
- SOUTH_NORTH_2 is OUT from 06:00. It is a single circuit, so the model treats it as informational, and its outage is assumed to be in the 760 MW contingency limit. Confirm that with PGO.

## 5. Outputs

| File | Content |
|---|---|
| `out/valuation_2026-11.csv` | November values, $/MWh. P01 1.75, P02 20.18, P03 4.65, P04 27.18, P05 21.88, P06 -3.45, P07 -4.95, P08 14.50, P09 9.02, P10 25.18. |
| `out/dispatch_2026-11-17.csv` | Hourly MW for 10 units and 5 load nodes, 24 hours. |
| `out/backtest_2026-11-10.csv` | Model and PGO prices for 8 points, 24 hours. |
| `out/backtest_2026-11-10_constraints.csv` | Model and PGO binding for each monitored element and hour. |

November moved materially from the old engine. The old values were P01 5.66, P02 -0.51, P03 1.32, P04 -2.98, P05 0.00, P06 -0.12, P07 1.73, P08 0.60, P09 -1.47 and P10 0.00. October's book values moved too: P01 3.74 to 5.88, P02 3.61 to 11.46, P03 2.50 to 5.03, P04 0.35 to 7.78, P05 0.00 to 6.06, P06 -1.00 to 1.50, P07 0.36 to 4.60, P08 2.17 to 7.15, P09 -2.36 to -1.81, P10 1.90 to 13.05.

## 6. Verification

- **Unit tests.** `py -3 -m unittest discover -s tests`: 29 tests, all pass. They cover each fix, the September worked example, the knockout threshold, heat not inverting, the sign, the import collapse, the option floor, hub-height wind, SCADA limits (including OUT and missing records), solver limits in both directions, the October comparison with Risk, and the backtest residuals.
- **Worked example.** September P01: 10.62 (was 2.79).
- **Risk reconciliation.** Nine of ten October paths agree within 0.004 (cent rounding). P07 is 2.84 apart, explained in section 3.
- **Independent re-derivation.** A standalone script written from `docs/METHODOLOGY.md`, not importing the engine, reproduces all 30 path values for September, October and November exactly.
- **LP check.** On both operating days, every hour's optimal cost and all 1 MW price probes match SciPy's HiGHS solver to within 1e-10. This was an out-of-repo check; the repository remains standard-library only.
- **Dispatch.** In both directions, no monitored element exceeds its SCADA limit in any hour on either day. No load is shed on 2026-11-17.
- **Backtest, 2026-11-10.** FAIL, as described in section 4.
- **Diagnostics (no model change).** Sweeps of the NORTH_IMPORT limit by hour, unconstrained prices for hours 8 and 9, and the identical-input comparison for hours 18 and 20. The results are in section 4.

## 7. Open items for the desk

1. PGO: which NORTH_IMPORT limit applied in hours 17 to 19 on 2026-11-10, and whether SCADA's 17:00 de-rate stamp is right. Same question for the 2026-11-17 schedule (900 MW to 06:00, then 760 MW).
2. PGO: realized load and unit outages for 2026-11-10 hours 8 and 9.
3. Risk: re-run P07 with the import collapse.
4. Do not trade the 2026-11-17 dispatch until item 1 is answered.
