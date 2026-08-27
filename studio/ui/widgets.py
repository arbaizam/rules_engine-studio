"""
Shared Streamlit widgets for canonical rules-engine metadata.

Function argument controls are generated from the engine-owned authoring
manifest rather than handwritten signatures. This keeps all registered
functions and their required, optional, literal-only, type, and allowed-value
contracts aligned with the production registry.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from decimal import InvalidOperation
from html import escape
from typing import Any

import streamlit as st

from .. import custom_functions, type_compatibility
from ..schema import (
    OPERAND_KINDS,
    Operand,
    infer_literal_type,
    normalize_literal_editor_type,
)

KIND_LABELS = {
    "field": "Input field",
    "assigned": "Prior assignment",
    "literal": "Literal",
    "custom_function": "Function",
}
KIND_ORDER = list(OPERAND_KINDS)


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
    column_profiles: Mapping[str, type_compatibility.ValueProfile] | None = None,
    assigned_profiles: Mapping[str, type_compatibility.ValueProfile] | None = None,
    allowed_types: frozenset[str] | None = None,
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
    column_profiles : Mapping[str, ValueProfile] | None, default None
        Value-derived types for incoming fields.
    assigned_profiles : Mapping[str, ValueProfile] | None, default None
        Inferred types for targets committed by earlier rules.
    allowed_types : frozenset[str] | None, default None
        Optional semantic-type constraint from an operator or function argument.

    Returns
    -------
    Operand
        The same mutable operand instance.
    """
    field_profiles = column_profiles or {}
    prior_profiles = assigned_profiles or {}
    operand.kind = st.selectbox(
        label,
        KIND_ORDER,
        index=index_of(KIND_ORDER, operand.kind, 2),
        format_func=lambda kind: KIND_LABELS.get(kind, kind.replace("_", " ").title()),
        key=f"{key}-kind",
        label_visibility="visible" if not compact else "collapsed",
    )

    if operand.kind == "field":
        compatible = type_compatibility.compatible_names(
            columns,
            field_profiles,
            allowed_types,
        )
        operand.field_name = _name_input(
            "Input field",
            operand.field_name,
            compatible,
            f"{key}-field",
            "field name",
            profiles=field_profiles,
            allowed_types=allowed_types,
        )
    elif operand.kind == "assigned":
        compatible = type_compatibility.compatible_names(
            assigned,
            prior_profiles,
            allowed_types,
        )
        operand.assigned_field = _name_input(
            "Prior assignment",
            operand.assigned_field,
            compatible,
            f"{key}-assigned",
            "target field",
            profiles=prior_profiles,
            allowed_types=allowed_types,
        )
    elif operand.kind == "custom_function":
        _function_editor(
            operand,
            key,
            columns,
            assigned,
            in_assignment=in_assignment,
            column_profiles=field_profiles,
            assigned_profiles=prior_profiles,
            allowed_types=allowed_types,
        )
    else:
        operand.value_type = normalize_literal_editor_type(operand.value_type, operand.value)
        literal_types = type_compatibility.literal_type_options(
            allowed_types,
            operand.value_type,
        )
        current_type = operand.value_type
        operand.value_type = st.selectbox(
            "Literal type",
            literal_types,
            index=index_of(literal_types, operand.value_type, 0),
            key=f"{key}-vtype",
            label_visibility="collapsed",
            format_func=lambda value: _type_option_label(
                value,
                current_type,
                allowed_types,
            ),
        )
        operand.value = literal_input(operand, f"{key}-value")

    if operand.kind != "literal":
        profile = type_compatibility.profile_for_operand(
            operand,
            field_profiles,
            prior_profiles,
        )
        _default_if_null_editor(
            operand,
            key,
            allowed_types=_fallback_types(profile, allowed_types),
        )
    return operand


def _name_input(
    label: str,
    value: str,
    options: Sequence[str],
    key: str,
    placeholder: str,
    *,
    profiles: Mapping[str, type_compatibility.ValueProfile] | None = None,
    allowed_types: frozenset[str] | None = None,
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
            format_func=lambda name: _name_option_label(
                name,
                value,
                profiles or {},
                allowed_types,
            ),
        )
    return st.text_input(
        label,
        value=value,
        key=f"{key}-text",
        placeholder=placeholder,
        label_visibility="collapsed",
    )


