"""
Shared Streamlit widgets for canonical rules-engine metadata.

Function argument controls are generated from ``CustomFunctionSpec`` rather
than handwritten signatures. This keeps all registered functions and their
required, optional, literal-only, type, and allowed-value contracts aligned
with the production registry.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from decimal import InvalidOperation
from typing import Any

import streamlit as st

from .. import custom_functions
from ..schema import LITERAL_TYPES, Operand, infer_literal_type

KIND_LABELS = {
    "field": "Input field",
    "assigned": "Prior assignment",
    "literal": "Literal",
    "custom_function": "Function",
}
KIND_ORDER = ["field", "assigned", "literal", "custom_function"]


def index_of(options: Sequence[Any], value: Any, default: int = 0) -> int:
    """Return the index of a value or a safe default when it is absent."""
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
    assigned: Sequence[str] = (),
    *,
    in_assignment: bool | None = None,
) -> Operand:
    """
    Edit one canonical operand in place.

    Parameters
    ----------
    operand : Operand
        Mutable studio operand.
    key : str
        Stable Streamlit widget-key prefix.
    columns : Sequence[str]
        Available incoming fields from the current test data.
    label : str, default "Source"
        Widget label for the operand kind.
    compact : bool, default False
        Whether to collapse the kind label.
    assigned : Sequence[str], default ()
        Fields committed by earlier rules.
    in_assignment : bool | None, default None
        Function-permission filter for the authoring context.

    Returns
    -------
    Operand
        The same mutable operand instance.
    """
    operand.kind = st.selectbox(
        label,
        KIND_ORDER,
        index=index_of(KIND_ORDER, operand.kind, 2),
        format_func=lambda kind: KIND_LABELS[kind],
        key=f"{key}-kind",
        label_visibility="visible" if not compact else "collapsed",
    )

    if operand.kind == "field":
        operand.field_name = _name_input(
            "Input field",
            operand.field_name,
            columns,
            f"{key}-field",
            "field name",
        )
    elif operand.kind == "assigned":
        operand.assigned_field = _name_input(
            "Prior assignment",
            operand.assigned_field,
            assigned,
            f"{key}-assigned",
            "target field",
        )
    elif operand.kind == "custom_function":
        _function_editor(
            operand,
            key,
            columns,
            assigned,
            in_assignment=in_assignment,
        )
    else:
        if operand.value_type == "list":
            operand.value_type = "array"
        operand.value_type = st.selectbox(
            "Literal type",
            LITERAL_TYPES,
            index=index_of(LITERAL_TYPES, operand.value_type, 0),
            key=f"{key}-vtype",
            label_visibility="collapsed",
        )
        operand.value = literal_input(operand, f"{key}-value")

    if operand.kind != "literal":
        _default_if_null_editor(operand, key)
    return operand


def _name_input(
    label: str,
    value: str,
    options: Sequence[str],
    key: str,
    placeholder: str,
) -> str:
    """Render a select box when names are known and text input otherwise."""
    available = list(dict.fromkeys([*options, value] if value else options))
    if available:
        return st.selectbox(
            label,
            available,
            index=index_of(available, value),
            key=key,
            label_visibility="collapsed",
        )
    return st.text_input(
        label,
        value=value,
        key=f"{key}-text",
        placeholder=placeholder,
        label_visibility="collapsed",
    )


def _function_editor(
    operand: Operand,
    key: str,
    columns: Sequence[str],
    assigned: Sequence[str],
    *,
    in_assignment: bool | None,
) -> None:
    """Render a registry-driven function selector and named arguments."""
    available = custom_functions.names(in_assignment=in_assignment)
    options = list(dict.fromkeys([*available, operand.function] if operand.function else available))
    if not options:
        st.error("No active functions are registered for this context.")
        return
    operand.function = st.selectbox(
        "Function",
        options,
        index=index_of(options, operand.function),
        key=f"{key}-function",
        label_visibility="collapsed",
    )
    specification = custom_functions.spec(operand.function)
    st.caption(
        f"{specification.description or 'Registered custom function.'} "
        f"Returns `{specification.return_type_hint or 'any'}`."
    )
    allowed_names = set(specification.argument_names)
    operand.args = {name: value for name, value in operand.args.items() if name in allowed_names}
    for argument in specification.arguments:
        authored = argument.name in operand.args
        if not argument.required:
            authored = st.checkbox(
                f"Override `{argument.name}`",
                value=authored,
                key=f"{key}-arg-{argument.name}-enabled",
                help=f"Registry default: {argument.default!r}",
            )
            if not authored:
                operand.args.pop(argument.name, None)
                continue
        if argument.literal_only:
            current = operand.args.get(
                argument.name,
                argument.default
                if not argument.required
                else _default_for_hint(argument.type_hint),
            )
            operand.args[argument.name] = _literal_argument_input(
                argument,
                current,
                f"{key}-arg-{argument.name}",
            )
            continue
        current = operand.args.get(argument.name)
        if argument.type_hint in {
            "sequence",
            "string_sequence",
            "integer_sequence",
            "date_sequence",
        }:
            mode = st.selectbox(
                f"{argument.name} source",
                ("Operand", "Authored sequence"),
                index=1 if isinstance(current, (list, tuple, set)) else 0,
                key=f"{key}-arg-{argument.name}-mode",
            )
            if mode == "Authored sequence":
                values = list(current) if isinstance(current, (list, tuple, set)) else []
                _sequence_operand_editor(
                    values,
                    f"{key}-arg-{argument.name}",
                    columns,
                    assigned,
                    in_assignment=in_assignment,
                    item_type_hint=argument.type_hint,
                )
                operand.args[argument.name] = values
                continue
        if not isinstance(current, Operand):
            default_value = (
                current
                if current is not None
                else argument.default
                if not argument.required
                else _default_for_hint(argument.type_hint)
            )
            current = Operand(
                kind="literal",
                value=default_value,
                value_type=_literal_type_for_hint(argument.type_hint, default_value),
            )
            operand.args[argument.name] = current
        st.markdown(f"`{argument.name}` · {argument.type_hint}")
        operand_editor(
            current,
            f"{key}-arg-{argument.name}",
            columns,
            label=argument.name,
            compact=True,
            assigned=assigned,
            in_assignment=in_assignment,
        )


def _sequence_operand_editor(
    values: list[Any],
    key: str,
    columns: Sequence[str],
    assigned: Sequence[str],
    *,
    in_assignment: bool | None,
    item_type_hint: str,
) -> None:
    """Render an authored sequence whose items may themselves be operands."""
    item_hint = {
        "string_sequence": "string",
        "integer_sequence": "integer",
        "date_sequence": "date",
    }.get(item_type_hint, "any")
    for index, value in enumerate(list(values)):
        if not isinstance(value, Operand):
            value = Operand(
                kind="literal",
                value=value,
                value_type=_literal_type_for_hint(item_hint, value),
            )
            values[index] = value
        with st.container(border=True):
            operand_editor(
                value,
                f"{key}-item-{index}",
                columns,
                label=f"Item {index + 1}",
                compact=True,
                assigned=assigned,
                in_assignment=in_assignment,
            )
            if st.button("Remove item", key=f"{key}-remove-{index}"):
                values.pop(index)
                st.rerun()
    if st.button("Add item", key=f"{key}-add"):
        default = _default_for_hint(item_hint)
        values.append(
            Operand(
                kind="literal",
                value=default,
                value_type=_literal_type_for_hint(item_hint, default),
            )
        )
        st.rerun()


def _literal_argument_input(argument: Any, current: Any, key: str) -> Any:
    """Render a literal-only argument from its registry contract."""
    label = f"{argument.name} · {argument.type_hint}"
    if argument.allowed_values is not None:
        values = list(argument.allowed_values)
        return st.selectbox(
            label,
            values,
            index=index_of(values, current),
            key=key,
        )
    if argument.type_hint == "boolean":
        return st.checkbox(label, value=bool(current), key=key)
    if argument.type_hint == "integer":
        return int(st.number_input(label, value=int(current or 0), step=1, key=key))
    if argument.type_hint in {"sequence", "string_sequence", "integer_sequence"}:
        values = list(current) if isinstance(current, (list, tuple, set)) else []
        text = ", ".join(str(value) for value in values)
        authored = st.text_input(label, value=text, key=key)
        parsed = [part.strip() for part in authored.split(",") if part.strip()]
        if argument.type_hint == "integer_sequence":
            try:
                return tuple(int(value) for value in parsed)
            except ValueError:
                st.error(f"`{argument.name}` requires integers.")
                return tuple(values)
        return tuple(parsed)
    return st.text_input(label, value="" if current is None else str(current), key=key)


def _default_for_hint(type_hint: str) -> Any:
    """Return a neutral editable literal for one registry argument type hint."""
    if type_hint in {"integer", "number"}:
        return 0
    if type_hint == "boolean":
        return False
    if type_hint in {"sequence", "string_sequence", "integer_sequence", "date_sequence"}:
        return []
    return ""


def _literal_type_for_hint(type_hint: str, value: Any) -> str:
    """Map a registry argument type hint to a studio literal editor type."""
    mapping = {
        "boolean": "boolean",
        "date": "date",
        "integer": "integer",
        "number": "decimal",
        "timestamp": "timestamp",
        "sequence": "array",
        "string_sequence": "array",
        "integer_sequence": "array",
        "date_sequence": "array",
        "string": "string",
    }
    return mapping.get(type_hint, infer_literal_type(value))


def _default_if_null_editor(operand: Operand, key: str) -> None:
    """Render the operand-level literal fallback supported by the engine."""
    enabled = st.checkbox(
        "Default if null",
        value=operand.default_if_null is not None,
        key=f"{key}-default-enabled",
        help="The production runtime applies this literal before comparison or assignment.",
    )
    if not enabled:
        operand.default_if_null = None
        return
    if operand.default_if_null is None:
        operand.default_if_null = Operand(kind="literal", value="", value_type="string")
    fallback = operand.default_if_null
    if fallback.value_type == "list":
        fallback.value_type = "array"
    fallback.value_type = st.selectbox(
        "Default type",
        [kind for kind in LITERAL_TYPES if kind != "null"],
        index=index_of([kind for kind in LITERAL_TYPES if kind != "null"], fallback.value_type),
        key=f"{key}-default-type",
        label_visibility="collapsed",
    )
    fallback.value = literal_input(fallback, f"{key}-default-value")


def literal_input(operand: Operand, key: str) -> Any:
    """Render a literal input while preserving compiler-relevant type intent."""
    kind = operand.value_type
    if kind == "null":
        st.caption("null")
        return None
    if kind == "boolean":
        current = (
            operand.value
            if isinstance(operand.value, bool)
            else str(operand.value).lower() == "true"
        )
        return st.checkbox("True", value=current, key=key)
    if kind == "integer":
        current = _to_number(operand.value, 0)
        return int(
            st.number_input(
                "Value",
                value=int(current),
                step=1,
                key=key,
                label_visibility="collapsed",
            )
        )
    if kind == "double":
        current = _to_number(operand.value, 0.0)
        return float(
            st.number_input(
                "Value",
                value=float(current),
                key=key,
                label_visibility="collapsed",
            )
        )
    if kind == "decimal":
        return st.text_input(
            "Decimal",
            value="" if operand.value is None else str(operand.value),
            key=key,
            placeholder="0.00",
            label_visibility="collapsed",
        )
    if kind in {"array", "list"}:
        current = list(operand.value) if isinstance(operand.value, (list, tuple, set)) else []
        return _json_literal_input(current, list, f"{key}-array", "JSON array")
    if kind == "struct":
        current = dict(operand.value) if isinstance(operand.value, dict) else {}
        return _json_literal_input(current, dict, f"{key}-struct", "JSON object")
    placeholder = {
        "date": "2026-08-23",
        "timestamp": "2026-08-23T12:00:00+00:00",
        "timestamp_ntz": "2026-08-23T12:00:00",
    }.get(kind, "value")
    return st.text_input(
        "Value",
        value="" if operand.value is None else str(operand.value),
        key=key,
        placeholder=placeholder,
        label_visibility="collapsed",
    )


def _json_literal_input(
    current: list[Any] | dict[str, Any],
    expected_type: type[list[Any]] | type[dict[str, Any]],
    key: str,
    label: str,
) -> list[Any] | dict[str, Any]:
    """Render and validate one canonical array or struct literal as JSON."""
    raw = st.text_area(
        label,
        value=json.dumps(current, indent=2, default=str),
        key=key,
        height=112,
        placeholder="[]" if expected_type is list else "{}",
        label_visibility="collapsed",
    )
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        st.error(f"Invalid {label}: {exc.msg} at line {exc.lineno}, column {exc.colno}.")
        return current
    if not isinstance(parsed, expected_type):
        st.error(f"{label} must start with {'[' if expected_type is list else '{'}.")
        return current
    return parsed


def _to_number(value: Any, fallback: float) -> float:
    """Return a finite widget number or a safe fallback."""
    try:
        return float(value)
    except (TypeError, ValueError, InvalidOperation):
        return fallback


def issue_list(issues: Sequence[Any], title: str = "Checks") -> None:
    """Render engine errors and sample-data warnings without altering them."""
    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity == "warning"]
    if not errors and not warnings:
        st.success(f"{title}: production validation passed.")
        return
    if errors:
        st.error(f"{len(errors)} engine validation issue(s)")
        for issue in errors:
            check = f" `{issue.check_name}`" if getattr(issue, "check_name", "") else ""
            st.markdown(f"- **{issue.where}**{check} — {issue.message}")
    if warnings:
        with st.expander(f"{len(warnings)} test-data warning(s)", expanded=not errors):
            for issue in warnings:
                st.markdown(f"- **{issue.where}** — {issue.message}")


def value_badge(value: Any) -> str:
    """Return a compact Markdown representation of a runtime value."""
    if value is None:
        return "`null`"
    if isinstance(value, bool):
        return "`true`" if value else "`false`"
    if isinstance(value, (list, tuple)):
        return "`" + ", ".join(str(item) for item in value) + "`"
    return f"`{value}`"
