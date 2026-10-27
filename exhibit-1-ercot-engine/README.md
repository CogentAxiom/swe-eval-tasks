# The ERCOT CRR Trading Engine

The full system that Tasks 02 and 03 in this package are modeled on: a research and bid-decision engine for ERCOT's Congestion Revenue Rights
auctions. It ingests the market, models congestion in constraint space, prices every path in every auction, grades its
own predictions against settlement, and surfaces the evidence. **It never places a trade.** The human selects, sizes
and submits.

I am its sole architect. Claude Fable 5 began the build with me on 2 July 2026; by the commit record (co-author
trailers), Fable 5 is the co-author on 153 of its 320 commits and Opus on 137 (Opus 4.8 on 120, Opus 5.5 on 17). It
runs unattended every night. Every number below was checked against the repository and its artifacts after the
2026-10-19 nightly run, and each names where it comes from. The portfolio's engine page (`portfolio/engine.html`)
draws the same material as charts. The source is private: it trades a live market, and aspects of the project are
proprietary. Nothing here is code.

**Tour the desk:** [six chapters](desk/README.md) walk through the trading desk tab by tab, with screenshots from the
live desk.

## At a glance

| | |
|---|---|
| Code | 113 pipeline stages (117 stage-pattern modules, 4 of them shared helpers); about 110,000 lines of tracked Python: 83,000 engine and tooling, 27,000 tests, excluding 27,000 lines of vendored reference code; 320 commits since 2 July 2026 |
| Tests | 1,210 test functions in 99 files (1,348 test cases with parametrization), including contract tests that bind claimed capabilities to on-disk artifacts; the full suite runs every night |
| Nightly | 03:30 daily: the full pipeline, then the test suite, then a restart of the trading desk; a 07:00 watchdog checks it. 2026-10-19: 110 of 111 stage runs OK in 438.6 minutes; one stage (fuel mix) failed on a feed timeout; tests 1,344 passed, 1 failed, 3 skipped |
| Desk | a Dash workbench of about 35 tabs (Bid Desk, Constraint Desk, Node Universe, Weather, Forecast Lab, Verification, Trade Explorer, Model Weights, Data Sufficiency, ...) |
| Universe | 1,295 settlement points (1,145 resource nodes), each tracked through its lifecycle; 992 plants (179 GW) mapped to their nearest settlement point; 837 interconnection-queue projects (207 GW) attributed to the nodes they will create |
| Ledger | 6,267,881 CRR transactions, rebuilt from primary auction files, every resale netted |

## Settlement truth: the vendor got it wrong, the engine ties out to actual

ERCOT is the oracle. Before the engine had API access to ERCOT's settlement data, it worked from a commercial SaaS
extract, and the transactions didn't tie. Measured against the ledger's resale chains, the extract booked **$416
million of P&L to holders who had already sold** (January 2024 to June 2026, gross), and its settlement hours disagree
with ERCOT's published calendar in 26 months. The engine rebuilt the market's ledger from ERCOT's primary auction files
and day-ahead prices, corrected the math, and reconciles to ERCOT's own settlement report (Portfolio-Adhoc). The reconciliation is two permanent contract tests; both passed when re-run
read-only on 2026-10-19.

| Tie-out against ERCOT's actual settlement | Engine | ERCOT | Difference |
|---|---:|---:|---:|
| July 2024 (Hurricane Beryl), buy obligations (36,127 positions, counts match exactly) | -$46.46M | -$45.89M | 1.2% |
| July 2024, buy options (74,054 positions, counts match exactly) | -$47.97M | -$47.41M | 1.2% |
| October 2025, monthly-auction buy options (26,258 positions) | $3,472,685 | $3,472,630 | $55 ($50 when the test shipped, 12 July 2026) |

Exact position counts prove the ledger holds the universe ERCOT settled that month.

**What the pre-API vendor extract got wrong:**

