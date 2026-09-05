"""Production-backed tests for a condition, rule, assignment, or ruleset."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st
from pyspark.sql import types as T

from rules_engine.spark_runtime import (
    ASSIGNMENT_RESULT_STRUCT,
    CONDITION_TRACE_STRUCT,
    MATCHED_RULE_TRACE_STRUCT,
    OPERAND_TRACE_STRUCT,
)

from .. import engine, state
from ..schema import Assignment, Condition, Rule
from .widgets import value_badge

SCOPES = ("Whole ruleset", "One rule", "One condition", "One assignment")


def render() -> None:
    """Render focused and batch production-runtime tests for current data."""
    errors = state.editor_errors()
    if errors:
        st.error("Fix invalid editor values before evaluating: " + "; ".join(errors.values()))
        return
    rows = state.rows()
    if not rows:
        st.info("Upload or enter test data before running the ruleset.")
        return
    try:
        source_schema = engine.sample_schema(rows)
    except (TypeError, ValueError) as exc:
        st.error(f"Sample schema cannot be inferred: {exc}")
        return
    with st.expander("Sample Spark schema", expanded=False):
        st.caption(
            "All scopes use this schema inferred from the full sample dataset. "
            "The production Spark validator checks source fields and assignment types. "
            "Validate again against the actual table schema before deployment."
        )
        st.json(source_schema.jsonValue())
    detail = st.radio(
        "Result detail",
        ("Compact", "Full audit"),
        horizontal=True,
        index=1,
        key="eval_detail",
        help=(
            "Full audit includes matched-rule explanations, resolved conditions, "
            "assignment provenance, overrides, and ruleset identity."
        ),
    )
    full_audit = detail == "Full audit"
    _single(rows, full_audit=full_audit, source_schema=source_schema)
    st.divider()
    _batch(rows, full_audit=full_audit, source_schema=source_schema)


def _single(rows: list[dict[str, Any]], *, full_audit: bool, source_schema: T.StructType) -> None:
    """Run a selected authoring scope against one test row."""
    st.subheader("Inspect one row")
    picker = st.columns([2, 3])
    scope = picker[0].selectbox("Scope", SCOPES, key="eval_scope")
    labels = [_row_label(index, row) for index, row in enumerate(rows)]
    index = picker[1].selectbox(
        "Row",
        range(len(rows)),
        format_func=lambda item: labels[item],
        key="eval_row",
    )
    row = rows[index]
    with st.expander("Input row", expanded=False):
        st.json(_jsonable(row))

    if scope == "Whole ruleset":
        _whole_ruleset(row, full_audit=full_audit, source_schema=source_schema)
    elif scope == "One rule":
        _one_rule(row, source_schema=source_schema)
    elif scope == "One condition":
        _one_condition(row, source_schema=source_schema)
    else:
        _one_assignment(row, source_schema=source_schema)


def _whole_ruleset(row: dict[str, Any], *, full_audit: bool, source_schema: T.StructType) -> None:
    """Render the stable business result from production row evaluation."""
    result = engine.evaluate_row(
        state.draft(), row, full_audit=full_audit, source_schema=source_schema
    )
    if result["error"]:
        st.error(f"Evaluation failed: {result['error']}")
        return
    metrics = st.columns([1, 2, 3])
    metrics[0].metric("Matched", "yes" if result["matched"] else "no")
    metrics[1].metric("Rules matched", len(result["matched_rule_ids"]))
    metrics[2].markdown(
        "**Rules, in order** "
        + (", ".join(f"`{rule_id}`" for rule_id in result["matched_rule_ids"]) or "—")
    )
    _assignment_result_table(result["assign"])
    if full_audit:
        _full_audit(result)


def _one_rule(row: dict[str, Any], *, source_schema: T.StructType) -> None:
    """Run one selected rule through the production condition runtime."""
    rules = state.draft().ordered_rules()
    if not rules:
        st.caption("No rules are available.")
        return
    rule = st.selectbox(
        "Rule",
        rules,
        format_func=lambda item: f"{item.rule_order} · {item.rule_id}",
        key="eval_rule",
    )
    try:
        outcome = engine.evaluate_rule(
            rule, row, ruleset=state.draft(), source_schema=source_schema
        )
    except engine.FocusedEvaluationSkipped as exc:
        st.warning(str(exc))
        return
    except engine.OperandError as exc:
        st.error(str(exc))
        return
    st.success("Matches.") if outcome["matched"] else st.warning("Does not match.")
    traces = []
    for trace in outcome["condition_trace"]:
        left = trace.get("left") or {}
        right = trace.get("right") or {}
        traces.append(
            {
                "condition_id": trace.get("condition_id"),
                "passed": trace.get("passed"),
                "operator": trace.get("operator"),
                "left": left.get("value"),
                "right": right.get("value"),
                "comparison_result": trace.get("comparison_result"),
                "left_default_applied": left.get("default_applied", False),
                "right_default_applied": right.get("default_applied", False),
            }
        )
    st.dataframe(_display_frame(pd.DataFrame(traces)), width="stretch", hide_index=True)
    if outcome["matched"]:
        _plain_assignment_table(outcome["assign"])


def _one_condition(row: dict[str, Any], *, source_schema: T.StructType) -> None:
    """Run one selected condition and expose its production trace values."""
    items = _all_conditions()
    if not items:
        st.caption("No conditions are available.")
        return
    _, rule, condition = st.selectbox(
        "Condition",
        items,
        format_func=lambda item: item[0],
        key="eval_condition",
    )
    try:
        result = engine.evaluate_condition(
            condition,
            row,
            ruleset=state.draft(),
            owning_rule=rule,
            source_schema=source_schema,
        )
    except engine.FocusedEvaluationSkipped as exc:
        st.warning(str(exc))
        return
    except engine.OperandError as exc:
        st.error(str(exc))
        return
    if not result["active_flag"]:
        st.warning(
            "This condition is inactive. Its operands are not evaluated and it returns false."
        )
    st.caption(
        "Condition inspection evaluates the selected condition within its prior-rule context."
    )
    metrics = st.columns([1, 1, 1, 2])
    metrics[0].metric("Passed", "true" if result["matched"] else "false")
    metrics[1].markdown(f"**Left**<br>{value_badge(result['left_value'])}", unsafe_allow_html=True)
    metrics[2].markdown(
        f"**Right**<br>{value_badge(result['right_value'])}", unsafe_allow_html=True
    )
    metrics[3].markdown(
        f"**Comparison result**<br>{value_badge(result['comparison_result'])}",
        unsafe_allow_html=True,
    )
    with st.expander("Production trace", expanded=False):
        st.json(_jsonable(result))


def _one_assignment(row: dict[str, Any], *, source_schema: T.StructType) -> None:
    """Resolve one assignment operand with the production runtime."""
    items = _all_assignments()
    if not items:
        st.caption("No assignments are available.")
        return
    _, rule, assignment = st.selectbox(
        "Assignment",
        items,
        format_func=lambda item: item[0],
        key="eval_assignment",
    )
    try:
        resolution = engine.evaluate_assignment(
            assignment,
            row,
            ruleset=state.draft(),
            owning_rule=rule,
            source_schema=source_schema,
        )
    except engine.FocusedEvaluationSkipped as exc:
        st.warning(str(exc))
        return
    except engine.OperandError as exc:
        st.error(str(exc))
        return
    st.markdown(f"`{assignment.target_field}` = {value_badge(resolution.value)}")
    with st.expander("Production operand trace", expanded=False):
        st.json(_jsonable(resolution.trace or {}))


def _batch(rows: list[dict[str, Any]], *, full_audit: bool, source_schema: T.StructType) -> None:
    """Run the entire ruleset over every uploaded test row."""
    st.subheader("Run all test rows")
    prefix = st.session_state.get(state.PREFIX, "rules_engine")
    try:
        _validate_output_prefix(rows, prefix)
    except ValueError as exc:
        st.error(str(exc))
        return
    results = engine.evaluate_rows(
        state.draft(), rows, full_audit=full_audit, source_schema=source_schema
    )
    frame = _results_frame(rows, results, prefix, full_audit=full_audit)
    matched = sum(1 for result in results if result["matched"] and not result["error"])
    errors = sum(1 for result in results if result["error"])
    metrics = st.columns(4)
    metrics[0].metric("Rows", len(rows))
    metrics[1].metric("Matched", matched)
    metrics[2].metric("Unmatched", len(rows) - matched - errors)
    metrics[3].metric("Errors", errors)
    st.dataframe(_display_frame(frame), width="stretch", hide_index=True)
    st.download_button(
        "Download evaluated CSV",
        data=frame.to_csv(index=False).encode("utf-8"),
        file_name=f"{state.draft().ruleset_id}_results.csv",
        mime="text/csv",
    )


def _results_frame(
    rows: list[dict[str, Any]],
    results: list[dict[str, Any]],
    prefix: str,
    *,
    full_audit: bool,
) -> pd.DataFrame:
    """Combine input rows and stable production business results."""
    _validate_output_prefix(rows, prefix)
    records: list[dict[str, Any]] = []
    for row, result in zip(rows, results, strict=True):
        record: dict[str, Any] = dict(row)
        for field_name in engine.result_fields(full_audit=full_audit):
            record[f"{prefix}_{field_name}"] = _cell(result[field_name])
        records.append(record)
    return pd.DataFrame(records)


def _validate_output_prefix(rows: list[dict[str, Any]], prefix: str) -> None:
    """Reserve every canonical output name before combining results with source data."""
    if not isinstance(prefix, str) or not prefix.strip():
        raise ValueError("Output column prefix must be non-empty.")
    reserved = {f"{prefix}_{name}".casefold() for name in engine.FULL_AUDIT_FIELDS}
    conflicts = sorted({name for row in rows for name in row if name.casefold() in reserved})
    if conflicts:
        raise ValueError(
            f"Input contains rules-engine output columns for prefix {prefix!r}: {conflicts}. "
            "Choose another output prefix."
        )


def _assignment_result_table(assignments: dict[str, Any]) -> None:
    """Render the production assignment envelope returned by ``evaluate_row``."""
    st.markdown("**Assignments**")
    rows = [
        {
            "field": field_name,
            "applied": result["applied"],
            "value": _cell(result["value"]),
        }
        for field_name, result in assignments.items()
    ]
    if rows:
        st.dataframe(_display_frame(pd.DataFrame(rows)), width="stretch", hide_index=True)
    else:
        st.caption("No assignment targets are defined.")


def _plain_assignment_table(assignments: dict[str, Any]) -> None:
    """Render assignment values returned by a focused single-rule test."""
    if not assignments:
        return
    st.dataframe(
        _display_frame(
            pd.DataFrame(
                [
                    {"field": field_name, "value": _cell(value)}
                    for field_name, value in assignments.items()
                ]
            )
        ),
        width="stretch",
        hide_index=True,
    )


def _full_audit(result: dict[str, Any]) -> None:
    """Render every field in the production full-audit structs."""
    st.markdown("#### Full audit")
    identity = result.get("ruleset") or {}
    identity_columns = st.columns([2, 1, 4])
    identity_columns[0].markdown(f"**Ruleset**  `{identity.get('id', '—')}`")
    identity_columns[1].markdown(f"**Version**  `{identity.get('version', '—')}`")
    identity_columns[2].markdown(
        f"**Content hash**  `{identity.get('content_hash', '—')}` · "
        f"engine `{result.get('engine_version', '—')}`"
    )
    st.caption(
        "Struct fields and Spark types below come directly from the production "
        "rules-engine audit schema."
    )

    st.markdown("**Matched rule trace**")
    matched_rules = result.get("matched_rules") or []
    if not matched_rules:
        st.caption("No rule matched this row.")
    for matched_rule in matched_rules:
        _matched_rule_struct(matched_rule)

    st.markdown("**Assignment provenance**")
    assignment_results = result.get("assignment_results") or []
    if assignment_results:
        _assignment_structs(assignment_results)
    else:
        st.caption("No assignments were applied.")
    with st.expander("Raw full-audit payload", expanded=False):
        st.json(
            _jsonable(
                {
                    field_name: result.get(field_name)
                    for field_name in engine.result_fields(full_audit=True)
                }
            )
        )


def _matched_rule_struct(matched_rule: dict[str, Any]) -> None:
    """Render one matched-rule struct and all of its condition structs."""
    label = (
        f"{matched_rule.get('rule_order', '—')} · {matched_rule.get('rule_id', '—')} · "
        f"{len(matched_rule.get('conditions') or [])} conditions"
    )
    with st.expander(label, expanded=True):
        st.markdown("**Rule struct**")
        _struct_table(
            matched_rule,
            MATCHED_RULE_TRACE_STRUCT,
            exclude={"conditions"},
        )
        conditions = matched_rule.get("conditions") or []
        st.markdown("**`conditions` · Condition structs**")
        if not conditions:
            st.caption("No condition traces were emitted.")
        for condition in conditions:
            _condition_struct(condition)


def _condition_struct(condition: dict[str, Any]) -> None:
    """Render one condition struct and both complete operand structs."""
    outcome = "passed" if condition.get("passed") else "failed"
    label = f"{condition.get('condition_id', '—')} · {outcome}"
    with st.container(border=True):
        st.markdown(f"**Condition struct · `{label}`**")
        _struct_table(
            condition,
            CONDITION_TRACE_STRUCT,
            exclude={"left", "right"},
        )
        st.markdown("**`left` and `right` · Resolved operand structs**")
        left = condition.get("left") or {}
        right = condition.get("right") or {}
        rows = _operand_struct_rows(left, right)
        st.dataframe(_display_frame(pd.DataFrame(rows)), width="stretch", hide_index=True)


def _assignment_structs(assignments: list[dict[str, Any]]) -> None:
    """Render every assignment-result struct field as an ordered audit event."""
    for assignment in assignments:
        disposition = "effective" if assignment.get("effective") else "overridden"
        label = (
            f"{assignment.get('rule_order', '—')} · "
            f"{assignment.get('target_field', '—')} · {disposition}"
        )
        with st.expander(label, expanded=True):
            _struct_table(assignment, ASSIGNMENT_RESULT_STRUCT)


def _struct_table(
    payload: dict[str, Any],
    struct: Any,
    *,
    exclude: set[str] | None = None,
) -> None:
    """Render scalar struct fields in declared production-schema order."""
    rows = _struct_rows(payload, struct, exclude=exclude)
    st.dataframe(_display_frame(pd.DataFrame(rows)), width="stretch", hide_index=True)


def _struct_rows(
    payload: dict[str, Any],
    struct: Any,
    *,
    exclude: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Project a payload through one production struct without losing null fields."""
    excluded = exclude or set()
    return [
        {
            "field": field.name,
            "Spark type": field.dataType.simpleString(),
            "value": _cell(payload.get(field.name)),
        }
        for field in struct.fields
        if field.name not in excluded
    ]