def _name_option_label(
    name: str,
    current: str,
    profiles: Mapping[str, type_compatibility.ValueProfile],
    allowed_types: frozenset[str] | None,
) -> str:
    """Describe a named value source and flag a retained incompatible import."""
    profile = profiles.get(name, type_compatibility.ValueProfile())
    label = f"{name} · {profile.label}"
    if (
        name == current
        and not type_compatibility.profile_matches(profile, allowed_types)
    ):
        label += " · incompatible"
    return label


def _type_option_label(
    value_type: str,
    current: str | None,
    allowed_types: frozenset[str] | None,
) -> str:
    """Flag an imported literal type that conflicts with the active constraint."""
    profile = type_compatibility.profile_for_literal_type(value_type)
    if (
        value_type == current
        and not type_compatibility.profile_matches(profile, allowed_types)
    ):
        return f"{value_type} · incompatible"
    return value_type


def _fallback_types(
    profile: type_compatibility.ValueProfile,
    inherited: frozenset[str] | None,
) -> frozenset[str] | None:
    """Constrain a null fallback to the operand's inferred concrete type."""
    if profile.kind in {type_compatibility.UNKNOWN, type_compatibility.MIXED}:
        return inherited
    if profile.kind in type_compatibility.NUMERIC_TYPES:
        return type_compatibility.NUMERIC_TYPES
    return frozenset({profile.kind})


def _function_editor(
    operand: Operand,
    key: str,
    columns: Sequence[str],
    assigned: Sequence[str],
    *,
    in_assignment: bool | None,
    column_profiles: Mapping[str, type_compatibility.ValueProfile],
    assigned_profiles: Mapping[str, type_compatibility.ValueProfile],
    allowed_types: frozenset[str] | None,
) -> None:
    """Render a registry-driven function selector and named arguments."""
    available = type_compatibility.compatible_function_names(
        custom_functions.names(in_assignment=in_assignment),
        allowed_types,
    )
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
    return_mode, _, return_argument = str(
        specification.get("return_type_hint") or ""
    ).partition(":")
    st.caption(
        f"{specification['description'] or 'Registered custom function.'} "
        f"Returns `{specification['return_type_hint'] or 'any'}`."
    )
    allowed_names = {argument["name"] for argument in specification["arguments"]}
    operand.args = {name: value for name, value in operand.args.items() if name in allowed_names}
    for argument in specification["arguments"]:
        argument_name = str(argument["name"])
        argument_type_hint = str(argument["type_hint"])
        derived_types = (
            allowed_types
            if argument_name == return_argument
            and return_mode in {"same_as", "common_type"}
            else None
        )
        authored = argument_name in operand.args
        if not argument["required"]:
            authored = st.checkbox(
                f"Override `{argument_name}`",
                value=authored,
                key=f"{key}-arg-{argument_name}-enabled",
                help=f"Registry default: {argument.get('default')!r}",
            )
            if not authored:
                operand.args.pop(argument_name, None)
                continue
        if argument["literal_only"]:
            current = operand.args.get(
                argument_name,
                argument.get("default")
                if not argument["required"]
                else _default_for_hint(argument_type_hint),
            )
            operand.args[argument_name] = _literal_argument_input(
                argument,
                current,
                f"{key}-arg-{argument_name}",
            )
            continue
        current = operand.args.get(argument_name)
        if argument_type_hint in {
            "sequence",
            "string_sequence",
            "integer_sequence",
            "date_sequence",
        }:
            mode = st.selectbox(
                f"{argument_name} source",
                ("Operand", "Authored sequence"),
                index=1 if isinstance(current, (list, tuple, set)) else 0,
                key=f"{key}-arg-{argument_name}-mode",
            )
            if mode == "Authored sequence":
                values = list(current) if isinstance(current, (list, tuple, set)) else []
                _sequence_operand_editor(
                    values,
                    f"{key}-arg-{argument_name}",
                    columns,
                    assigned,
                    in_assignment=in_assignment,
                    item_type_hint=argument_type_hint,
                    column_profiles=column_profiles,
                    assigned_profiles=assigned_profiles,
                    item_allowed_types=(
                        derived_types if return_mode == "common_type" else None
                    ),
                )
                operand.args[argument_name] = values
                continue
        if not isinstance(current, Operand):
            default_value = (
                current
                if current is not None
                else argument.get("default")
                if not argument["required"]
                else _default_for_hint(argument_type_hint)
            )
            current = Operand(
                kind="literal",
                value=default_value,
                value_type=_literal_type_for_hint(argument_type_hint, default_value),
            )
            operand.args[argument_name] = current
        st.markdown(f"`{argument_name}` · {argument_type_hint}")
        operand_editor(
            current,
            f"{key}-arg-{argument_name}",
            columns,
            label=argument_name,
            compact=True,
            assigned=assigned,
            in_assignment=in_assignment,
            column_profiles=column_profiles,
            assigned_profiles=assigned_profiles,
            allowed_types=(
                derived_types
                if return_mode == "same_as" and derived_types is not None
                else type_compatibility.allowed_types_for_hint(argument_type_hint)
            ),
        )


