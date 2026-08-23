"""Shared widgets.

Layout rule for everything in this package: never open ``st.columns`` inside a
column. Widgets here stack vertically so a caller can drop them into a column
without breaking the tree.
"""

from __future__ import annotations

from typing import Any, Sequence

import streamlit as st

from ..custom_functions import names as function_names
from ..schema import LITERAL_TYPES, Operand
from ..text_operands import format_arg_lines, parse_arg_lines

KIND_LABELS = {"field": "Column", "literal": "Value", "function": "Function"}
KIND_ORDER = ["field", "literal", "function"]


def index_of(options: Sequence[Any], value: Any, default: int = 0) -> int:
    try:
        return list(options).index(value)
    except ValueError:
        return default


def operand_editor(
    operand: Operand,
    key: str,
    columns: Sequence[str],
    label: str = "Source",
    compact: bool = False,
) -> Operand:
    """Edit an operand in place. Returns the same object for convenience."""
    operand.kind = st.selectbox(
        label,
        KIND_ORDER,
        index=index_of(KIND_ORDER, operand.kind, 1),
        format_func=lambda k: KIND_LABELS[k],
        key=f"{key}-kind",
        label_visibility="visible" if not compact else "collapsed",
    )

    if operand.kind == "field":
        options = list(dict.fromkeys([*columns, operand.field_name] if operand.field_name else columns))
        if options:
            operand.field_name = st.selectbox(
                "Column",
                options,
                index=index_of(options, operand.field_name),
                key=f"{key}-field",
                label_visibility="collapsed",
            )
        else:
            operand.field_name = st.text_input(
                "Column",
                value=operand.field_name,
                key=f"{key}-field-text",
                placeholder="column name",
                label_visibility="collapsed",
            )
        return operand

    if operand.kind == "function":
        available = function_names()
        options = list(dict.fromkeys([*available, operand.function] if operand.function else available))
        if options:
            operand.function = st.selectbox(
                "Function",
                options,
                index=index_of(options, operand.function),
                key=f"{key}-fn",
                label_visibility="collapsed",
            )
        else:
            operand.function = st.text_input(
                "Function", value=operand.function, key=f"{key}-fn-text", label_visibility="collapsed"
            )
        raw = st.text_area(
            "Arguments",
            value=format_arg_lines(operand.args),
            key=f"{key}-args",
            height=80,
            help="One argument per line: field:col, str:text, int:5, num:0.8, "
            "bool:true, list:a,b,c, null, fn:name(field:a|str:b)",
            label_visibility="collapsed",
            placeholder="field:cost_centre",
        )
        try:
            operand.args = parse_arg_lines(raw)
        except (ValueError, TypeError) as exc:
            st.error(str(exc))
        return operand

    # literal
    operand.value_type = st.selectbox(
        "Type",
        LITERAL_TYPES,
        index=index_of(LITERAL_TYPES, operand.value_type, 0),
        key=f"{key}-vtype",
        label_visibility="collapsed",
    )
    operand.value = literal_input(operand, f"{key}-value")
    return operand


def literal_input(operand: Operand, key: str) -> Any:
    kind = operand.value_type
    if kind == "null":
        st.caption("null")
        return None
    if kind == "boolean":
        current = operand.value if isinstance(operand.value, bool) else str(operand.value).lower() == "true"
        return st.checkbox("True", value=current, key=key)
    if kind == "integer":
        current = _to_number(operand.value, 0)
        return int(st.number_input("Value", value=int(current), step=1, key=key, label_visibility="collapsed"))
    if kind == "number":
        current = _to_number(operand.value, 0.0)
        return float(st.number_input("Value", value=float(current), key=key, label_visibility="collapsed"))
    if kind == "list":
        current = operand.value if isinstance(operand.value, (list, tuple)) else [operand.value]
        text = ", ".join("" if v is None else str(v) for v in current)
        raw = st.text_input(
            "Values",
            value=text,
            key=key,
            placeholder="a, b, c",
            label_visibility="collapsed",
        )
        return [p.strip() for p in raw.split(",") if p.strip()]
    return st.text_input(
        "Value",
        value="" if operand.value is None else str(operand.value),
        key=key,
        placeholder="value",
        label_visibility="collapsed",
    )


def _to_number(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def issue_list(issues, title: str = "Checks") -> None:
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    if not errors and not warnings:
        st.success(f"{title}: nothing to fix.")
        return
    if errors:
        st.error(f"{len(errors)} to fix before export")
        for issue in errors:
            st.markdown(f"- **{issue.where}** — {issue.message}")
    if warnings:
        with st.expander(f"{len(warnings)} worth a look", expanded=not errors):
            for issue in warnings:
                st.markdown(f"- **{issue.where}** — {issue.message}")


def value_badge(value: Any) -> str:
    if value is None:
        return "`null`"
    if isinstance(value, bool):
        return "`true`" if value else "`false`"
    if isinstance(value, (list, tuple)):
        return "`" + ", ".join(str(v) for v in value) + "`"
    return f"`{value}`"
