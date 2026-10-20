# Amendment No. 3 — implementation notes

For the Agent's field examiner and Larkspur Treasury. Covers how `bbcalc` implements Amendment No. 3
(`docs/amendment_no_3.md`), the judgment calls made, the reconciliation to the field examiner's July
2026 recomputation, and exactly what was run to verify the change.

## September 2026 certificate (due to the Agent October 20, 2026)

Written to `out/2026-09_certificate.json` by `py -3 -m bbcalc.cli data/2026-09 --out out/2026-09_certificate.json`.

| Line | Amount |
|---|---:|
| Gross Accounts | 12,838,902.92 |
| less affiliate (c) | 191,516.11 |
| less foreign (d) | 234,364.12 |
| less special_terms (g) | 125,465.00 |
| less past_due (a) | 353,201.73 |
| less cross_age (b) | 67,225.90 |
| less contra (e) | 64,900.00 |
| less concentration (f) | 0.00 |
| **Eligible Accounts** | **11,802,230.06** |
| Accounts availability (85%) | 10,031,895.55 |
| Eligible Inventory | 7,908,331.77 |
| Inventory availability — least of 55% (4,349,582.47), 85% x NOLV 0.66 (4,436,574.12), cap | **4,000,000.00** |
| Reserve: customs_duties | 42,000.00 |
| Reserve: rent | 185,000.00 |
| Reserve: dilution — 11,802,230.06 x (0.071 - 0.05) | 247,846.83 |
| **Borrowing Base** | **13,557,048.72** |
| Revolving Exposure | 11,100,000.00 |
| **Availability** | **2,457,048.72** |

For context only: the pre-change code produces Availability of 2,855,853.19 for September, so the
amended terms reduce September Availability by 398,804.47.

## Provision by provision

The terms that apply depend on the certificate's `as_of` date. That switch lives in one place,
`bbcalc/agreement.py`. All rule changes are keyed off it.

