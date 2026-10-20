# Postmortem: the October CRR book and the 17 November shadow dispatch

For the power desk. `docs/METHODOLOGY.md` (v3.2) and `docs/DISPATCH_RULES.md` (v1.4) are authoritative;
every fix below makes the code agree with them. No date, path, hour, element or number is special-cased.

**Short version.** The valuation had five independent faults. The one Market Risk saw was the
hurricane scenario pricing Metro up instead of down, but three others moved every path in every month,
including the worked example in the methodology (September P01 came out 2.79, the document says 10.62).
The shadow dispatch was not a security-constrained dispatch at all, it limited lines against the
weather vendor's ratings, it read the wrong wind, and its backtest could not fail. After the fixes the
engine reproduces nine of Risk's ten October H-1026 spreads to the cent. On the tenth, P07, the engine
is right and Risk's number is wrong (section 3). The corrected dispatch reproduces PGO's published
prices for 2026-11-10 at all 192 Settlement-Point hours, and the backtest passes.

---

## 1. Valuation

### V1. No knockout inversion (the October loss)

- **Symptom.** In the realized scenario H-1026 the engine had the paths into Metro gaining: P01 +9.14,
  P02 +9.01, P10 +7.30, against Risk's -13.85, -7.53, -7.86. P06 (out of Metro) was -3.77 against +21.63.
- **What was wrong.** `weather.scenario_bias` applied the demand curve `w0 + beta * I` to every region an
  event touches. For Metro in H-1026 that is `+9.00 x 0.80 = +7.20`, so a hurricane that took out 38% of
  Metro's load raised Metro's price. Methodology 4.2(b): a hurricane or freeze with outage fraction
  `D >= 0.15` removes the load, and the price falls, `w0 - lambda * D = -55.00 x 0.38 = -20.90`. That is a
  28.10 swing in the weather term of every path with Metro at one end.
- **Fix.** `weather.knocked_out_regions(event)` returns the regions with `D >= 0.15` (inclusive) for a
  hurricane or freeze, and never for heat. `scenario_bias` uses `w0 - lambda * D` for those regions and
  the demand curve for the rest. South at `D = 0.09` stays on the demand curve.

### V2. No import collapse

- **Symptom.** In H-1026 `METRO_IMPORT` stayed in the network adjustment of every path: +5.41 on P01, +4.42
  on P02, +2.84 on P07, -2.44 on P06: money attributed to a constraint that cannot bind in that scenario.
- **What was wrong.** Methodology 6: a constraint whose `import_region` is knocked out in the scenario is
  slack there, `q(c,s) = 0`. The engine used `binding_probability` in every scenario. The rule is about the
  constraint, not about the path, so it applies to a path with no Metro endpoint.
- **Fix.** `valuation._network_adjustment` takes the scenario's knocked-out regions and skips any
  constraint whose `import_region` is in the set. It is zero for that scenario only. The same rule
  collapses `NORTH_IMPORT` in the November freeze `F-1126` (North, `D = 0.24`).

### V3. Network adjustment had the wrong sign (every month)

- **Symptom.** The methodology's own worked example failed: September P01 was 2.79, not 10.62. The
  network term was `-3.69 - 0.225`, not `+3.69 + 0.225`. October and November congestion was likewise
  inverted for every path.
- **What was wrong.** `network.path_factor` returned `SF(sink) - SF(source)`. Section 6: a point's
  congestion price is `-sum SF * mu`, a path settles sink minus source, so the path's congestion value is
  `sum (SF(source) - SF(sink)) * mu`.
- **Fix.** `path_factor` returns `SF(source) - SF(sink)` (a missing shift factor is still zero).

### V4. Wind at 10 m instead of hub height

- **Symptom.** November base bias for the wind regions had no wind discount: WEST `+0.70` instead of
  `-5.86`, PANHANDLE `+0.60` instead of `-9.08`. That is up to 6.56 or 9.68 of error in the weather term
  of P02, P04, P05, P08 and P10. August to October were unaffected (the 100 m wind was below `wind_ref`
  in both wind regions), so October's run did not show it.
