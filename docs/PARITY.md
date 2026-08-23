# Preview evaluator vs. the real engine

`studio/engine.py` is a pure-Python reimplementation of the semantics described
in the 0.4.0 audit review. It exists so an author can get feedback in
milliseconds while typing, with no Spark session and no cluster.

It is a drafting aid. A ruleset that behaves correctly in the studio has not
been proven to behave correctly in production.

## What it reproduces on purpose

| Behaviour | Where it comes from |
|---|---|
| Rules run in `rule_order`; inactive rules are skipped entirely | `_build_row_evaluator` filters on `rule.active_flag` |
| Inactive conditions are skipped | only `Rule` and `Condition` carry `active_flag`; `Assignment` does not |
| Assignments merge into one dict, last write wins | plain dict overwrite in the row loop |
| `assignment_results` marks the last write per field effective and names the winner for the rest | `_assignment_results` derives effective/`overridden_by` from the last index per target field |
| `stop_on_match` halts traversal only when the rule matched | the `break` is nested inside `if matched:` |
| An erroring row is quarantined with empty sibling fields | `_base_payload` / `_error_payload` |
| `full_audit` adds observability and changes no decision | both branches share the operand resolution path |
| Output column order: compact fields, then full-audit fields, then `ruleset`, `engine_version` | `_result_struct` filters one ordered list |

The test suite pins each of these, so a change to the studio that breaks one is
caught rather than silently shipped.

## What it does not reproduce

- **Type coercion.** The studio compares Python values. Spark applies its own
  casting rules across mixed numeric and string types, and decimals in
  particular will not match.
- **Null semantics.** `_resolve_null_result` is modelled as a per-condition
  policy defaulting to no-match. That is a guess and needs checking.
- **Custom functions.** The studio calls its own registry
  (`studio/custom_functions.py`), not the engine's. Arity, argument order and
  return types can differ.
- **Schema validation.** No check that a column exists with a compatible Spark
  type, no `column_prefix` collision check against a real DataFrame, no
  worker-serialisability check.
- **Scale.** Row-at-a-time Python over a sample. It is not a performance signal.

## Retiring it

The clean path is to make the real engine the evaluator whenever it is
importable, and keep the preview only as the offline fallback:

1. Add `rules_engine` to `requirements.txt` and detect it at startup.
2. Build a `Ruleset` from the draft's `to_dict()` via the engine's own loader —
   the same path production uses, so schema drift surfaces immediately.
3. Call `evaluate_dataframe(df, ruleset=ruleset, full_audit=..., column_prefix=...,
   fail_on_error=False)` on a Spark DataFrame of the sample rows, then collect.
   `fail_on_error=False` matters: the studio wants to *show* the error row, not
   raise on it.
4. Keep `studio/engine.py` behind a "no Spark session" fallback, and label the
   preview in the UI so nobody mistakes one for the other.

Worth doing at the same time: run both evaluators over the same sample and
report any disagreement. That turns this document into a test.