| Provision | Where implemented | Notes / judgment calls |
|---|---|---|
| **s.2(a)** Clause (a): more than 90 days after the original invoice date **or** more than 60 days after the original due date | `bbcalc/receivables.py`: `is_past_due`, `original_due_date`, `days_past_due`, `DUE_DATE_LIMIT_DAYS` | "More than 60 days" means 61 or more calendar days after the original due date, counted as of `as_of`. The due date is worked out from the `terms` code (data dictionary): `NETn` and `x/y NETn` give invoice date + n; `NETn EOM` gives the last day of the invoice month + n; `DUE_ON_RECEIPT` gives the invoice date. A terms code the code doesn't recognise raises an error instead of being guessed. |
| **s.2(g)** "original due date" — without giving effect to any extension, rebilling or modification | `original_due_date` | `extended_due_date` is never read in eligibility. September has two extended invoices, both Saltmarsh Seafood (C1026). INV-2609-00667 ($12,675.25) is 67 days past its original due date of 2026-07-25 and is ineligible even though it was extended to 2026-10-01. INV-2609-00666 ($10,220.00) is 57 days past its original due date, so it is eligible whichever date is used. |
| **s.2(b)** Clause (b): cross-aging threshold 50% → 35% | `cross_aged_customers`, `CROSS_AGE_THRESHOLD_AMENDED` | Clause (b) refers to Accounts "ineligible under clause (a) above". The numerator therefore uses **amended** clause (a), which includes the due-date test. The denominator is unchanged: all Accounts of that Account Debtor (`customer_id`). The test is "more than" 35%, so exactly 35% passes. |
| **s.2(c)** Clause (f): 35% limit for an Investment Grade Account Debtor | `concentration_excess`, `is_investment_grade`, `INVESTMENT_GRADE_SCHEDULE`, `SP_RATING_SCALE` | Investment grade means **both** listed on Schedule 1.01(c) (matched on `legal_name` exactly) **and** an S&P rating of BBB- or higher (`sp_rating` as of `as_of`). Blank, `NR` or an unrecognised rating is not investment grade. Only Bluestem Foods Corporation (C1004, A-) and Carrow Industrial Supply Co. (C1011, BBB-) qualify. Bluestem Farms Cooperative (C1013, A) and Halvorsen (C1012, BBB) are rated but not on the schedule, so they stay at 20%. *Judgment call:* an affiliated group gets 35% only if every member with Accounts in the base is investment grade; a mixed group stays at 20%. No group is mixed today, so this has no effect on the numbers. The 35% cap is rounded to the cent, the same way as the existing 20% cap. |
| **s.2(d)** New clause (g): bill-and-hold, guaranteed sale, sale-or-return, sale on approval, consignment, progress billing | `is_special_terms`, `SPECIAL_TERMS_INVOICE_TYPES` (`BH`, `GS`, `SOR`, `SOA`, `CNS`, `PB`); new category `special_terms` | `SVC` (services billed: installation, maintenance, freight handling) and `STD` are not any of the listed arrangements, so clause (g) does not exclude them. **This is where we differ from the Agent's July recomputation (see below).** *Judgment call:* each ineligible dollar goes to one category, and `special_terms` is checked after `foreign` and before `past_due`. That is the Agent's own order in its July file. The order only decides which line a dollar appears on; total Eligible Accounts is the same whatever the order. For pre-amendment months the category list is the original one (`INELIGIBLE_CATEGORIES`, unchanged), so there is no `special_terms` key. |
| **s.2(e)** Borrowing Base clause (b): least of 55% of Eligible Inventory, 85% x NOLV x Eligible Inventory, and $4,000,000 | `bbcalc/inventory.py`: `inventory_availability(..., as_of=)`, `INVENTORY_ADVANCE_RATE_AMENDED`, `INVENTORY_AVAILABILITY_CAP` | The cap is compared against the two cent-rounded legs. It binds in September (4,000,000.00 against 4,349,582.47 and 4,436,574.12). The definition of Eligible Inventory is not amended and is unchanged. |
| **s.2(f)** Reserves shall include the Dilution Reserve; **s.2(g)** "Dilution Ratio", "Dilution Reserve" | `bbcalc/reserves.py`: `dilution_reserve`, `compute_reserves(period, eligible_accounts=None)` | Dilution Reserve = cents(Eligible Accounts x (Dilution Ratio - 0.05)), and zero if the ratio is 0.05 or less. The ratio is `period.json` `dilution_ratio`, which the data dictionary describes as the ratio "most recently notified by the Agent after a field exam" (0.071 for September). The reserve is computed on Eligible Accounts **as shown on the certificate**, after every clause including (f). It is shown as its own line, `dilution`, which is the Agent's line name, after the Agent-notified reserves. The line appears even when it is 0.00. If the ratio is missing, or if `agent_reserves` already has a `dilution` line, the run stops with an error rather than leaving the reserve out or counting it twice. |
| **s.3** Effective July 1, 2026, for month-ends on or after that date. Earlier months, including re-deliveries, stay on the old terms. | `bbcalc/agreement.py`: `amendment_no_3_applies(as_of)` (`as_of >= 2026-07-01`) | Fiscal months end on the last day of the calendar month (s.5.01(d)). July 2026 is therefore the first amended month, and June 2026 and every earlier month are computed exactly as before. |
| **s.3 proviso** Dilution Reserve only for fiscal months ending on or after September 30, 2026 | `dilution_reserve_applies(as_of)` (`as_of >= 2026-09-30`) | July and August 2026 use the amended eligibility and inventory terms but carry no Dilution Reserve. |
| s.1, s.4 | — | No computational effect. |
| AR aging summary | unchanged (`aging_summary`) | Still by days from invoice date in 30-day buckets, whatever eligibility test applies (README). It ties to the Agent's July aging on all four buckets. |

## July 2026: reconciliation to the field examiner's recomputation

We do **not** tie to `data/2026-07/agent_recomputed_certificate.json`. We agree on every line except
those that follow from two items. Both are positions to take up with the Agent before October 20.

**Lines that tie to the cent:** gross accounts; affiliate 192,792.92; foreign 229,083.20; past_due
492,152.91; cross_age 65,860.40; contra 58,400.00; concentration 0.00; gross, ineligible and eligible
inventory; inventory availability 3,627,331.65; rent and customs_duties reserves; revolving
commitments; revolving exposure; all four aging buckets.

