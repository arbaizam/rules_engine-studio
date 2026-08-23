"""Production-backed tests for a condition, rule, assignment, or ruleset."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from .. import engine, state
from ..schema import Assignment, Condition, Rule
from .widgets import value_badge

SCOPES = ("Whole ruleset", "One rule", "One condition", "One assignment")


def render() -> None:
    """Render focused and batch production-runtime tests for current data."""
    rows = state.rows()
    if not rows:
        st.info("Upload or enter test data before running the ruleset.")
        return
    _single(rows)
    st.divider()
    _batch(rows)


def _single(rows: list[dict[str, Any]]) -> None:
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
        _whole_ruleset(row)
    elif scope == "One rule":
        _one_rule(row)
    elif scope == "One condition":
        _one_condition(row)
    else:
        _one_assignment(row)


def _whole_ruleset(row: dict[str, Any]) -> None:
    """Render the stable business result from production row evaluation."""
    result = engine.evaluate_row(state.draft(), row)
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


def _one_rule(row: dict[str, Any]) -> None:
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
        outcome = engine.evaluate_rule(rule, row)
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
    st.dataframe(pd.DataFrame(traces), width="stretch", hide_index=True)
    if outcome["matched"]:
        _plain_assignment_table(outcome["assign"])


def _one_condition(row: dict[str, Any]) -> None:
    """Run one selected condition and expose its production trace values."""
    items = _all_conditions()
    if not items:
        st.caption("No conditions are available.")
        return
    _, _, condition = st.selectbox(
        "Condition",
        items,
        format_func=lambda item: item[0],
        key="eval_condition",
    )
    try:
        result = engine.evaluate_condition(condition, row)
    except engine.OperandError as exc:
        st.error(str(exc))
        return
    metrics = st.columns([1, 1, 1, 2])
    metrics[0].metric("Passed", "true" if result["matched"] else "false")
    metrics[1].markdown(
        f"**Left**<br>{value_badge(result['left_value'])}", unsafe_allow_html=True
    )
    metrics[2].markdown(
        f"**Right**<br>{value_badge(result['right_value'])}", unsafe_allow_html=True
    )
    metrics[3].markdown(
        f"**Comparison result**<br>{value_badge(result['comparison_result'])}",
        unsafe_allow_html=True,
    )
    with st.expander("Production trace", expanded=False):
        st.json(_jsonable(result))


def _one_assignment(row: dict[str, Any]) -> None:
    """Resolve one assignment operand with the production runtime."""
    items = _all_assignments()
    if not items:
        st.caption("No assignments are available.")
        return
    _, _, assignment = st.selectbox(
        "Assignment",
        items,
        format_func=lambda item: item[0],
        key="eval_assignment",
    )
    try:
        resolution = engine.evaluate_assignment(assignment, row)
    except engine.OperandError as exc:
        st.error(str(exc))
        return
    st.markdown(f"`{assignment.target_field}` = {value_badge(resolution.value)}")
    with st.expander("Production operand trace", expanded=False):
        st.json(_jsonable(resolution.trace or {}))


def _batch(rows: list[dict[str, Any]]) -> None:
    """Run the entire ruleset over every uploaded test row."""
    st.subheader("Run all test rows")
    prefix = st.session_state.get(state.PREFIX, "rules_engine")
    results = engine.evaluate_rows(state.draft(), rows)
    frame = _results_frame(rows, results, prefix)
    matched = sum(1 for result in results if result["matched"] and not result["error"])
    errors = sum(1 for result in results if result["error"])
    metrics = st.columns(4)
    metrics[0].metric("Rows", len(rows))
    metrics[1].metric("Matched", matched)
    metrics[2].metric("Unmatched", len(rows) - matched - errors)
    metrics[3].metric("Errors", errors)
    st.dataframe(frame, width="stretch", hide_index=True)
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
) -> pd.DataFrame:
    """Combine input rows and stable production business results."""
    records: list[dict[str, Any]] = []
    for row, result in zip(rows, results, strict=True):
        record: dict[str, Any] = dict(row)
        for field_name in engine.COMPACT_FIELDS:
            record[f"{prefix}_{field_name}"] = _cell(result[field_name])
        records.append(record)
    return pd.DataFrame(records)


def _assignment_result_table(assignments: dict[str, Any]) -> None:
    """Render the production assignment envelope returned by ``evaluate_row``."""
    st.markdown("**Assignments**")
    rows = [
        {
            "field": field_name,
            "applied": result["applied"],
            "value": result["value"],
        }
        for field_name, result in assignments.items()
    ]
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.caption("No assignment targets are defined.")


def _plain_assignment_table(assignments: dict[str, Any]) -> None:
    """Render assignment values returned by a focused single-rule test."""
    if not assignments:
        return
    st.dataframe(
        pd.DataFrame(
            [
                {"field": field_name, "value": value}
                for field_name, value in assignments.items()
            ]
        ),
        width="stretch",
        hide_index=True,
    )


def _cell(value: Any) -> Any:
    """Serialize nested production results for CSV-safe table cells."""
    if isinstance(value, (dict, list)):
        return json.dumps(_jsonable(value), default=str)
    return value


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
