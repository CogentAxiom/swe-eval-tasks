# Deep dive: the nightly run and its repair protocols

The engine rebuilds itself every night without a person in the loop, so the run is built to fail loud, keep its
history, and repair what it can on its own. This page describes the run, the guards around it and the protocols that
fix broken feeds, links and connections. It sits under the [desk tour](README.md); the statistics behind the numbers
are in [the statistics and the gates](statistics-and-gates.md). The description is of the engine's code and
configuration in late October 2026.

## The run

- **03:30, every night.** A scheduled task runs the full pipeline: 117 stages in dependency order. The order is pinned
  by a contract test, so a stage cannot quietly move ahead of an input it reads.
- **One process per stage.** Each stage runs as its own child process on the same interpreter, isolated, while the
  parent holds the pipeline lock. The night's peak memory is the largest single stage, not the sum of everything before
  it, and every stage's peak is logged.
- **Booking that cannot lie.** A stage that returns is OK. A deliberate exit is SKIP. An exception is FAIL, with its
  message. A child that dies without reporting, reports and then exits non-zero, or never exits is FAIL too. Guards
  raise errors rather than exiting, so a guard can never be booked as a skip.
- **No stacking.** An OS-level lock lets only one pipeline run at a time; a second one exits with a distinct code
  instead of competing for memory.
- **Then the tests, then the desk.** The full suite (1,879 test cases) runs after the pipeline in about ten minutes,
  and the trading desk restarts on the fresh artifacts.
- **07:00, a watchdog.** It first checks the real-time price accumulator, unconditionally. Then, if the freshness
  manifest is more than 20 hours old, it reruns the pipeline (the lock prevents overlap) and restarts the desk.
- **Logs that survive.** Every stage writes to its own files, never through a shell pipeline whose reader could die
  and take the stage with it. Each run keeps its own log. Old runs are zipped into an archive, never deleted. A stage
  that normally prints but produced nothing is called out in the log's own words: "its output was LOST, not empty".

## Freshness and sufficiency

- **A 24-hour guarantee.** A freshness stage records every tracked artifact's age against 24 hours, and the desk's pill
  turns when one is older.
- **Every input declared.** The data-sufficiency registry lists every input of every stack with its severity
  (critical, high, info), its status (present, stale, degraded, missing) and what the model loses without it. The
  engine always runs; the desk says which cylinder is down.
- **Content, not file times.** A file rewritten every night can look fresh while its data is months old, so the
  critical inputs are checked by what they contain. For example, the settlement lake's newest delivery date must be
  within three days. An input whose probe fails is treated as stale, never as present.

## History is never lost

- **A vintage archive.** Forecast and decision files are copied every night into a content-addressed, append-only
  archive (SHA-256). An unchanged file costs nothing, and nothing in the archive is ever rewritten. Every forward
  month's bid economics is frozen on every night inside an auction bid window, so any bid night can be rebuilt as it
  was, and live forecast skill can be scored after the fact.
- **Single-copy history is written safely.** Accumulators that nothing else can rebuild are written to a temporary
  file and swapped in atomically, keep their previous version, and refuse any write that would hold fewer rows than
  must survive.
- **Windows merge, revisions are receipted.** Rolling feeds merge new data into their history rather than rewriting
  it, and when a climate index is revised at its source, the engine keeps the old values as dated receipts and the raw
  file by its content hash.
- **Backups to two drives.** Code, history and data are copied inside the pipeline lock, never mirror-deleted.
  ERCOT's restricted network data is excluded from every target except one allowlisted fixed disk, and a test pins the
  rule.

## Repair protocols

The engine expects its sources to break. Each protocol below records the failure, keeps the run going, and either
repairs the gap or says exactly what it limits.

- **A failed feed is recorded, never hidden.** It is marked down with its error, the run continues on the last good
  copy, and the registry and the desk carry the gap.
- **Transport ladders.** The NRC reactor feed falls back to EIA's daily generator outage data, then to archived
  snapshots. The climate-index forecast walks a ladder of sources down to a persistence fallback that labels itself
  collapsed. Nodal prices come from the API or from ERCOT's archive branch, which was proven row-for-row identical to
  the API before it was trusted.
- **Retries that know the difference.** Timeouts, dropped or refused connections, server errors and rate limits are
  retried on a fixed backoff (15, 45 and 120 seconds). A bad request, a missing page or a parse error raises on the
  first attempt, and when retries run out the real error is re-raised, so a dead link costs one attempt and the log
  still names it.
- **Bounded fetching.** The large-load locator holds a stage-wide fetch budget of 15 minutes and a per-document wall
  clock that cuts off a slow-drip server. A body shorter than its declared length is rejected, never cached. A
  document whose text extraction failed is marked and retried after a week instead of every night.
- **Holes diagnosed at the source.** A guard probes every incomplete day of real-time prices at ERCOT, separates days
  ERCOT never posted from days that can be filled, fills those and writes a receipt. A stall it cannot explain
  escalates after 72 hours. In its own words: "likely upstream holes, not a dead process".
- **Whose gap is it.** The day-ahead disclosure lane compares its newest bundle with ERCOT's newest posting every
  night and names the side a gap is on: "OURS to fix, not external", or external, with nothing to fix.
- **Moved pages and refused connections.** In October 2026, two of ERCOT's public listing pages moved, and a state
  regulator's filing site refused the runtime's secure connection. The locator stage recorded each feed down with its
  error and finished. The repair probed the live pages, restored the secure connection with verification kept on, and
  shipped with tests that pin both. The next run fetched all seven regulatory dockets it follows.
- **Sources that relabel themselves.** A forecast source began serving its newest chart under a shifted date. The
  issuance date read from the chart is now cross-checked against its first plotted season, and a future-dated or stale
  issuance is refused.
- **Artifacts that age in the open.** The universe reconciliation refuses to restamp itself for a month it could not
  reconcile, so the freshness pill turns red instead of a month silently vanishing.
- **A universe that keeps up.** Node births are rescanned weekly. A settlement point active in the day-ahead market
  but missing from the modeled universe is itself a registry gap.

## The doctrine in one line

Fail loud, label, never drop: the engine always runs, every gap is named with what it limits, and a number that cannot
be trusted is shown with its reason instead of being silently filled.