**Lines that differ:**

| Line | bbcalc | Agent | Difference |
|---|---:|---:|---:|
| special_terms | 98,020.00 | 112,470.00 | 14,450.00 |
| total_ineligible_accounts | 1,136,309.43 | 1,150,759.43 | 14,450.00 |
| eligible_accounts | 10,103,357.52 | 10,088,907.52 | (14,450.00) |
| accounts_availability | 8,587,853.89 | 8,575,571.39 | (12,282.50) |
| reserves: dilution | — (none) | 211,867.06 | 211,867.06 |
| total_reserves | 227,000.00 | 438,867.06 | 211,867.06 |
| borrowing_base | 11,988,185.54 | 11,764,035.98 | (224,149.56) |
| availability | 1,638,185.54 | 1,414,035.98 | (224,149.56) |

**Bridge, bbcalc → Agent Availability:** 1,638,185.54 - 12,282.50 (item 1, 85% x 14,450.00) - 211,867.06
(item 2) = 1,414,035.98. Applying exactly these two Agent positions to `bbcalc` reproduces every line of
the Agent's file to the cent (test `test_agent_positions_reproduce_agent_file_exactly`). There is no
third difference.

1. **Services invoice treated as clause (g).** The Agent's `special_terms` of 112,470.00 is our 98,020.00
   (INV-2607-00639 bill-and-hold 41,720.00 + INV-2607-00640 progress billing 56,300.00) plus
   INV-2607-00641, Aldergrove Market Co. (C1001), dated 2026-07-16, NET30, $14,450.00, type `SVC`.
   Clause (g) lists bill-and-hold, guaranteed sale, sale-or-return, sale on approval, consignment and
   progress billing. Services billed is none of these, and nothing else in
   `docs/credit_agreement_excerpts.md` excludes services Accounts. The invoice is not past due or
   otherwise ineligible, so `bbcalc` treats it as eligible.
   *Caveat:* I have seen only the data extract, not the invoice or the services contract. If Treasury
   finds these services are in substance billed in stages (progress billing), or the Agent cites a
   provision not reproduced in `docs/`, the Agent's treatment would be right. **September exposure:**
   September has two `SVC` invoices, INV-2609-00661 ($15,880.00) and INV-2609-00662 ($27,310.00). If the
   Agent's position prevails, September Availability falls by 35,804.51, to 2,421,244.21 (Eligible
   Accounts 11,759,040.06; Dilution Reserve 246,939.84).
2. **Dilution Reserve included in July.** The Agent's figure is 10,088,907.52 x (0.071 - 0.05) =
   211,867.06, which is the right formula. However, the Section 3 proviso includes the Dilution Reserve
   "only for fiscal months ending on or after September 30, 2026", and July 31, 2026 falls before that.
   `bbcalc` carries no Dilution Reserve for July. This item has no effect on September, where both
   views include the reserve.