- **What was wrong.** `weather.base_bias` read `wind_10m`. Section 4.1: the wind term uses `wind_100m`; the
  10 m reading is a surface value that decouples from the wind aloft on stable nights and understates
  it. November's outlook is exactly that case (`temp_100m` above `temp_2m` in WEST and PANHANDLE).
- **Fix.** `base_bias` uses `wind_100m`.

### V5. Option priced as `max(0, obligation value)`

- **Symptom.** An option whose probability-weighted spread is slightly negative was priced at nothing
  even when it pays in most scenarios. With the other fixes in place the old rule gives October P03
  0.00 instead of 5.03 (it pays 6.71 in the 75% base scenario) and P10 11.08 instead of 13.05.
- **What was wrong.** `value_paths` summed `p x S` and floored the total. Section 8: an option's value
  is `sum p_s x max(0, S(s))`, not `max(0, V_obligation)`.
- **Fix.** Options are summed scenario by scenario. A value that rounds to zero is written as `0.00`,
  never `-0.00`. Rounding is half away from zero, at the end, at full precision (unchanged).

### Valuation, before and after

October H-1026 spread, $/MWh: engine as found, engine now, Risk.

| Path | Found | Now | Risk |
|---|---:|---:|---:|
| P01 | 9.14 | -13.85 | -13.85 |
| P02 | 9.01 | -7.53 | -7.53 |
| P03 | 5.27 | -20.13 | -20.13 |
| P04 | 0.35 | 8.47 | 8.47 |
| P05 | -0.05 | 6.70 | 6.70 |
| P06 | -3.77 | 21.63 | 21.63 |
| P07 | 2.98 | 5.10 | **7.94** |
| P08 | 4.79 | 10.52 | 10.52 |
| P09 | -4.99 | -4.43 | -4.43 |
| P10 | 7.30 | -7.86 | -7.86 |

November (`out/valuation_2026-11.csv`):

| P01 | P02 | P03 | P04 | P05 | P06 | P07 | P08 | P09 | P10 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.75 | 20.18 | 4.65 | 27.18 | 21.88 | -3.45 | -4.95 | 14.50 | 9.02 | 25.18 |

---

## 2. Shadow dispatch

### D1. Merit-order stack, not a security-constrained dispatch

- **Symptom.** On 17 November the dispatch loaded `NORTH_IMPORT` to between 786 and 939 MW in every
  hour from 6 to 23 against SCADA's 760 MW: 18 element-hours over the post-contingency limit, worst
  179 MW over at hour 17. It could not shed load, so it could not respond to a limit at all.
- **What was wrong.** `dispatch_day` sorted units by offer and filled the load. It ignored the network
  (rules section 4), had no load shed (section 5) and was not the optimisation of section 6.
- **Fix.** Each hour is a linear program solved with `gridbook/lp.py`: minimise offer cost plus
  `$9,000/MWh` of shed, subject to the balance, availability, `0 <= shed <= load`, and
  `-limit <= flow <= +limit` on every monitored element. Output has every unit and every load node, each hour.

### D2. Line limits came from the weather vendor

- **Symptom.** `line_limits` returned 1450 / 1350 / 1500 MW for `NORTH_IMPORT` / `WEST_EXPORT` /
  `METRO_SOUTH` all day. SCADA says `NORTH_IMPORT` 900 until 05:00 and 760 from 06:00 (the icing
  de-rate, the hour the South-North circuit is forced out), `WEST_EXPORT` 1000 and `METRO_SOUTH` 1100.
- **What was wrong.** It read `ambient_adjusted_rating_mw`, which section 4 says is advisory and "in cold air
  runs well above what PGO will let a line carry". It also never looked at the hour's own record.
- **Fix.** `feeds.line_limits` returns SCADA's `post_contingency_limit_mw` for each monitored element in
  each hour (status `IN`), for hours 0 to 23. The single circuit `SOUTH_NORTH_2` has no shift
  factors and is not returned. Normal and emergency ratings and the vendor's ratings are not used for
  limits. Two cases the rules do not spell out are handled conservatively: a monitored element whose
  record says `OUT` gets a limit of 0, and a monitored element with no usable record raises
  `ValueError` rather than getting an invented limit.

