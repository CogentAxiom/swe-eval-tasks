# Post-mortem: the October CRR book and the 2026-11-17 cold snap

Ten root causes, five in the valuation and five in the shadow dispatch and its backtest. All ten are
fixed against `docs/METHODOLOGY.md` and `docs/DISPATCH_RULES.md`. One disagreement with Market Risk
remains after the fixes, on P07, and Risk's number is the one that is wrong. The fixed model also fails
its backtest in five hours of 2026-11-10, and in each the model is right: PGO's pricing run had an input
ours did not (a nuclear outage, hours 8-9) or kept an input it should have dropped (the pre-de-rate
import limit, hours 17-19).

## Part 1: CRR valuation

### 1. No knockout inversion (methodology 4.2 b, c)

- **Symptom.** H-1026 knocked out 38% of Metro's load. In the H-1026 scenario the engine had every
  path into Metro gaining (P01 +9.14, P03 +5.27, P10 +7.30); Risk's revaluation has them losing
  (-13.85, -20.13, -7.86).
- **Wrong.** `weather.scenario_bias` applied the demand curve, `w0 + beta * I`, to every region an event
  touched, whatever the event type and outage fraction.
- **Fix.** A hurricane or freeze with `outage_fraction` at or above 0.15 knocks a region out, and its
  bias becomes `w0 - lambda * D`, with no demand term. Below the threshold, and for heat at any outage,
  the demand curve applies. `weather.knocked_out(event)` returns the knocked-out regions.

### 2. Network adjustment had the wrong sign (methodology 6)

- **Symptom.** The methodology's worked example (section 10) values September P01 at 10.62; the engine
  gave 2.79. The difference, 2 x (3.69 + 0.225), is the network term counted with the opposite sign.
- **Wrong.** `network.path_factor` returned `SF(sink) - SF(source)`. A point's congestion price is
  `-SF * mu`, so the path's value is `(SF(source) - SF(sink)) * mu`.
- **Fix.** `SF(source) - SF(sink)`. September P01 is now 10.62.

### 3. The wind term read the 10 m wind (methodology 4.1)

- **Symptom.** November is an inversion month: WEST and PANHANDLE have 11.6 and 12.4 m/s at 100 m,
  above their reference speeds (7.5, 8.0), and 4.2 and 3.8 m/s at 10 m. The engine's wind term was zero.
- **Wrong.** `weather.base_bias` used `wind_10m`.
- **Fix.** `wind_100m`, the fleet's hub height. WEST's November bias is now 0.70 - 1.60 x 4.1 = -5.86.

### 4. Options were valued as the positive part of the expected spread (methodology 8)

- **Symptom.** P05 in November: the engine gave 0.00 before the other fixes; after them the formula
  matters whenever an option's spread is negative in some scenario.
- **Wrong.** `value_paths` computed the obligation value and floored it at zero: `max(0, sum p*S)`.
- **Fix.** `sum p * max(0, S)`: an option pays nothing in a scenario whose spread is negative.

### 5. No import collapse (methodology 6)

- **Symptom.** With 1 to 4 fixed, October's H-1026 spreads still missed Risk's on eight paths, each by
  that path's METRO_IMPORT term. They matched on P09, which has no exposure to METRO_IMPORT, and on
  P07 (below).
- **Wrong.** `_network_adjustment` used each constraint's `binding_probability` in every scenario.
- **Fix.** A constraint whose `import_region` the scenario knocks out has `q = 0` in that scenario: with
  Metro's load gone, Metro's import limit is slack. This applies to every path, whether or not either
  end is in the knocked-out region.

### Where the engine still disagrees with Risk: P07

After the five fixes the engine's H-1026 spread matches `risk/october_revaluation.csv` to the cent on
nine of ten paths. P07 (PGO_HUB_NORTH to PGO_HUB_SOUTH, an obligation) does not: the engine has
**5.10**, Risk has **7.94**, a difference of 2.84.