- **The calendar.** A CRR settles on hours: weekday peak, weekend-and-holiday peak, off-peak. The hours implied by
  the vendor's own cost lines disagree with ERCOT's published TOU hours in 26 delivery months (33 month-and-bucket
  cells) between May 2022 and May 2026. Holiday peak hours are dropped (16 short in each holiday month, 32 in November
  2024 and November 2025). The November daylight-saving hour is missing from off-peak. October 2022 loses a weekday.
  Off-peak is over-counted by 16 hours in January and May 2026. Its multi-month strips and quarters don't sum to their
  months either (engine backlog, S1c). The engine generates its calendar from the rule, NERC holidays and daylight
  saving included, and refuses to write it unless all 60 months match ERCOT's official workbooks.
- **Resales.** The extract has no sell rows. A CRR resold in a later auction stays listed at full MW under its
  original buyer, so every holder's P&L is wrong by what they had sold. The ledger nets every resale through
  award-linkage chains: all 1,076,132 sells carry their original CRR ID, and 99.2% resolve to the original award.
  Measured against those chains, the extract books P&L on MW already resold of $48M in 2024 (22,881 fully resold
  awards still listed), $174M in 2025 (106,693) and $193M in the first half of 2026 (113,248). Gross figures, as
  absolute P&L on the resold MW; the ledger's resale records begin in August 2023.

**The bug hunt that made the oracle permanent.** I caught a wrong-sign P&L by eye. It traced to three bugs: doubled
hours from overlapping price series, options settled on monthly means instead of the hourly positive part, and sells
settled with the buy sign. All three were invisible to the rank and per-hour validation that existed, because nothing
checked dollar levels. The oracle tests are that level check, and any one of the three breaks them.