### D3. Wind availability read the 10 m wind

- **Symptom.** In the 11 inversion hours of 17 November (0 to 7 and 21 to 23, `temp_100m` above
  `temp_2m`) the model said both wind fleets were off: `wind_10m` is 2.2 m/s, under the 3.0 cut-in, while
  `wind_100m` is 13.0 to 13.5 m/s (rated). With the network enforced but this fault left in, the day costs
  $2.39 million; at hub height it costs $1.54 million. On the 10 November backtest the same fault alone
  produces a worst price error of $27.00.
- **What was wrong.** `availability` fed `wind_10m` to the power curve. Section 3: availability follows
  `wind_100m`; the 10 m wind is a surface reading that decouples on stable cold nights.
- **Fix.** `availability` uses `wind_100m`.

### D4. The backtest could not fail

- **Symptom.** On 2026-11-10 it printed `PASS` with a mean price error of $10.96 and a worst error of
  $20.00.
- **What was wrong.** The "model price" was the offer of the marginal unit, the same at every node, so no
  congestion ever showed. It passed when no flow exceeded the vendor's ratings, which sit 350 to 690 MW
  above SCADA's limits, so the test was nearly impossible to fail. It never compared prices to PGO's
  beyond printing them, never compared binding hours or elements, and wrote `_lines.csv` instead of the
  `_constraints.csv` the rules specify.
- **Fix.** Model price is the 1 MW change in the hour's optimal cost at each of the 8 Settlement Points in
  `points.csv` (a node with no load gets 1 MW), rules section 7. Passing means every price within $0.05 and the
  set of (hour, element) the model binds (flow within 0.5 MW of the limit) equal to PGO's. A day with no
  published prices is reported as not scored, never as a pass. The model never reads PGO's prices. The CLI
  writes `out/backtest_<day>.csv` and `out/backtest_<day>_constraints.csv`.

### Result

- **Backtest, 2026-11-10: PASS.** 192 of 192 prices within $0.05; the worst difference is $0.0044, which
  is PGO publishing to the cent. The model binds `NORTH_IMPORT` in hours 7, 8, 9, 17, 18, 19 and 20 and
  nothing else, which is exactly PGO's published list. The congested hours' prices match too, for
  example hour 7: LZ_NORTH $62.00, PGO_HUB_NORTH $61.10, LZ_PANHANDLE $52.52, LZ_METRO $48.00.
- **Dispatch, 2026-11-17** (`out/dispatch_2026-11-17.csv`): no load shed, production cost $1,536,059.91.
  `NORTH_IMPORT` sits at its limit of 760 MW in hours 7 to 21 (740 MW in hour 6 as the limit steps down
  from 900, so not bound there). LZ_NORTH reaches $145/MWh in hours 8, 18, 19 and 20, the highest price
  of the day, against $35 to $48 at night. This day cannot itself be backtested: PGO has not priced it.
- **What 2026-11-10 does not test.** It has one constant limit per element and no hour where a flow goes
  past a limit in the reverse direction. The hour-to-hour limit change on 17 November, reverse-direction
  limits and load shed are covered by unit tests and by the cross-checks in section 4.

---

## 3. Where the engine and Risk still disagree: P07, and the engine is right

Nine of ten paths agree to within a cent: the largest difference is 0.004, because Risk rounds its
spreads to the cent and the engine does not. **P07** (PGO_HUB_NORTH to PGO_HUB_SOUTH, an obligation)
does not: engine 5.10, Risk 7.94, a difference of 2.84.