Risk is wrong. The difference is exactly P07's METRO_IMPORT term,
`(SF(PGO_HUB_NORTH) - SF(PGO_HUB_SOUTH)) x shadow x q = (0.18 - (-0.25)) x 12.00 x 0.55 = 2.838`, which
rounds to 2.84. Risk's spreadsheet left METRO_IMPORT binding on P07 while collapsing it on every other
path. Under methodology section 6, METRO_IMPORT's import region, METRO, is knocked out in H-1026
(outage 0.38, above 0.15), so the constraint does not bind in that scenario for any path, including a
path with neither end in Metro. No consistent rule reproduces Risk's file: a rule that collapses only
for paths with an end in Metro would also leave METRO_IMPORT binding on P04, P05 and P08, which Risk
has collapsed. The engine is not changed to match. Risk should restate P07's realized spread as 5.10.

### November valuation (`out/valuation_2026-11.csv`)

| Path | Type | Value $/MWh |
|---|---|---:|
| P01 | OBL | 1.75 |
| P02 | OBL | 20.18 |
| P03 | OPT | 4.65 |
| P04 | OBL | 27.18 |
| P05 | OPT | 21.88 |
| P06 | OBL | -3.45 |
| P07 | OBL | -4.95 |
| P08 | OPT | 14.50 |
| P09 | OBL | 9.02 |
| P10 | OPT | 25.18 |

The freeze F-1126 knocks out North (outage 0.24), so in that scenario North's bias inverts and
NORTH_IMPORT collapses: the North-sink paths P04 and P05 lose most of their value there, and P09 turns
negative.

## Part 2: the shadow dispatch and the backtest

### 6. The dispatch chased the demand signal (DISPATCH_RULES 4, 6)

- **Symptom.** For 2026-11-17 the dispatch put up to 939 MW on NORTH_IMPORT, 179 MW over SCADA's
  post-contingency limit of 760 MW, in 18 hours. It was the unconstrained merit order in every hour.
- **Wrong.** `dispatch_day` stacked units by cost against total load and never looked at the network.
- **Fix.** Each hour is the linear program of section 6, solved with `gridbook/lp.py`: least cost
  plus $9,000/MWh of shed, balance, availability, and `-limit <= flow <= limit` on every monitored
  element, in both directions.

### 7. Line limits came from the weather feed (DISPATCH_RULES 4)

- **Wrong.** `feeds.line_limits` returned the weather vendor's ambient-adjusted ratings: 1,450 MW on
  NORTH_IMPORT all day, against SCADA's 900 MW before 06:00 and 760 MW after the South-North circuit 2
  outage and the icing de-rate.
- **Fix.** SCADA's `post_contingency_limit_mw`, hour by hour, for monitored elements (those with shift
  factors) whose status is `IN`. The weather feed's ratings are advisory and are no longer read.

### 8. Wind availability read the 10 m wind (DISPATCH_RULES 3)

- **Symptom.** On the inversion nights of 2026-11-17 the 10 m wind is 2.2 m/s, below cut-in, so the
  model had no wind; at 100 m it is 13.0 and 13.5 m/s, rated output, 1,200 MW.
- **Fix.** `wind_100m` on the power curve.

### 9. No load shed (DISPATCH_RULES 5)

- **Wrong.** When the load could not be served, the old dispatch left it unserved and unrecorded, so
  generation no longer equaled load; a linear program without a shed variable is simply infeasible.
- **Fix.** A shed variable per load node, bounded by its load, at $9,000/MWh. 2026-11-17 needs none;
  the test data set in `tests/test_fixes.py` does.

### 10. The backtest checked the wrong thing (DISPATCH_RULES 7)

- **Symptom.** `backtest` on 2026-11-10 printed `BACKTEST PASS ... 0 line overloads in 24 hours; LMP MAE
  $18.08`.
- **Wrong.** It passed whenever no flow exceeded `line_limits`, which were the weather ratings, so a
  dispatch that ignored the network passed. Its predicted price was the marginal unit's cost, the same
  at every node, and the price error was printed but never tested.
