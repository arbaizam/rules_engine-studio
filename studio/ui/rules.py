"""Canonical rule editor arranged as ordered conditions and assignments."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from html import escape
from typing import Any

import streamlit as st

from .. import engine, expressions, state
from ..schema import (
    OPERATOR_NAMES,
    OPERATORS_BY_NAME,
    TOLERANCE_OPERATORS,
    Assignment,
    Condition,
    ConditionGroup,
    Operand,
    Rule,
    assigned_fields,
    new_condition,
)
from .widgets import index_of, operand_editor, value_badge


def render() -> None:
    """Render the selected rule and its production-backed row test."""
    rule = state.selected_rule()
    if rule is None:
        st.info("No rules yet. Add the first one from the rule list on the left.")
        if st.button("Add a rule", type="primary"):
            state.queue(state.add_rule)
        return

    columns = state.columns()
    with st.container(key=f"rule_node_{rule.uid}"):
        st.markdown(
            '<div class="studio-node-label studio-rule-label">Rule</div>',
            unsafe_allow_html=True,
        )
        _header(rule)
        rule_expression_slot = st.empty()
        st.divider()
        _conditions(rule, columns)
        st.divider()
        _assignments(rule, columns)
        with rule_expression_slot.container():
            _expression_expander(
                f"Rule expression · {rule.rule_name or rule.rule_id or 'Untitled'}",
                "Complete rule",
                expressions.rule_expression(rule),
            )
        st.divider()
        _try_it(rule)


# --------------------------------------------------------------------------
# header
# --------------------------------------------------------------------------


def _header(rule: Rule) -> None:
    """Render canonical rule identity, description, order, and flags."""
    top = st.columns([2, 3, 4])
    rule.rule_id = top[0].text_input("Rule id", value=rule.rule_id, key=f"rid-{rule.uid}")
    rule.rule_name = top[1].text_input("Rule name", value=rule.rule_name, key=f"rname-{rule.uid}")
    rule.description = top[2].text_input(
        "Description",
        value=rule.description,
        key=f"rdesc-{rule.uid}",
        placeholder="Plain-language summary for whoever reads this next",
    )

    flags = st.columns([1, 1, 1, 3])
    rule.rule_order = int(
        flags[0].number_input(
            "Runs at", value=int(rule.rule_order), step=10, key=f"rorder-{rule.uid}"
        )
    )
    rule.active_flag = flags[1].toggle(
        "Active",
        value=rule.active_flag,
        key=f"ractive-{rule.uid}",
        help="Inactive rules are skipped entirely and never appear in matched_rule_ids.",
    )
    rule.stop_on_match = flags[2].toggle(
        "Stop on match",
        value=rule.stop_on_match,
        key=f"rstop-{rule.uid}",
        help="When this rule matches, no later rule runs. A non-match never stops evaluation.",
    )
    if not rule.active_flag:
        flags[3].warning(
            "Inactive — this rule is excluded from evaluation.", icon=":material/block:"
        )


# --------------------------------------------------------------------------
# conditions
# --------------------------------------------------------------------------


def _conditions(rule: Rule, columns: Sequence[str]) -> None:
    """Render the nested canonical condition tree for one rule."""
    st.subheader("When")
    st.caption("Rule → root group → nested groups and conditions")
    _group(rule.conditions, None, columns, depth=0)


def _group(
    group: ConditionGroup,
    parent: ConditionGroup | None,
    columns: Sequence[str],
    depth: int,
) -> None:
    """Render one logical group and recursively render child groups."""
    with st.container(border=True, key=f"group_depth_{depth}_{group.uid}"):
        node_label = "Root group" if depth == 0 else f"Nested group · level {depth}"
        st.markdown(
            f'<div class="studio-node-label">{node_label}</div>',
            unsafe_allow_html=True,
        )
        head = st.columns([2, 3, 1, 1, 1])
        group.logical_operator = head[0].selectbox(
            "Match",
            ["all", "any"],
            index=0 if group.logical_operator == "all" else 1,
            format_func=lambda v: "Match all of" if v == "all" else "Match any of",
            key=f"glogic-{group.uid}",
            label_visibility="collapsed",
        )
        group.condition_group_id = head[1].text_input(
            "Group id",
            value=group.condition_group_id,
            key=f"gid-{group.uid}",
            label_visibility="collapsed",
        )
        if head[2].button("Add test", key=f"gaddc-{group.uid}"):
            default = columns[0] if columns else ""
            state.queue(lambda g=group, d=default: g.children.append(new_condition(d)))
        if head[3].button("Add group", key=f"gaddg-{group.uid}", disabled=depth >= 3):
            state.queue(lambda g=group: g.children.append(ConditionGroup(children=[])))
        if parent is not None and head[4].button("Remove group", key=f"gdel-{group.uid}"):
            state.queue(lambda p=parent, g=group: p.children.remove(g))

        group_expression_slot = st.empty()
        if not group.children:
            st.caption("Empty group — matches every row.")

        direct_conditions = [
            child for child in group.children if not isinstance(child, ConditionGroup)
        ]
        nested_groups = [child for child in group.children if isinstance(child, ConditionGroup)]
        for condition in direct_conditions:
            _condition(condition, group, columns)
        for nested_group in nested_groups:
            _group(nested_group, group, columns, depth + 1)
        with group_expression_slot.container():
            _expression_expander(
                f"Group expression · {group.condition_group_id or 'Untitled group'}",
                "Matches when",
                expressions.group_expression(group),
            )


def _condition(condition: Condition, parent: ConditionGroup, columns: Sequence[str]) -> None:
    """Render one canonical condition with operand-level null behavior."""
    with st.container(border=True, key=f"condition_{condition.uid}"):
        st.markdown('<div class="studio-node-label">Condition</div>', unsafe_allow_html=True)
        meta = st.columns([4, 1, 1, 1])
        condition.condition_id = meta[0].text_input(
            "Condition id",
            value=condition.condition_id,
            key=f"cid-{condition.uid}",
            label_visibility="collapsed",
        )
        condition.active_flag = meta[1].toggle(
            "Active", value=condition.active_flag, key=f"cactive-{condition.uid}"
        )
        condition.error_on_null = meta[2].toggle(
            "Error on null",
            value=condition.error_on_null,
            key=f"cerrornull-{condition.uid}",
            disabled=condition.operator in {"is_null", "is_not_null"},
        )
        if condition.operator in TOLERANCE_OPERATORS:
            tolerance = meta[3].text_input(
                "Tolerance",
                value=str(condition.tolerance_abs),
                key=f"ctolerance-{condition.uid}",
            )
            try:
                condition.tolerance_abs = Decimal(tolerance)
            except (InvalidOperation, ValueError):
                st.error("Tolerance must be a finite decimal.")

        cols = st.columns([3, 2, 3, 1])

        with cols[0]:
            operand_editor(
                condition.left,
                f"cl-{condition.uid}",
                columns,
                label="If",
                assigned=assigned_fields(state.draft()),
                in_assignment=False,
            )

        with cols[1]:
            condition.operator = st.selectbox(
                "Test",
                OPERATOR_NAMES,
                index=index_of(OPERATOR_NAMES, condition.operator),
                format_func=lambda name: OPERATORS_BY_NAME[name].label,
                key=f"cop-{condition.uid}",
            )
            if condition.operator in {"is_null", "is_not_null"}:
                condition.error_on_null = False

        spec = OPERATORS_BY_NAME.get(condition.operator)
        with cols[2]:
            if spec is not None and spec.arity == 1:
                st.markdown("&nbsp;", unsafe_allow_html=True)
                st.caption("No value needed.")
            else:
                if condition.right is None:
                    condition.right = Operand()
                operand_editor(
                    condition.right,
                    f"cr-{condition.uid}",
                    columns,
                    label="Compare to",
                    assigned=assigned_fields(state.draft()),
                    in_assignment=False,
                )
                if spec is not None and spec.hint:
                    st.caption(spec.hint)

        with cols[3]:
            st.markdown("&nbsp;", unsafe_allow_html=True)
            if st.button("Remove", key=f"cdel-{condition.uid}"):
                state.queue(lambda p=parent, c=condition: p.children.remove(c))

        _expression_card("Condition expression", expressions.condition_expression(condition))


def _expression_expander(label: str, heading: str, expression: str) -> None:
    """Render a collapsible expression without making it an editing control."""
    with st.expander(label, expanded=False):
        _expression_card(heading, expression)


def _expression_card(heading: str, expression: str) -> None:
    """Render escaped, whitespace-preserving human-readable expression text."""
    st.markdown(
        (
            '<div class="studio-expression-preview">'
            f'<div class="studio-expression-label">{escape(heading)}</div>'
            f'<div class="studio-expression-text">{escape(expression)}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# assignments
# --------------------------------------------------------------------------


def _assignments(rule: Rule, columns: Sequence[str]) -> None:
    """Render canonical assignments emitted when the rule matches."""
    st.subheader("Then set")
    st.caption(
        "Each target may be assigned once per rule. A later matched rule can replace "
        "a value committed by an earlier rule."
    )

    if not rule.assignments:
        st.caption("No assignments yet.")

    for assignment in list(rule.assignments):
        with st.container(border=True, key=f"assignment_{assignment.uid}"):
            st.markdown(
                '<div class="studio-node-label">Assignment</div>',
                unsafe_allow_html=True,
            )
            assignment.assignment_id = st.text_input(
                "Assignment id",
                value=assignment.assignment_id,
                key=f"aid-{assignment.uid}",
            )
            cols = st.columns([2, 4, 1])
            with cols[0]:
                assignment.target_field = st.text_input(
                    "Field to set",
                    value=assignment.target_field,
                    key=f"atarget-{assignment.uid}",
                    placeholder="hierarchy_node",
                )
            with cols[1]:
                operand_editor(
                    assignment.value,
                    f"aval-{assignment.uid}",
                    columns,
                    label="Set to",
                    assigned=assigned_fields(state.draft()),
                    in_assignment=True,
                )
            with cols[2]:
                st.markdown("&nbsp;", unsafe_allow_html=True)
                if st.button("Remove", key=f"adel-{assignment.uid}"):
                    state.queue(lambda r=rule, a=assignment: r.assignments.remove(a))

    if st.button("Add assignment", key=f"aadd-{rule.uid}"):
        state.queue(lambda r=rule: r.assignments.append(Assignment(value=Operand())))

    _override_note(rule)


def _override_note(rule: Rule) -> None:
    """Report targets that can be overwritten by later active rules."""
    ruleset = state.draft()
    mine = {a.target_field for a in rule.assignments if a.target_field}
    if not mine:
        return
    later: list[str] = []
    for other in ruleset.ordered_rules():
        if other.uid == rule.uid or other.rule_order <= rule.rule_order or not other.active_flag:
            continue
        for assignment in other.assignments:
            if assignment.target_field in mine:
                later.append(f"{assignment.target_field} → {other.rule_id}")
    if later:
        st.info(
            "Later rules overwrite: " + ", ".join(sorted(set(later))),
            icon=":material/low_priority:",
        )


# --------------------------------------------------------------------------
# single-rule test
# --------------------------------------------------------------------------


def _try_it(rule: Rule) -> None:
    """Run the selected rule against one test row with production semantics."""
    st.subheader("Try this rule")
    rows = state.rows()
    if not rows:
        st.caption("Add sample data to test this rule.")
        return

    labels = [_row_label(i, row) for i, row in enumerate(rows)]
    picked = st.selectbox(
        "Sample row", range(len(rows)), format_func=lambda i: labels[i], key=f"try-{rule.uid}"
    )
    row = rows[picked]

    try:
        outcome = engine.evaluate_rule(rule, row, state.functions())
    except engine.OperandError as exc:
        st.error(str(exc))
        return

    if not rule.active_flag:
        st.warning("Rule is inactive, so it would be skipped. Result below ignores that.")

    if outcome["matched"]:
        st.success("Matches this row.", icon=":material/check_circle:")
    else:
        st.warning("Does not match this row.", icon=":material/cancel:")

    _trace(outcome["condition_trace"])

    if outcome["matched"] and rule.assignments:
        lines = []
        for assignment in rule.assignments:
            try:
                resolved = engine.evaluate_assignment(assignment, row, state.functions())
                lines.append(f"- `{assignment.target_field}` = {value_badge(resolved.value)}")
            except engine.OperandError as exc:
                lines.append(f"- `{assignment.target_field}` — {exc}")
        st.markdown("**Would set**\n" + "\n".join(lines))


def _trace(traces: list[dict[str, Any]]) -> None:
    """Render production condition traces without reinterpreting their values."""
    for trace in traces:
        mark = "✓" if trace.get("passed") else "✗"
        left = trace.get("left") or {}
        right = trace.get("right") or {}
        detail = f"left={value_badge(left.get('value'))}"
        if trace.get("right") is not None:
            detail += f" · right={value_badge(right.get('value'))}"
        if left.get("default_applied") or right.get("default_applied"):
            detail += " · null default applied"
        st.markdown(f"{mark} `{trace.get('condition_id')}` · `{trace.get('operator')}` · {detail}")


def _row_label(index: int, row: dict[str, Any]) -> str:
    """Return a compact select-box label for one test row."""
    first = next(iter(row.items()), (None, None))
    return f"{index + 1}. {first[0]}={first[1]}" if first[0] else f"Row {index + 1}"