def _operand_struct_rows(
    left: dict[str, Any],
    right: dict[str, Any],
) -> list[dict[str, Any]]:
    """Project both operand payloads through the complete operand struct."""
    return [
        {
            "field": field.name,
            "Spark type": field.dataType.simpleString(),
            "left": _cell(left.get(field.name)),
            "right": _cell(right.get(field.name)),
        }
        for field in OPERAND_TRACE_STRUCT.fields
    ]


def _cell(value: Any) -> Any:
    """Serialize nested production results for CSV-safe table cells."""
    if isinstance(value, (dict, list)):
        return json.dumps(_jsonable(value), default=str)
    return value


def _display_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize mixed audit values before Streamlit converts them through Arrow."""
    return frame.astype("string").fillna("")


def _all_conditions() -> list[tuple[str, Rule, Condition]]:
    """Return selectable conditions in production evaluation order."""
    items: list[tuple[str, Rule, Condition]] = []
    for rule in state.draft().ordered_rules():
        for condition in rule.conditions.walk_conditions():
            items.append((f"{rule.rule_id} · {condition.condition_id}", rule, condition))
    return items


def _all_assignments() -> list[tuple[str, Rule, Assignment]]:
    """Return selectable assignments in production evaluation order."""
    items: list[tuple[str, Rule, Assignment]] = []
    for rule in state.draft().ordered_rules():
        for assignment in rule.assignments:
            items.append(
                (
                    f"{rule.rule_id} · {assignment.target_field or '?'} = "
                    f"{assignment.value.describe()}",
                    rule,
                    assignment,
                )
            )
    return items


def _row_label(index: int, row: dict[str, Any]) -> str:
    """Return a compact select-box label for one test row."""
    if row.get("LoanNo"):
        return f"{index + 1}. LoanNo={row['LoanNo']}"
    first = next(iter(row.items()), (None, None))
    return f"{index + 1}. {first[0]}={first[1]}" if first[0] else f"Row {index + 1}"


def _jsonable(value: Any) -> Any:
    """Recursively normalize production values for Streamlit JSON rendering."""
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