**The ledger** (S51, S52): 6,267,881 transactions (3,701,691 from public auction results, 2,566,190 award records from the
pre-API vendor files, joined on verified IDs; the vendor's P&L columns are ignored); 1,076,132 sells, every one chained to its original CRR, so the data contains no naked shorts
and bearish positions are counterflow buys; $744M of auction-to-auction round trips resolved without day-ahead prices;
471 holders, each with a round-trip record computed as of each auction; 5,191,749 positions with full-life P&L,
4,090,257 fully settled.

**A null result kept on record.** Skill-conditioned order flow ("follow the holders who win") was built as 2,117,829
as-of features under a two-clock no-leak contract and tested by ablation: 0 of 40 feature sets improved the replay.
Nothing was wired into any prediction.

**Microstructure as a data guard.** Within one auction the clearing LP enforces option put-call parity exactly (all
7,214 pairs, edge 0.000). The engine turned that into a tripwire: a "parity edge" means corrupted clearing data, not a
trade.

Sources: `tests/test_s31_pnl_oracle.py`, `tests/test_s31_beryl_oracle.py`; `s31/participant_trades.parquet`;
`s51/ledger_summary.json`; `s52/lifetime_summary.json`, `s52/position_lifetime.parquet`; `s01/tou_hours_monthly.parquet`;
the vendor's export files (hours implied by cost / MW / price, de-duplicated across overlapping exports); engine backlog
rows S1c, S31, S51, S52.

## Every variable that moves a congestion price

| Group | What the engine models |
|---|---|
| The network | 1,295 settlement points and their lifecycle (1,052 online, 78 newborn, 61 gone dark); binding-constraint families and shift factors, from which the path value is composed, never fitted per pair; contingencies, stability limits (GTCs) and the transmission outage register; ERCOT's CRR network model each auction |
| Supply and outages | 992 plants with heat rates and marginal costs (a regional merit order); dispatch forecast on weather-driven net load and a scarcity adder; daily NRC reactor status; quiet derates read from SCED disclosures; retirements; coal stocks; gas basis; the interconnection queue |
| Demand and behavior | the seven-day load forecast by region; measured load response to temperature by region and month; load-share regimes |
| Weather, macro to micro | months ahead, climate indices condition the tails; weeks ahead, a sub-seasonal outbreak challenger; days ahead, the live load forecast triggers; storms enter as two knobs |
| The auction itself | the clearing model; fill curves from 4.85M bids (bids above clearing fill 95.7%, at the margin 32.7%); a winner's-curse haircut; put-call parity as a tripwire; clearing-price regime tagged by era |
| Who else is trading | every holder's positions, resales and P&L; informed positioning, bid-time knowledge, follow flags. Read-only and architecturally quarantined from pricing |

## Macro to micro: how a covariate earns its way in

Weather reaches a congestion price through a chain: macro states months ahead (climate indices and ocean temperatures)
size the tails; sub-seasonal drivers own outbreak timing one to three weeks out; the live
forecast triggers; measured behavior converts weather into load; the constraint space prices it.

- **Testing covariates.** The macro scan crossed eight drivers (ONI, Niño 3.4, SOI, AO, NAO, PNA, PDO, AMO) with four
  regions, twelve months, the mean and variance of temperature, and leads of two to four months over 75 years: 2,304
  tests. About 115 false positives were expected at p < .05; 362 came in; 57 survived false-discovery control; 48 also
  held the same sign with |r| >= 0.2 in both halves of the record, against about 3 expected under the null. Which
  drivers, regions and months survived, and how they are used, is not published here.
- **The hindcast gate.** A conditioned forecast must beat the flat climatological one by Brier score over 74-75 years,
  region by region and month by month: 21 of 48 cells win. The cold and wet families (288 cells) and the
  signal-strength split (112 tests) produced no false-discovery survivors and size nothing.
- **Lifting covariates.** Day-ahead basis forecasters take 127 as-of covariates. Replacing hand-picked corridor
  temperatures with each path's own endpoint stations and differentials lifted LightGBM from 12 to 14 trusted corridor
  blocks of 16 (mean skill 0.161 to 0.266) and Chronos-2 from 10 to 13, under a gate of 10% skill over seasonal-naive on
  a three-fold, 14-day walk-forward. The sub-seasonal outbreak model clears no region's gate and stays advisory.
- **Promotion rules: evidence promotes, humans check.** Bid submission stays human, always; promotion belongs to the
  evidence gate. Tier 1, bounded reversible reweights: automatic, a card notifies. Tier 2, component swaps under strong
  gates: automatic after a visible veto window. Tier 3, thin-sample gates or history-rewriting changes: a human check is
  required (an outage signal once passed at 93x out of sample on a tiny sample, and the check caught it). Levers move
  only if a challenger beats the incumbent's rank correlation by at least 0.005 on every one of 14 replayed auctions. A
  CUSUM governor watches 24 streams; outliers go to the tail layer, never the central weights; 5,489 gate events are
  ledgered.

## Scenario analysis: any season, any catastrophe

The event library holds 69 events since 2016: 13 winter freezes, 9 heat waves, 3 off-season heat events, 37 cool fronts
that killed air-conditioning load, and 7 hand-tagged hurricanes. An event is an extreme anomaly against the season (z >=
2, three days, 1,500 MW), its load effect measured through the region-and-month response. The playbook joins each type
to the market's outcome; the receipts are thin and labeled thin.

The mechanisms predict opposite signs. A demand surge (heat dome, freeze) raises the zone and the value of paths that
sink into it, and multiplies through the measured response, so a November freeze is a no-op. A transport loss (lines or
plants out, load intact) raises import congestion. Demand destruction (landfall, evacuation, a cool front) makes the
zone cheap and pays the counterflow. A summer catastrophe can be both, extreme heat lifting demand while a storm takes
out the wires; the knobs are priced separately and the net is shown. Scenario probabilities come from named
climatology (freeze 19.7% for January 2027; hurricane 15.8% and heat dome 13.7% for August 2027), and they move the 95th
percentile, which sizes a bid, more than the mean.

## The weather inversion

Extreme weather usually raises demand and prices. A hurricane or a deep freeze that knocks out delivery does the
opposite, and the engine learned it from a $24.8 million receipt.

- **Beryl (July 2024).** The hurricane destroyed distribution into Houston: 2.7 million customers dark, load collapsed,
  congestion into Houston inverted. Houston-sink CRRs lost $24.8 million in ERCOT's settlement. North → Houston lost
  $8.74 million; the counterflow, Houston → North, made $1.27 million; the exact reverse hub pair (HB_HOUSTON →
  HB_NORTH, peak obligation, +$952k) was the single biggest winner in the Houston complex. Houston → South lost
  $0.34 million.
- **The bug it exposed.** The old event knob applied one sign to every storm, "hurricane = congestion up". That is the
  transmission-loss storm: load intact, imports constrained. Beryl was the demand-destruction storm.
- **The fix (July 2026).** Two independent knobs per event. A transmission and generation derate raises import
  congestion. A load haircut for distribution damage, evacuation and demand destruction lowers the zone and raises
  counterflow value. The storm slider drives both, anchored on Beryl: a category-1 landfall takes about 42% off the
  region's load, capped at 50%, and an offshore storm counts as zero.
- **The doctrine: Behavioral Response.** "Weather never prices anything directly. BEHAVIOR does." Three receipts:
  Beryl (the opposite sign); Francine, September 2024 (a storm near Houston with no landfall moved load -0.2%: no
  response, no trade); and the U-curve (S54). North Texas load responds at -305 MW per °F in January and +65 in
  November. In cold weeks at least 8 °F below the month's norm, it rose about 5,432 MW in January and about 10 MW in
  November, roughly 540 times less for the same anomaly. A freeze at 100% in November is a contract-tested no-op. Any
  new weather feature must cite a measured behavioral response, or it doesn't ship.
- **Macro.** A 75-year, 2,304-test scan, FDR-controlled and split-half validated, decides which climate signals may
  size tail exposure (see Macro to micro). Event frequency sizes dry powder; only a live forecast triggers.
- **Counterflow screen (S53).** A read-only screen for regional demand shocks; it never moves the core forecast. Its
  trigger and statistics are not published here.
- **Still open, by the engine's own backlog:** re-solving the constraint space with storm outages as contingencies.

Sources: engine decision log (2026-07-09, Behavioral Response doctrine); engine backlog (weather-event sign row, Beryl
counterflow receipt, S54); `s54/load_response.parquet`.

## How it grades itself

The engine ranks verification evidence in tiers: **external oracle (realized day-ahead settlement) > falsification >
invariants > same-author re-derivation**, and calls the last one "tautological — not verification". Every number
carries the rung it earned.

- **Walk-forward gates.** A forecaster is trusted only if it beats seasonal-naive by 10% on holdout; building that gate
  caught a baseline bug that had inflated skills to 0.9. Foundation-model challengers (Chronos-2, and Kronos on its own
  runtime) never overwrite the baseline.
- **Humans sign the thin ones.** One macro signal was one of 6 stable survivors out of 1,416 tests (about 3 expected
  by chance). It wins its walk-forward hindcast (Brier 0.228 vs 0.242 flat, 45 years) and ships only because I signed it
  (2026-07-26). It abstains whenever its driver is unpublished, and sizes tail exposure only.
- **Live replay (S14, September 2026 auction, 56,471 obligation paths, all settled):** model value against realized
  settlement, Spearman 0.678; top-decile hit rate 73.1% (mean realized profit $2.76/MWh, against -$0.215 for all
  paths). The artifact labels it a diagnostic rebuilt with current pools, not out-of-sample; walk-forward P&L belongs to
  the backtest stage, and the label travels with the number.
- **Daily scorecard (S20, September 2026):** 1,122,390 path-days; mean absolute error $2.54/h; mean error +$0.45/h (the
  model ran pessimistic).
- **Prediction-versus-reality ledger (S97):** every call about a delivery month is scored nightly. Of 961 directional
  calls scored, 655 hit (68%); 26 were refused a score as look-ahead, and the 2026-10-19 run caught 16 more.
- **Refuted, and kept on record:** a forward monthly day-ahead price model lost to persistence out of sample and stays
  advisory.

## Under the hood: solvers, pipelines and invariants

Four pieces of the engine, as its code implements them. The code stays private, except for two short excerpts quoted
verbatim below: the Laplacian solve and the parity tripwire. The math is the code's math, and each receipt is from the
2026-10-19 artifacts.

### S06: graph-Laplacian geolocation (a Dirichlet problem on the transmission graph)

When the build started, only about 288 of some 1,200 settlement points had coordinates. Transmission branches are
geographically short, so a bus sits near the mean of its electrical neighbours, and the unknown positions solve as a
boundary-value problem with buses matched to known coordinates (asset and published points) as the boundary set B:

```
minimize over x_I    sum over branches (i,j) in E  of  (x_i - x_j)^2
subject to           x_k = xhat_k   for every anchor k in B

Laplacian            L = D - W        (W: unweighted adjacency, D: degree; sparse)
interior solve       L_II * x_I = -L_IB * x_B
```

- Restricted to the largest connected component (islands make L singular).
- `x_I = spsolve(L_II, -L_IB @ x_B)`, one sparse solve for latitude and one for longitude.
- Estimates are tagged and never overwrite a real coordinate (published point > asset centroid > estimate).
- Receipt: 923 settlement points placed, 872 through ERCOT's official settlement-point-to-bus mapping and 51 by name
  prefix.

Verbatim excerpt, `engine/stacks/s06_geo_interpolation.py` lines 124-139 (indentation removed). Every line is unchanged
since commit 234346e on 2 July 2026, the build's first day: author Jonathan Hurst, co-author Claude Opus 4.8.

```python
A = csc_matrix((vals, (rows, cols)), shape=(n, n))
L = csc_matrix((deg, (range(n), range(n))), shape=(n, n)) - A

interior = ~anchored & (deg > 0)
Lii = L[interior][:, interior].tocsc()
Lib = L[interior][:, anchored]

def solve(anchor_vals: np.ndarray) -> np.ndarray:
    x = np.full(n, np.nan)
    x[anchored] = anchor_vals[anchored]
    rhs = -Lib @ anchor_vals[anchored]
    x[interior] = spsolve(Lii, rhs)
    return x

lat = solve(anchor_lat)
lon = solve(anchor_lon)
```

### S07d: DC power flow and exact shift factors, with a sign guard

The auction network model (PSS/E v30 RAW) is parsed. Branches are kept if in service with |x| > 1e-7, the largest
connected component is taken, and the slack bus is removed. Then:

```
B'_ii = sum over branches l touching i of 1/x_l        B'_ij = -1/x_l   for branch l = (i, j)
factor once:          B' = LU                          (sparse LU, scipy splu)
per monitored element m = (a, b):   solve (B')^T y = (e_a - e_b) / x_m
injection shift factor             ISF(m, k) = y_k      (slack ISF = 0)
path P -> Q on m                   SF = ISF(m, Q) - ISF(m, P)        (sink minus source)
```

- The sanity guard: RAW branch orientation is arbitrary relative to the market's monitored direction, so a family's
  sign is a labeling convention. Against published shift factors, 15 of 31 constraint families came out reversed.
  Each family's sign is aligned to the published data (flip where the per-family correlation is negative).
- The physics check is the magnitude: per-family |corr| median 0.90 (interquartile 0.75 to 0.99) over 5,802
  overlapping node and constraint pairs.
- The exact factors replace snapshot ones as a versioned swap; the interface does not change (constraint-space
  doctrine).
- The network model is ECEII under ERCOT Protocol 1.3.2. Model files and per-bus values stay on the machine; only
  derived analytics leave it.

### S33 and S35: next-morning outage pipelines

ERCOT's unplanned resource outage report (NP1-346-ER) lags about three days.

- **S33, the NRC.** The NRC publishes each reactor's power every weekday morning. The engine uses a transport ladder:
  - the live NRC file first. Its firewall intermittently blocks scripted clients, so it gets a short timeout and one
    retry, and every raw file is archived so history outlives the 365-day window;
  - then EIA API v2 daily generator nuclear outages (2007 to present);
  - then archived snapshots.

  The EIA fallback was cross-validated on the June 2026 South Texas unit 2 trip: NRC 0% power equals EIA 100% outage,
  and the ramp-back day matches at 28% out. The four ERCOT units map exactly to their settlement points.
- **S35, TCEQ.** The emission-event database is a ColdFusion application with plain GETs, no pagination and a 50-row
  response cap. It is queried in 4-day windows, newest first, because 7-day windows hit the cap on busy weeks.
  Filings are often dated the day of the event. Power relevance is a scored candidate, never asserted: a token match
  against outage resource names plus power keywords. Generic tokens are barred after real false matches ("UNIT1",
  "SOUTH"). On 2026-10-19: 1,353 filings, 1,023 incidents, 45 power candidates.
- Both are annotation-tier. They flag the desk and feed no price until they pass the Tier-2 gate (out-of-sample lift
  and falsification).

### S12b: put-call parity as a clearing-data tripwire

```
OBL(P->Q) + OPT(Q->P)  pays  s + max(0, -s) = max(0, s) = OPT(P->Q)       for every hourly spread s
edge = premium OPT(P->Q) - [ clearing OBL(P->Q) + premium OPT(Q->P) ]  =  0   within one auction
```

- Within one auction the clearing LP prices all three legs jointly, so no-arbitrage forces the edge to zero.
- May 2026: all 7,214 pairs cleared at 0.000. For example, HB_SOUTH -> HB_WEST: obligation -4.952 plus reverse option
  10.747 equals 5.795, the direct option.
- The October 2026 auction: 7,851 pairs, largest edge 0.000.
- A contract test asserts that at least 99% of pairs sit within $0.01. A break means corrupted clearing data (a wrong
  auction mixed in, hedge types crossed, units broken), never a trading opportunity.

Verbatim excerpt, `tests/test_s12b_parity.py` lines 44-49, inside `test_within_auction_no_arbitrage_receipt()`
(indentation removed). Unchanged since commit 91707e1 on 9 July 2026: author Jonathan Hurst, co-author Claude Opus 4.8.
It runs in the nightly suite and passed when re-run on 2026-10-19.

```python
frac = duckdb.connect().sql(f"""
    SELECT avg(CASE WHEN abs(parity_edge) <= 0.01 THEN 1.0 ELSE 0 END)
    FROM parquet_scan('{p}')""").fetchone()[0]
assert frac >= 0.99, (
    f"within-auction parity broken on {(1-frac)*100:.1f}% of pairs — "
    "clearing data corrupted, not a trading opportunity")
```

## Architecture: what the stages do

| Family | Stages (selected) | What they do |
|---|---|---|
| Ingestion | S00 registry; S01 catalog, auction results, shadow prices, CRR network model, secure feeds, TOU calendar, day-grain healing; S05 live signal and binding constraints; S64 DAM disclosure; S67 real-time prices | Every stack declares its inputs; a missing critical one is a banner on the desk. Partitions over 1% null are refused; completeness is checked by day |
| Universe | S02, S06, S69 | Node lifecycle; does each path still exist, and did the grid grow a node we don't model |
| Constraint space | S07a constraint families, S07b shift factors, S07d network, S07e contingencies, S07f stability limits, S07g/h shift-factor blend and basis | The coordinate system: nodes and constraint families, never pairs; hourly atomic |
| Outages and supply | S24, S29, S33 NRC reactor status, S34 queue and node births, S35, S36, S37 retirements, S38 quiet derates, S41 transmission outages, S42 coal, S44 gas basis, S46 merit order, dispatch forecast, scarcity, S50 node-failure indicators | Forced outages and contingencies enter the network side; who runs, at what cost, and when they are down |
| Weather, demand, macro | S03, S43 load forecast, S53 counterflow, S54 U-curve, S56 surprise-event library, S57 conditional tails, S60 sub-seasonal challenger, S65 load regimes | Scenario mixtures, never point biases; tails move sizing |
| Forecast and calibration | S04, S08 calibration, LightGBM quantiles, option payoff, S48-S49 challengers, S68 forward DAM price | Each earns its `trustworthy` flag walk-forward |
| Clearing and bidding | S09 clearing, fills, adverse selection, S10 haircuts, S12 candidates and optimizer, S13 bid economics, S27, S40, S47, S59, S61 | You pay the clearing price; you clear exactly when the crowd valued the path lower; the optimizer decides nothing |
| Scenarios and attribution | S16, S17 residual atlas, S18 model weights, S21 driver attribution | Unexplained variance becomes named residual series, never smeared into weights |
| Validation | S14 replay, S19 outcomes, S20 scorecard, S22 backtest with outlier naming, S55 regime governor, S97 prediction ledger | Components keep earning their place, or the governor demotes them |
| Ledger and settlement | S51 ledger and flow ablation, S52 lifetime P&L, S66 whole-book QSE P&L | Every transaction, resale-netted, tied out to ERCOT's settlement |
| Participants (the edge) | S15, S23 informed positioning, S24, S25 bid-time knowledge, S26 entity registry, S31 participant P&L, S32 follow flags, S62, S63 | Who trades, who might know something, whose trades to follow; read-only annotation, quarantined: nothing in S7, S9, S12 or S13 imports it, and removing it is a documented delete-list |
| Operations | S98 vintage archive, S99 freshness, S99a backup | The 24-hour freshness guarantee, provable per artifact |

Stack: Python, Polars and DuckDB over Parquet, LightGBM with conformal calibration, cvxpy with HiGHS, Dash.

## Contracts and governance

The founding specification binds seven contracts; several exist because an earlier agent silently broke the thing they
protect:

1. **Constraint-space doctrine.** Model nodes and constraints, never source-sink pairs.
2. **Option valuation contract.** Options are the hourly positive part; option risk is the premium paid.
3. **Clearing-price regime rule.** No structural auction discount assumed; every anchor carries an era tag; backtests
   report pre- and post-RTC+B separately.
4. **Forecasting-model boundary.** A challenger never defines the baseline, never moves clearing cost, never overwrites
   a value, and always shows its own delta.
5. **Awardable-MW non-filter.** Informational columns never filter, rank or drop a candidate.
6. **Weather scenario doctrine.** Weather enters only as a scenario mixture with duration and probability.
7. **Residual doctrine.** One-offs become scenarios, never weights ("Uri is a state with a probability, not a February
   tilt").

Governance for software built with AI agents:

- **Evidence promotes, humans check.** Statistical gates (walk-forward skill against the incumbent, false-discovery-rate
  control, oracle reconciliation, contract tests) promote automatically; humans hold veto, one-click revert and sole
  execution authority. Human conjectures enter only signed, labeled and bannered in red.
- **A dated decision log** every agent session must read before changing behavior, and a completeness matrix with no
  silent "done".
- **Purity tiers.** Model artifacts, annotation, user what-ifs and configuration live in separate trees, and no model
  stage reads annotation or what-ifs.
- **Every numeric claim binds to an artifact**, and failing tests are reported verbatim. The nightly log does the same
  in its own words: "OURS to fix, not external"; "likely upstream holes, not a dead process".

## Bugs caught by validating, now permanent guards

- The missing minus sign in the congestion identity (every path inverted) and a contingency multi-count, both caught by
  the first replay against realized settlement.
- Month names sort alphabetically: `max(auction_name)` pinned the whole engine to May. Artifacts are now selected
  chronologically.
- The operator's archive files carry a leading space in prices: an untrimmed cast made every price null, and
  `greatest(0, NULL) = 0` silently zeroed option payouts. Ingest now strips, and refuses partitions over 1% null.
- A day missing inside a partition reported "32/32 COMPLETE" for four months. Completeness is now checked at day grain,
  nightly.
- A stale correlation (0.87) sat on the desk while the artifact said 0.75. Desk numbers are now read live, never
  copied.
- Doubled hours, monthly-mean options and buy-signed sells, caught by the settlement oracle (above).

## How the tasks in this package relate

The tasks are task-scale models of this engine's work, built in the format Polaris uses: a self-contained repository,
a prompt and a hidden grader, on fictional data. The full methods are on this page.

- **Task 02** (a shadow settlement that doesn't tie) is modeled on the tie-out above, rebuilt at task scale on
  fictional data.
- **Task 03** (CRR weather inversion and a cold-snap dispatch) is modeled on the weather inversion above. It was built
  from the design document of an earlier, superseded build of this engine, on a fictional market. Its oracle is a same-author re-derivation, the tier this
  engine's own brief calls "not verification", and it has no unit-outage feed, which this engine ingests. It shows the
  grading method; this page shows the system.
