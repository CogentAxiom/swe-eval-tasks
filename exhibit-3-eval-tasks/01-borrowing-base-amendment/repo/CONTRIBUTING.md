# Conventions

* **Money is `Decimal`, never `float`.** Build amounts with `bbcalc.money.D` from strings.
* **Rounding.** Each certificate line is rounded to the cent (`ROUND_HALF_UP`, `bbcalc.money.cents`)
  at the point the line is computed. Downstream lines are computed from the rounded values. This
  matches the Agent's spreadsheet; differing by a cent is a reconciliation break.
* **Dates.** Ages are measured in calendar days as of the period's `as_of` date, never "today".
* **One category per ineligible dollar.** An invoice that fails several eligibility tests is shown
  once, under the first category in `INELIGIBLE_CATEGORIES` order, so categories sum to the total.
* **Credit Agreement text is the spec.** When code and `docs/` disagree, `docs/` wins. Cite the
  clause you implement in the docstring.
* **Tests:** `python -m unittest discover -s tests`. Add a test for every rule you change.
