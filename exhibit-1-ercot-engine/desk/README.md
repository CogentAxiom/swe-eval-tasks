# The desk, tab by tab

The engine's workbench is a desk of 37 tabs. These six chapters walk through it in the order the work runs: what the
engine stands on, the physics of the grid, who holds what, the forecasts, the decision, and how the engine grades
itself. Each tab gets the question it answers, what it shows, and a screenshot from the live desk in late October
2026. The method behind the tabs is in the [exhibit README](../README.md), and three deep dives go under the desk:
[entity resolution](entity-resolution.md), [the statistics and the gates](statistics-and-gates.md), and
[the nightly run and its repair protocols](nightly-and-self-repair.md).

## The doctrine behind every tab

Every number on the desk comes from a formula, and every formula answers to a rule in the engine's decision log,
enforced by its contract tests. The tabs are where those rules become visible:

- **Constraint space, not pairs.** A path's value is composed, never fitted pair by pair:
  `path_value(A→B, tou) = −Σ_c [SF(sink,c) − SF(source,c)] · E[shadow_price(c, tou)]`, where the expected shadow price
  is how often constraint c binds times how hard. The leading minus is the congestion sign; it was once dropped,
  flipped every book, and a contract test now guards it. 1,967 constraint families stand in for 1.2 million node pairs.
- **Exact physics, checked against ERCOT.** Shift factors come from a DC power flow on ERCOT's own auction network
  model, solved for each forward month. Before a month's model may price anything, the solver must reproduce ERCOT's
  published auction results at R² ≥ 0.99 in every time-of-use block. On the October 2026 auction it reproduces them
  at R² 0.99999 or better.
- **Options are hourly.** `option_value = E[Σ_h max(0, spread_h)]`, never the monthly mean: a day or two of
  volatility can pay a whole month's premium, and a monthly mean erases exactly that.
- **Scenario algebra is linear and exact.** Region multipliers `m_r = 1 + Σ_e p_e (mult_e − 1)` and
  `value_scenario = Σ_r contrib_r · m_r`. Every live what-if re-prices through that dot product, and its residual
  against the full recomputation is regression-checked at exactly zero (0.0 in late October 2026).
- **Weather never prices anything directly; behavior does.** Every weather-to-value signal passes through a measured
  load response, and a weather feature that cannot cite one does not ship (the exhibit's
  [weather inversion](../README.md#the-weather-inversion)).
- **Baselines shrink, and the shrinkage is a column.** Same-month history is shrunk toward all months by how much
  history the month has, and the weight rides every row, so an assumption cannot be forgotten. Every dollar traces to
  one delivery month and a labeled basis.
- **Regimes are flagged.** The 2021–23 era of discounted clearing ended in 2024, and ERCOT's real-time
  co-optimization (live 5 December 2025) is a mandatory flag on every training row.
- **Residuals are named, not absorbed.** Unexplained variance becomes a named variable, then a feature search, then a
  news tag; a one-off event becomes a scenario, never a weight.
- **Label, never drop.** Informational columns never filter, and blank means unknown, never zero.
- **Evidence is ranked.** External oracle (realized settlement) > falsification > invariants > the engine
  re-deriving its own numbers, which does not count as verification. Every model carries a trust flag it must earn on
  holdout.
- **Evidence promotes, humans check.** Statistical gates promote automatically: walk-forward skill against the
  incumbent, falsification under false-discovery control, reconciliation to ERCOT's settlement. Bounded reweights
  apply themselves, component swaps apply after a visible veto window, and thin-sample gates wait for a person. A human
  conjecture is not evidence: it enters only signed, labeled and bannered in red. Bid submission stays human, always.

**And all of it is re-evaluated every night.** The pipeline rebuilds the whole surface, re-fits the fitted models,
and scores them against data they did not see (walk-forward tests) and against what actually settled (backtests and
replays). The original Kronos challenger, last scored in July, is the one model outside that nightly loop. Trust
follows the scores: a component earns its place by beating a baseline and loses it on the run it stops passing, and
an append-only ledger records every flip (6,193 so far). A drift detector watches every component's errors. Even the
judgment calls run on a clock: the engine counts 15 hand-set constants, and any left unchanged for three months gets
a card asking that it be fitted from data or retired. The result is measured where it matters: in the September 2026
replay, the model's top decile of paths realized $2.76/MWh against −$0.22 for all paths. Selection is the edge.

## The chapters

| Chapter | Tabs |
|---|---|
| [1. Data and coverage](01-data-and-coverage.md) | Data Sufficiency, Node Universe, Load Register, Hidden Load, Map, Weather, Live ERCOT |
| [2. Grid physics](02-grid-physics.md) | Constraint Desk, Outage Watch, Dispatch Stack, Radar |
| [3. Who holds what](03-who-holds-what.md) | Entity Map, Participants CRR, Participants QSE, Trade Explorer, P&L Explorer, Follow Trades, Forensics, and the [entity-resolution](entity-resolution.md) deep dive |
| [4. Forecasts and scenarios](04-forecasts-and-scenarios.md) | Drivers, Scenarios, Forecast Lab, Ultra Prediction, Kronos Lab, Model Weights, Signals Research, Tail Hunter |
| [5. The decision](05-the-decision.md) | Bid Desk, Kronos Bid Desk, Kronos II Bid Desk, Bid Desk + Signals, Bid Loader |
| [6. Grading itself](06-grading-itself.md) | Backtest, Verification, Lookback, Feedback |
| Deep dives | [Entity resolution](entity-resolution.md), [the statistics and the gates](statistics-and-gates.md), [the nightly run and its repair protocols](nightly-and-self-repair.md) |

**What the screenshots leave out.** The desk trades a live market, so the tour shows how it works, not what it would
buy.
- The desk's header carries private research dials, so every screenshot starts below the tab strip.
- Company names and holder codes are replaced with aliases, and DUNS numbers and CRR transaction ids are masked,
  before each capture. A capture is refused if any registered name survives.
- Path rankings, bids and the paths themselves are pixelated wherever they would show what the desk favors.
- Four tabs (Hidden Load, Signals Research, Tail Hunter, Feedback) are described without a screenshot, and two more
  are not shown at all, because they carry the desk's edge.
- Seven desk labels that are being corrected were edited out of the screenshots (three in chapter 3, three in
  chapter 5, one in chapter 6), large-load names in chapter 1 are aliased, and local file paths read "[local path]".