- **Fix.** The model's price is the change in the hour's optimal cost for 1 MW more load at the node.
  The backtest compares it with PGO's published price at every Settlement Point and hour, and the
  binding constraints with PGO's published ones, as section 7 defines a pass.

### Where the backtest still fails, and why the model is right

With the five dispatch causes fixed, the backtest on 2026-11-10 matches PGO's published prices to the
cent in 19 of 24 hours and fails in five: 8, 9, 17, 18 and 19. I did not change the model to close them.
For each missed hour, `python -m gridbook.cli explain --data data --day 2026-11-10` re-prices the hour
under every single change to the inputs that the day's own records support (each unit out of service;
each monitored element at each limit or rating SCADA or the weather feed gives it) and lists the ones
that reproduce PGO's prices within $0.05 at all eight points.

**Hours 8-9 (08:00 to 09:59): the South nuclear unit, S_NUKE, was out of service, and our data does not
say so.** PGO published $140.00 at every point in hour 8 and $137.78 in hour 9, with no constraint
binding; the model, with S_NUKE's 900 MW available, has $62.00 at LZ_NORTH and $55.00 at PGO_HUB_SOUTH,
with NORTH_IMPORT binding. Taking S_NUKE out of service reproduces both hours to the cent, and no other
single unit outage or limit does. `data/dispatch/units.csv` and the SCADA feed carry no unit status, so
this is an outage PGO had and the desk's inputs lacked: a forced outage to confirm with PGO, not a model
error.

**Hours 17-19 (17:00 to 19:59): PGO priced with the stale NORTH_IMPORT limit, 820 MW, instead of the
600 MW de-rate.** SCADA shows NORTH_IMPORT's post-contingency limit at 820 MW until 16:59 and 600 MW from
17:00 ("icing de-rate from 17:00"). PGO's published prices for hours 17-19 are the 820 MW prices: in hours
18-19 LZ_NORTH is $62.00 (N_GAS marginal) where the de-rated network needs the North peaker and prices
$145.00, and the explain run finds NORTH_IMPORT at 820 MW is the only change that reproduces them. Hour 17
alone fits any limit high enough not to bind, 820 among them. From hour 20 PGO's prices are the 600 MW
prices again. PGO's pricing run picked up the de-rate three hours late; the SCADA limit is the right one,
and the backtest should not be made to pass by using the pre-de-rate limit, which would break every later
de-rate.

### The cold snap, 2026-11-17 (`out/dispatch_2026-11-17.csv`)

Production cost $1,536,059.91 and no load shed. NORTH_IMPORT binds at 760 MW in 15 hours, 07:00 through
21:00. Wind runs at 1,200 MW through the inversion nights and 494 MW in the day; the North peaker
N_PEAK runs at 08:00 and 18:00 to 20:00, when North cannot import more.

## Verification

    python -m unittest discover -s tests
    python -m gridbook.cli value --data data --month 2026-11 --out out/valuation_2026-11.csv
    python -m gridbook.cli backtest --data data --day 2026-11-10 --out out/backtest_2026-11-10.csv
    python -m gridbook.cli explain --data data --day 2026-11-10
    python -m gridbook.cli dispatch --data data --day 2026-11-17 --out out/dispatch_2026-11-17.csv

- 25 tests, all pass: the 11 original tests and 14 new ones in `tests/test_fixes.py`, one or more per
  root cause and one for the backtest's two unexplained blocks.
- September P01 is 10.62, the methodology's worked example.
- October in the realized scenario matches Risk's revaluation on nine of ten paths; P07 is Risk's error.
- The backtest on 2026-11-10 reproduces PGO's published prices to the cent at every Settlement Point in
  19 of 24 hours, and its binding constraints in 21. It fails in hours 8-9 (S_NUKE out of service in PGO's
  run, not in our data) and 17-19 (PGO's stale 820 MW NORTH_IMPORT limit); `explain` reproduces each of
  those hours exactly with that one change and no other.
- Every hour of the 2026-11-17 dispatch balances and keeps every monitored element within SCADA's limit.