**Related open items for Treasury (not checked — the data isn't in this repository):**
- I have not seen the July 2026 certificate as delivered. If it came from the pre-change code, it was
  computed on pre-amendment terms (that code gives July Availability of 1,234,362.76). The amended
  figure is 1,638,185.54.
- No August 2026 data is in `data/`, so August was not recomputed. Amended terms apply to August
  (without the Dilution Reserve).
- Carrow Industrial Supply Co. is rated exactly BBB-, the investment-grade floor. In September its
  Accounts are 20.93% of the clause (f) base. Without the 35% limit, 110,211.46 would be ineligible
  and Availability would be 91,365.30 lower. `sp_rating` is maintained by Treasury for
  credit-insurance purposes. The Agent may want to confirm the S&P ratings independently.

## Pre-amendment months

June 2026 (and any month ending before July 1, 2026) computes exactly as before.
`py -3 -m bbcalc.cli data/2026-06 --json` matches `data/2026-06/expected_certificate.json` text for text.
The June bill-and-hold invoice INV-2606-00601 ($38,250.00) stays eligible, and there is no
`special_terms` key and no `dilution` line.

## Backward compatibility (Treasury scripts importing `bbcalc.receivables`, `.inventory`, `.reserves`)

- Every existing public function keeps its parameters, in the same order. New parameters are
  optional keywords only: `concentration_excess(..., as_of=None)`,
  `inventory_availability(..., as_of=None)`, `compute_reserves(period, eligible_accounts=None)`.
  Existing constants keep their names and values; `INELIGIBLE_CATEGORIES` is still the
  pre-amendment tuple. New names: `INELIGIBLE_CATEGORIES_AMENDED`, `ineligible_categories(as_of)`,
  `original_due_date`, `days_past_due`, `is_special_terms`, `is_investment_grade`, `dilution_reserve`.
- *Judgment call:* functions that **take a date** follow the terms in force on that date:
  `is_past_due`, `cross_aged_customers`, `compute_eligible_accounts`, and `compute_reserves` (via
  `period.as_of`). Calls with pre-July 2026 dates return what they always did. Calls with later dates
  return amended results. In practice: `compute_eligible_accounts` returns a `special_terms` key, and
  `compute_reserves(period)` for September 2026 onward returns a `dilution` line, which it computes
  itself if `eligible_accounts` isn't passed.
- *Judgment call:* functions that **take no date** (`inventory_availability`, `concentration_excess`)
  keep the pre-amendment result when `as_of` is omitted, so undated calls never silently change.
  **Owners of the cash-forecast and covenant workbooks should pass `as_of=`** when calling these for
  July 2026 or later; otherwise they get the old 50% inventory leg (no $4M cap) and a flat 20%
  concentration limit.

## What was run to verify, and the results

All commands were run from the repository root, with Python 3.14.5 on Windows (`py -3`). Python 3.14.5 is the
only interpreter installed here, so the README's "Python 3.9+" was not run-tested. The new code uses
no syntax newer than 3.9: no `X | Y` annotations, no `match`, and no built-in generics.

1. `py -3 -m unittest discover -s tests -v` → **Ran 42 tests, OK.** That is the 9 existing tests,
   unmodified, plus 33 new ones in `tests/test_amendment_no_3.py`:
   - one test class per provision, covering the effective dates, original due date and terms codes,
     the 60-day test, cross-aging at 35%, investment-grade concentration, clause (g), the inventory
     leg and cap, and the Dilution Reserve;
   - the June tie (existing test);
   - the July reconciliation: the only differing lines are the 8 listed above, and applying the two
     Agent positions reproduces the Agent's file exactly;
   - a check of the September figures above.
2. `py -3 -m bbcalc.cli data/2026-09 --out out/2026-09_certificate.json` → wrote the certificate.
   Availability 2,457,048.72.
3. `py -3 -m bbcalc.cli data/2026-06 --json`, compared with `data/2026-06/expected_certificate.json`
   → identical, both as text (with line endings normalised) and as parsed JSON.
4. Ad-hoc independent recomputation, run as a `py -3 -` stdin script and not saved in the repo. It
   rebuilt July and September from the raw CSVs and `period.json` without importing `bbcalc`.
   Result: every ineligibility category (concentration is zero in both), Eligible Accounts, inventory availability, Dilution Reserve, Borrowing
   Base and Availability matched `bbcalc` for both months. July: 10,103,357.52 / 1,638,185.54.
   September: 11,802,230.06 / 13,557,048.72 / 2,457,048.72.
5. Ad-hoc backward-compatibility check, run as a `py -3 -` stdin script. It loaded the original
   modules in memory from `git show HEAD:bbcalc/<module>.py` and compared them with the changed code:
   - all old public function signatures are compatible and all old constants are unchanged;
   - the June certificate re-run as of each of the 181 days from 2026-01-01 to 2026-06-30 matched the
     original code every time (0 mismatches);
   - undated `inventory_availability` and `concentration_excess` calls on July and September data
     gave the same results as the original code;
   - `compute_reserves(period)` matched for July. For September it differs only by the new
     `dilution` line, as intended.

Nothing has been committed. The changes are in the working tree: `bbcalc/agreement.py` (new),
`bbcalc/receivables.py`, `bbcalc/inventory.py`, `bbcalc/reserves.py`, `bbcalc/certificate.py`,
`tests/test_amendment_no_3.py` (new), `README.md`, `CHANGELOG.md`, `out/2026-09_certificate.json`
and this file.
