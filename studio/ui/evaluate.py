"""Evaluate: try one expression, one rule, or the whole ruleset against sample data."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from .. import engine, state
from ..schema import Assignment, Condition, Rule
from ..text_operands import parse_operand_text
from .widgets import value_badge

SCOPES = ["Whole ruleset", "One rule", "One test", "One assignment", "Ad-hoc expression"]


def render() -> None:
    rows = state.rows()
    if not rows:
        st.info("Add sample data first — the Sample data tab.")
        return

    _single(rows)
    st.divider()
    _batch(rows)
    st.divider()
    _parity(rows)


# --------------------------------------------------------------------------
# one row at a time
# --------------------------------------------------------------------------


def _single(rows: list[dict[str, Any]]) -> None:
    st.subheader("Check one row")

    picker = st.columns([2, 3])
    scope = picker[0].selectbox("What to evaluate", SCOPES, key="eval_scope")
    labels = [_row_label(i, row) for i, row in enumerate(rows)]
    index = picker[1].selectbox(
        "Row", range(len(rows)), format_func=lambda i: labels[i], key="eval_row"
    )
    row = rows[index]

    with st.expander("Row values", expanded=False):
        st.json(_jsonable(row))

    if scope == "Whole ruleset":
        _whole_ruleset(row)
    elif scope == "One rule":
        _one_rule(row)
    elif scope == "One test":
        _one_condition(row)
    elif scope == "One assignment":
        _one_assignment(row)
    else:
        _ad_hoc(row)


def _whole_ruleset(row: dict[str, Any]) -> None:
    full_audit = st.session_state.get(state.FULL_AUDIT, False)
    result = engine.evaluate_row(state.draft(), row, state.functions(), full_audit=full_audit)

    if result["error"]:
        st.error(f"Row quarantined: {result['error']}")
    cols = st.columns([1, 2, 3])
    cols[0].metric("Matched", "yes" if result["matched"] else "no")
    cols[1].metric("Rules matched", len(result["matched_rule_ids"]))
    cols[2].markdown(
        "**Rules, in order** " + (", ".join(f"`{r}`" for r in result["matched_rule_ids"]) or "—")
    )

    st.markdown("**Assigned**")
    assign = result["assign"]
    if not assign:
        st.caption("null — nothing was assigned.")
    else:
        st.dataframe(
            pd.DataFrame([{"field": k, "value": v} for k, v in assign.items()]),
            use_container_width=True,
            hide_index=True,
        )

    if full_audit:
        with st.expander("Full audit detail", expanded=False):
            st.markdown("**assignment_results**")
            if result["assignment_results"]:
                st.dataframe(
                    pd.DataFrame(result["assignment_results"]),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("[]")
            st.markdown("**first_matched_rule_trace**")
            st.json(_jsonable(result["first_matched_rule_trace"]))


def _one_rule(row: dict[str, Any]) -> None:
    rules = state.draft().ordered_rules()
    if not rules:
        st.caption("No rules yet.")
        return
    rule = st.selectbox(
        "Rule", rules, format_func=lambda r: f"{r.rule_order} · {r.rule_id}", key="eval_rule"
    )
    try:
        outcome = engine.evaluate_rule(rule, row, state.functions())
    except engine.OperandError as exc:
        st.error(str(exc))
        return
    st.success("Matches.") if outcome["matched"] else st.warning("Does not match.")
    st.json(_jsonable(outcome["condition_trace"]))


def _one_condition(row: dict[str, Any]) -> None:
    items = _all_conditions()
    if not items:
        st.caption("No tests to evaluate yet.")
        return
    label, rule, condition = st.selectbox(
        "Test", items, format_func=lambda item: item[0], key="eval_condition"
    )
    try:
        result = engine.evaluate_condition(condition, row, state.functions())
    except engine.OperandError as exc:
        st.error(str(exc))
        return

    cols = st.columns([1, 1, 1, 2])
    cols[0].metric("Result", "true" if result["matched"] else "false")
    cols[1].markdown(f"**Left**<br>{value_badge(result['left_value'])}", unsafe_allow_html=True)
    cols[2].markdown(f"**Right**<br>{value_badge(result['right_value'])}", unsafe_allow_html=True)
    with cols[3]:
        st.markdown(f"**Expression**<br>`{result['expression']}`", unsafe_allow_html=True)
        if result["null_result_applied"]:
            st.caption(f"An operand was empty, so the empty-value policy returned {result['null_result_applied']}.")


def _one_assignment(row: dict[str, Any]) -> None:
    items = _all_assignments()
    if not items:
        st.caption("No assignments to evaluate yet.")
        return
    label, rule, assignment = st.selectbox(
        "Assignment", items, format_func=lambda item: item[0], key="eval_assignment"
    )
    try:
        resolution = engine.evaluate_assignment(assignment, row, state.functions())
    except engine.OperandError as exc:
        st.error(str(exc))
        return
    st.markdown(f"`{assignment.target_field}` = {value_badge(resolution.value)}")
    if resolution.children:
        st.caption("Arguments resolved to:")
        st.dataframe(
            pd.DataFrame(
                [{"argument": c.detail, "value": c.value} for c in resolution.children]
            ),
            use_container_width=True,
            hide_index=True,
        )
    st.caption("This shows the assignment on its own. Whether it survives depends on later rules.")


def _ad_hoc(row: dict[str, Any]) -> None:
    st.caption(
        "Type an expression: `field:job_level`, `fn:leaf_key(field:cost_centre|field:job_family)`, "
        "`int:5`, `list:a,b,c`."
    )
    text = st.text_input("Expression", value="field:job_family", key="eval_adhoc")
    if not text.strip():
        return
    try:
        operand = parse_operand_text(text)
        resolution = engine.resolve_operand(operand, row, state.functions())
    except (ValueError, engine.OperandError) as exc:
        st.error(str(exc))
        return
    st.markdown(f"→ {value_badge(resolution.value)}  ·  _{type(resolution.value).__name__}_")


# --------------------------------------------------------------------------
# all rows
# --------------------------------------------------------------------------


def _batch(rows: list[dict[str, Any]]) -> None:
    st.subheader("Run over every row")
    prefix = st.session_state.get(state.PREFIX, "rules_engine")
    full_audit = st.session_state.get(state.FULL_AUDIT, False)

    results = engine.evaluate_rows(state.draft(), rows, state.functions(), full_audit=full_audit)
    frame = _results_frame(rows, results, prefix, full_audit)

    matched = sum(1 for r in results if r["matched"])
    errors = sum(1 for r in results if r["error"])
    cols = st.columns(4)
    cols[0].metric("Rows", len(rows))
    cols[1].metric("Matched", matched)
    cols[2].metric("Unmatched", len(rows) - matched - errors)
    cols[3].metric("Quarantined", errors)

    st.dataframe(frame, use_container_width=True, hide_index=True)

    st.download_button(
        "Download results as CSV",
        data=frame.to_csv(index=False).encode("utf-8"),
        file_name=f"{state.draft().ruleset_id}_preview.csv",
        mime="text/csv",
    )

    if errors:
        st.error(
            "Quarantined rows carry the error text and nothing else — matched is false, "
            "matched_rule_ids is empty, assign is null."
        )


def _results_frame(
    rows: list[dict[str, Any]],
    results: list[dict[str, Any]],
    prefix: str,
    full_audit: bool,
) -> pd.DataFrame:
    ruleset = state.draft()
    records: list[dict[str, Any]] = []
    for row, result in zip(rows, results):
        record: dict[str, Any] = dict(row)
        for key in engine.COMPACT_FIELDS:
            record[f"{prefix}_{key}"] = _cell(result[key])
        if full_audit:
            for key in engine.FULL_AUDIT_EXTRA_FIELDS:
                record[f"{prefix}_{key}"] = _cell(result[key])
        record[f"{prefix}_ruleset"] = json.dumps(
            {"ruleset_id": ruleset.ruleset_id, "version": ruleset.version, "content_hash": None}
        )
        records.append(record)
    return pd.DataFrame(records)


def _cell(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(_jsonable(value), default=str)
    return value


# --------------------------------------------------------------------------
# parity
# --------------------------------------------------------------------------


def _parity(rows: list[dict[str, Any]]) -> None:
    st.subheader("Compact vs full audit")
    st.caption(
        "full_audit is meant to add observability without changing a single decision. "
        "This compares the two modes over the sample rows."
    )
    if not st.button("Compare the two modes"):
        return

    compact = engine.evaluate_rows(state.draft(), rows, state.functions(), full_audit=False)
    audited = engine.evaluate_rows(state.draft(), rows, state.functions(), full_audit=True)

    drift: list[dict[str, Any]] = []
    for index, (left, right) in enumerate(zip(compact, audited)):
        for key in engine.COMPACT_FIELDS:
            if left[key] != right[key]:
                drift.append(
                    {"row": index + 1, "field": key, "compact": left[key], "full_audit": right[key]}
                )

    if drift:
        st.error("The two modes disagree. That is a defect, not a preference.")
        st.dataframe(pd.DataFrame(drift), use_container_width=True, hide_index=True)
    else:
        st.success(
            f"Identical across {len(rows)} rows for error, matched, matched_rule_ids and assign."
        )


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _all_conditions() -> list[tuple[str, Rule, Condition]]:
    items: list[tuple[str, Rule, Condition]] = []
    for rule in state.draft().ordered_rules():
        for condition in rule.conditions.walk_conditions():
            items.append((f"{rule.rule_id} · {condition.describe()}", rule, condition))
    return items


def _all_assignments() -> list[tuple[str, Rule, Assignment]]:
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
    first = next(iter(row.items()), (None, None))
    return f"{index + 1}. {first[0]}={first[1]}" if first[0] else f"Row {index + 1}"


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items() if k not in ("left_resolution", "right_resolution")}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
