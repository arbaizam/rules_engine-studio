"""The rule editor: one rule at a time, read top to bottom as When / Then."""

from __future__ import annotations

from typing import Any, Sequence

import streamlit as st

from .. import engine, state
from ..schema import (
    NULL_RESULTS,
    OPERATOR_NAMES,
    OPERATORS_BY_NAME,
    Assignment,
    Condition,
    ConditionGroup,
    Operand,
    Rule,
    new_condition,
)
from .widgets import index_of, operand_editor, value_badge

_NULL_CHOICES = ["default", *NULL_RESULTS]
_NULL_LABELS = {
    "default": "empty → engine default",
    "false": "empty → no match",
    "true": "empty → match",
    "null": "empty → unknown",
}


def render() -> None:
    rule = state.selected_rule()
    if rule is None:
        st.info("No rules yet. Add the first one from the rule list on the left.")
        if st.button("Add a rule", type="primary"):
            state.queue(state.add_rule)
        return

    columns = state.columns()
    _header(rule)
    st.divider()
    _conditions(rule, columns)
    st.divider()
    _assignments(rule, columns)
    st.divider()
    _try_it(rule)


# --------------------------------------------------------------------------
# header
# --------------------------------------------------------------------------


def _header(rule: Rule) -> None:
    top = st.columns([2, 4])
    rule.rule_id = top[0].text_input("Rule id", value=rule.rule_id, key=f"rid-{rule.uid}")
    rule.description = top[1].text_input(
        "What this rule does",
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
        "Active", value=rule.active_flag, key=f"ractive-{rule.uid}",
        help="Inactive rules are skipped entirely and never appear in matched_rule_ids.",
    )
    rule.stop_on_match = flags[2].toggle(
        "Stop on match",
        value=rule.stop_on_match,
        key=f"rstop-{rule.uid}",
        help="When this rule matches, no later rule runs. A non-match never stops evaluation.",
    )
    if not rule.active_flag:
        flags[3].warning("Inactive — this rule is excluded from evaluation.", icon=":material/block:")


# --------------------------------------------------------------------------
# conditions
# --------------------------------------------------------------------------


def _conditions(rule: Rule, columns: Sequence[str]) -> None:
    st.subheader("When")
    st.caption("Rows that satisfy this run the assignments below.")
    _group(rule.conditions, None, columns, depth=0)


def _group(
    group: ConditionGroup,
    parent: ConditionGroup | None,
    columns: Sequence[str],
    depth: int,
) -> None:
    with st.container(border=True):
        head = st.columns([2, 1, 1, 1, 1])
        group.logic = head[0].selectbox(
            "Match",
            ["all", "any"],
            index=0 if group.logic == "all" else 1,
            format_func=lambda v: "Match all of" if v == "all" else "Match any of",
            key=f"glogic-{group.uid}",
            label_visibility="collapsed",
        )
        group.active_flag = head[1].toggle(
            "Active", value=group.active_flag, key=f"gactive-{group.uid}"
        )
        if head[2].button("Add test", key=f"gaddc-{group.uid}"):
            default = columns[0] if columns else ""
            state.queue(lambda g=group, d=default: g.children.append(new_condition(d)))
        if head[3].button("Add group", key=f"gaddg-{group.uid}", disabled=depth >= 3):
            state.queue(lambda g=group: g.children.append(ConditionGroup(children=[])))
        if parent is not None and head[4].button("Remove group", key=f"gdel-{group.uid}"):
            state.queue(lambda p=parent, g=group: p.children.remove(g))

        if not group.children:
            st.caption("Empty group — matches every row.")

        for child in list(group.children):
            if isinstance(child, ConditionGroup):
                _group(child, group, columns, depth + 1)
            else:
                _condition(child, group, columns)