The engine's number, from the inputs: baseline 1.70; weather `w(SOUTH) - w(NORTH) = (1.26 + 7.00 x 0.50) - 1.00
= 3.76` (South's `D = 0.09` is under the threshold, so South is on the demand curve, North is unaffected);
network: `METRO_IMPORT` is slack (Metro is knocked out, `D = 0.38`), `WEST_EXPORT` has equal shift factors at
both hubs (0), and `PAN_NORTH` gives `(-0.20 - 0) x 4.50 x 0.40 = -0.36`. Total `1.70 + 3.76 - 0.36 = 5.10`.

Risk's 7.94 is the engine's 5.100 plus `METRO_IMPORT` left binding: `(0.18 - (-0.25)) x 12.00 x 0.55 =
2.838`, and `5.100 + 2.838 = 7.938`, which rounds to 7.94. That is the import collapse not applied to
P07. Methodology 6 applies the collapse to the constraint, in every path, not only paths that end in
Metro. Risk's own sheet applies it that way on P04, P05 and P08, which have no Metro endpoint
either and whose `METRO_IMPORT` exposures (-0.92, -0.86, -0.99) are absent from Risk's numbers. P07 is the one
path where it was left in. P07's spread in H-1026 should be 5.10, and Risk should correct its sheet.

---

## 4. What I ran, and what happened

- `python -m unittest discover -s tests`: 35 tests, all pass. The suite now covers the worked example
  (P01 September = 10.615 before rounding, 10.62), hub-height wind in both valuation and dispatch,
  the inclusive 0.15 threshold, heat never inverting, import collapse applied to a path with no Metro
  endpoint, scenario-by-scenario option value, half-away-from-zero rounding, October against Risk
  (P07 asserted as the documented exception), per-hour SCADA limits, limits holding in both
  directions on both days, forward and reverse limits and VOLL shed in a toy network, the backtest
  passing on 11-10 and failing for a model with the network lifted, and the backtest not needing PGO's
  prices.
- `python -m gridbook.cli value --data data --month 2026-11 --out out/valuation_2026-11.csv`
- `python -m gridbook.cli backtest --data data --day 2026-11-10 --out out/backtest_2026-11-10.csv`:
  `BACKTEST PASS`, 192 prices scored, max error $0.0044, 0 outside tolerance, 0 binding mismatches.
- `python -m gridbook.cli dispatch --data data --day 2026-11-17 --out out/dispatch_2026-11-17.csv`:
  360 rows (24 hours x 10 units and 5 load nodes), production cost $1,536,059.91.
- **Independent valuation check.** I re-implemented sections 3 to 9 with exact fractions, straight from
  the CSVs, and compared all 40 values (4 months x 10 paths). Zero mismatches.
- **Independent dispatch check.** I rebuilt each hour's LP from the raw files and solved it with SciPy/HiGHS
  (used only for the check, not by the repo). Optimal cost and all 8 prices per hour agree with the
  engine to about 1e-10, on both days. 383 random stress cases (random loads, availability and limits,
  114 with load shed, 161 element-cases bound in the reverse direction) agree to a relative 1e-13 and
  never exceed a limit in either direction. `lp.py` agrees with brute-force vertex enumeration on 3,000
  random small programs (1,620 solved, 1,380 correctly infeasible).
- **Can the backtest fail?** Putting each old fault back on the corrected engine: 10 m wind gives
  max error $27.00, 142 price misses and 12 binding mismatches; vendor or normal ratings as limits give $14.00,
  49 and 7; lifting all limits fails as well (unit test). One fault is not detected on 2026-11-10: a limit
  enforced in one direction only passes, because that day never binds in reverse. The unit tests
  above cover it.
- **Effect of each valuation fix alone** (reverting one on the fixed engine and re-running): V1 moves the
  H-1026 spreads of the Metro-endpoint paths by 28.10; V2 moves H-1026 spreads by up to 5.41; V3 moves
  H-1026 spreads by up to 9.05 and November values by up to 22.88; V4 changes five November values by 6.56
  to 9.68 and no earlier month; V5 changes two October values (P03 by 5.03, P10 by 1.97) and no November value.

## 5. Things I decided that the documents leave open

- A monitored element with SCADA status `OUT` has a limit of 0 (nothing can flow), and a missing
  or null SCADA limit for a monitored element stops the run with an error. Neither occurs in the current
  data. Silently falling back to the vendor's ratings is what caused D2.
- The model "binds" an element when the optimal dispatch's flow is within 0.5 MW of its limit
  (rules section 7). When two dispatches cost the same the rules call either correct, so in principle a
  tie could change which hours show as bound. On 2026-11-10 it does not.
- The shadow prices of the constraints PGO published (22.58 in hour 7, 9.72 in the others) are not part of the
  pass test and are not scored.