def _sequence_operand_editor(
    values: list[Any],
    key: str,
    columns: Sequence[str],
    assigned: Sequence[str],
    *,
    in_assignment: bool | None,
    item_type_hint: str,
    column_profiles: Mapping[str, type_compatibility.ValueProfile],
    assigned_profiles: Mapping[str, type_compatibility.ValueProfile],
    item_allowed_types: frozenset[str] | None,
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
                column_profiles=column_profiles,
                assigned_profiles=assigned_profiles,
                allowed_types=(
                    item_allowed_types
                    if item_allowed_types is not None
                    else type_compatibility.allowed_types_for_hint(item_hint)
                ),
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


def _literal_argument_input(argument: Mapping[str, Any], current: Any, key: str) -> Any:
    """Render a literal-only argument from its registry contract."""
    argument_name = str(argument["name"])
    argument_type_hint = str(argument["type_hint"])
    label = f"{argument_name} · {argument_type_hint}"
    if argument.get("allowed_values") is not None:
        values = list(argument["allowed_values"])
        return st.selectbox(
            label,
            values,
            index=index_of(values, current),
            key=key,
        )
    if argument_type_hint == "boolean":
        return st.checkbox(label, value=bool(current), key=key)
    if argument_type_hint == "integer":
        return int(st.number_input(label, value=int(current or 0), step=1, key=key))
    if argument_type_hint in {
        "sequence",
        "string_sequence",
        "integer_sequence",
        "date_sequence",
    }:
        values = list(current) if isinstance(current, (list, tuple, set)) else []
        text = ", ".join(str(value) for value in values)
        authored = st.text_input(label, value=text, key=key)
        parsed = [part.strip() for part in authored.split(",") if part.strip()]
        if argument_type_hint == "integer_sequence":
            try:
                return tuple(int(value) for value in parsed)
            except ValueError:
                st.error(f"`{argument_name}` requires integers.")
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
    if type_hint == "mapping":
        return {}
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
        "mapping": "struct",
        "string": "string",
    }
    return mapping.get(type_hint, infer_literal_type(value))


def _default_if_null_editor(
    operand: Operand,
    key: str,
    *,
    allowed_types: frozenset[str] | None,
) -> None:
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
    fallback.value_type = normalize_literal_editor_type(fallback.value_type, fallback.value)
    fallback_types = type_compatibility.literal_type_options(
        allowed_types,
        fallback.value_type,
    )
    fallback_types = [kind for kind in fallback_types if kind != "null"]
    current_type = fallback.value_type
    fallback.value_type = st.selectbox(
        "Default type",
        fallback_types,
        index=index_of(fallback_types, fallback.value_type),
        key=f"{key}-default-type",
        label_visibility="collapsed",
        format_func=lambda value: _type_option_label(
            value,
            current_type,
            allowed_types,
        ),
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
        text = "null"
    elif isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (list, tuple)):
        text = ", ".join(str(item) for item in value)
    else:
        text = str(value)
    longest_run = 0
    current_run = 0
    for character in text:
        current_run = current_run + 1 if character == "`" else 0
        longest_run = max(longest_run, current_run)
    delimiter = "`" * max(1, longest_run + 1)
    return f"{delimiter} {escape(text)} {delimiter}"