def _condition(condition: Condition, parent: ConditionGroup, columns: Sequence[str]) -> None:
    with st.container(border=True):
        cols = st.columns([3, 2, 3, 1])

        with cols[0]:
            operand_editor(condition.left, f"cl-{condition.uid}", columns, label="If")

        with cols[1]:
            condition.operator = st.selectbox(
                "Test",
                OPERATOR_NAMES,
                index=index_of(OPERATOR_NAMES, condition.operator),
                format_func=lambda name: OPERATORS_BY_NAME[name].label,
                key=f"cop-{condition.uid}",
            )
            current = condition.null_result or "default"
            choice = st.selectbox(
                "Empty values",
                _NULL_CHOICES,
                index=index_of(_NULL_CHOICES, current),
                format_func=lambda v: _NULL_LABELS[v],
                key=f"cnull-{condition.uid}",
                label_visibility="collapsed",
            )
            condition.null_result = None if choice == "default" else choice

        spec = OPERATORS_BY_NAME.get(condition.operator)
        with cols[2]:
            if spec is not None and spec.arity == 1:
                st.markdown("&nbsp;", unsafe_allow_html=True)
                st.caption("No value needed.")
            else:
                if condition.right is None:
                    condition.right = Operand()
                operand_editor(condition.right, f"cr-{condition.uid}", columns, label="Compare to")
                if spec is not None and spec.hint:
                    st.caption(spec.hint)

        with cols[3]:
            condition.active_flag = st.toggle(
                "On", value=condition.active_flag, key=f"cactive-{condition.uid}"
            )
            if st.button("Remove", key=f"cdel-{condition.uid}"):
                state.queue(lambda p=parent, c=condition: p.children.remove(c))


# --------------------------------------------------------------------------
# assignments
# --------------------------------------------------------------------------


def _assignments(rule: Rule, columns: Sequence[str]) -> None:
    st.subheader("Then set")
    st.caption(
        "Fields written when the rule matches. Within a rule and across rules, the last "
        "write to a field wins."
    )

    if not rule.assignments:
        st.caption("No assignments yet.")

    for assignment in list(rule.assignments):
        with st.container(border=True):
            cols = st.columns([2, 4, 1])
            with cols[0]:
                assignment.target_field = st.text_input(
                    "Field to set",
                    value=assignment.target_field,
                    key=f"atarget-{assignment.uid}",
                    placeholder="hierarchy_node",
                )
            with cols[1]:
                operand_editor(assignment.value, f"aval-{assignment.uid}", columns, label="Set to")
            with cols[2]:
                st.markdown("&nbsp;", unsafe_allow_html=True)
                if st.button("Remove", key=f"adel-{assignment.uid}"):
                    state.queue(lambda r=rule, a=assignment: r.assignments.remove(a))

    if st.button("Add assignment", key=f"aadd-{rule.uid}"):
        state.queue(lambda r=rule: r.assignments.append(Assignment(value=Operand())))

    _override_note(rule)


def _override_note(rule: Rule) -> None:
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
    st.subheader("Try this rule")
    rows = state.rows()
    if not rows:
        st.caption("Add sample data to test this rule.")
        return

    labels = [_row_label(i, row) for i, row in enumerate(rows)]
    picked = st.selectbox("Sample row", range(len(rows)), format_func=lambda i: labels[i], key=f"try-{rule.uid}")
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

    _trace(outcome["condition_trace"], depth=0)

    if outcome["matched"] and rule.assignments:
        lines = []
        for assignment in rule.assignments:
            try:
                resolved = engine.evaluate_assignment(assignment, row, state.functions())
                lines.append(f"- `{assignment.target_field}` = {value_badge(resolved.value)}")
            except engine.OperandError as exc:
                lines.append(f"- `{assignment.target_field}` — {exc}")
        st.markdown("**Would set**\n" + "\n".join(lines))


def _trace(node: dict[str, Any], depth: int) -> None:
    indent = "&nbsp;" * (depth * 4)
    if node.get("kind") == "condition" or "expression" in node and "children" not in node:
        mark = "✓" if node.get("matched") else "✗"
        if node.get("skipped"):
            mark = "–"
        detail = ""
        if not node.get("skipped") and "left_value" in node:
            detail = f" &nbsp; left={value_badge(node['left_value'])}"
            if node.get("right_value") is not None:
                detail += f" right={value_badge(node['right_value'])}"
            if node.get("null_result_applied"):
                detail += f" &nbsp; _(empty → {node['null_result_applied']})_"
        st.markdown(f"{indent}{mark} {node.get('expression', '')}{detail}", unsafe_allow_html=True)
        return

    mark = "✓" if node.get("matched") else "✗"
    if node.get("skipped"):
        mark = "–"
    logic = "all of" if node.get("logic") == "all" else "any of"
    st.markdown(f"{indent}{mark} **{logic}**", unsafe_allow_html=True)
    for child in node.get("children", []):
        _trace(child, depth + 1)


def _row_label(index: int, row: dict[str, Any]) -> str:
    first = next(iter(row.items()), (None, None))
    return f"{index + 1}. {first[0]}={first[1]}" if first[0] else f"Row {index + 1}"
