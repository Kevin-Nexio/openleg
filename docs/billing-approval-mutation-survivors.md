# Billing approval mutation survivor classification

Record for the #672 waves (parent #478). The module holds 1,261 mutants in
the configured scope; the honest classification below reflects the waves
that have landed so far.

## Wave 1 (#672 opening): pinned diagnostics and the Swiss local date

Behavior tests in `tests/test_billing_approval.py` kill the seventeen
survivors of the small-function block: every fail-closed refusal of
`prepare_invoice_snapshots` now names its exact German diagnostic — the
invalid issue date, the broken fingerprint shape, the empty and invalid
source-document sequences, both unparsable period markers, the equal-period
window and the mixed date/datetime formats — and the Swiss local default
`today()` returns the Zurich-local date for a late-UTC instant instead of
hosting on whatever clock the process runs on.

## Intentional equivalents

| Mutant | Mutation | Why behavior is unchanged |
| --- | --- | --- |
| `_as_decimal` #5, #6 | Return `Decimal("nan")` or `Decimal("NAN")`. | Python's Decimal parser folds the three spellings to the same quiet non-finite NaN; callers only read `is_finite()`. |
| `_require_order` #2 | `ordered = start < end` instead of `start <= end`. | The equal-window case is refused right after the call by `_require_increasing_window` with the same diagnostic, so no caller accepts the mutant's extra refusal differently. |
