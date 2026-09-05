"""
Shared Streamlit widgets for canonical rules-engine metadata.

Function argument controls are generated from the engine-owned authoring
manifest rather than handwritten signatures. This keeps all registered
functions and their required, optional, literal-only, type, and allowed-value
contracts aligned with the production registry.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from html import escape
from typing import Any

import streamlit as st

from rules_engine.canonical_values import canonical_json_dumps, decode_json_types

from .. import custom_functions, type_compatibility
from ..schema import (
    OPERAND_KINDS,
    SCALAR_LITERAL_TYPES,
    Operand,
    _argument_from_payload,
    _argument_to_payload,
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


@contextmanager
def editor_pass(rule_uid: str):
    """Clear stale parse blockers for controls removed from this rule's form."""
    seen: set[str] = set()
    st.session_state["studio_editor_seen"] = seen
    try:
        yield
    finally:
        known = st.session_state.setdefault("studio_editor_keys_by_rule", {})
        errors = st.session_state.setdefault("studio_editor_errors", {})
        raw_values = st.session_state.setdefault("studio_editor_raw", {})
        for key in set(known.get(rule_uid, ())) - seen:
            errors.pop(key, None)
            raw_values.pop(key, None)
        known[rule_uid] = sorted(seen)
        st.session_state.pop("studio_editor_seen", None)


def editor_error(key: str, message: str | None, *, raw: str | None = None) -> None:
    """Register parse failures so evaluation and export cannot use stale values."""
    seen = st.session_state.get("studio_editor_seen")
    if seen is not None:
        seen.add(key)
    errors = st.session_state.setdefault("studio_editor_errors", {})
    if message is None:
        errors.pop(key, None)
        st.session_state.setdefault("studio_editor_raw", {}).pop(key, None)
    else:
        errors[key] = message
        if raw is not None:
            st.session_state.setdefault("studio_editor_raw", {})[key] = raw
        st.error(message)


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
        _literal_editor(operand, key, allowed_types=allowed_types)

    profile = type_compatibility.profile_for_operand(operand, field_profiles, prior_profiles)
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
    previous_function = operand.function
    operand.function = st.selectbox(
        "Function",
        options,
        index=index_of(options, operand.function),
        key=f"{key}-function",
        label_visibility="collapsed",
    )
    try:
        specification = custom_functions.spec(operand.function)
    except StopIteration:
        st.error(f"Function `{operand.function}` is not registered. Select a registered function.")
        return
    return_mode, _, return_argument = str(
        specification.get("return_type_hint") or ""
    ).partition(":")
    st.caption(
        f"{specification['description'] or 'Registered custom function.'} "
        f"Returns `{specification['return_type_hint'] or 'any'}`."
    )
    allowed_names = {argument["name"] for argument in specification["arguments"]}
    if operand.function != previous_function:
        operand.args = {name: value for name, value in operand.args.items() if name in allowed_names}
    elif unknown_arguments := set(operand.args) - allowed_names:
        st.error("Unrecognized arguments: " + ", ".join(sorted(unknown_arguments)))
        if st.button("Remove unrecognized arguments", key=f"{key}-remove-unknown-args"):
            operand.args = {name: value for name, value in operand.args.items() if name in allowed_names}
            st.rerun()
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
        if isinstance(current, Mapping) or (
            isinstance(current, (list, tuple, set))
            and argument_type_hint not in type_compatibility.SEQUENCE_HINTS
        ):
            operand.args[argument_name] = _collection_argument_input(current, f"{key}-arg-{argument_name}")
            continue
        if argument_type_hint in type_compatibility.SEQUENCE_HINTS:
            if argument_type_hint == "ordered_sequence" and isinstance(current, set):
                st.error(f"`{argument_name}` requires an ordered list or tuple, not a set.")
                continue
            mode = st.selectbox(
                f"{argument_name} source",
                ("Operand", "Authored sequence"),
                index=1 if isinstance(current, (list, tuple, set)) else 0,
                key=f"{key}-arg-{argument_name}-mode",
            )
            if mode == "Authored sequence":
                values = list(current) if isinstance(current, (list, tuple, set)) else []
                operand.args[argument_name] = values
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
                if isinstance(current, (tuple, set)) and values == list(current):
                    operand.args[argument_name] = current
                continue
        raw_argument = not isinstance(current, Operand)
        had_argument = argument_name in operand.args
        if not isinstance(current, Operand):
            default_value = (
                current
                if had_argument
                else argument.get("default")
                if not argument["required"]
                else _default_for_hint(argument_type_hint)
            )
            current = Operand(
                kind="literal",
                value=default_value,
                value_type=None if had_argument else _literal_type_for_hint(argument_type_hint, default_value),
            )
        previous_payload = current.to_dict()
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
        if not raw_argument or not had_argument or current.to_dict() != previous_payload:
            operand.args[argument_name] = current


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
        if isinstance(value, (Mapping, list, tuple, set)):
            with st.container(border=True):
                values[index] = _collection_argument_input(value, f"{key}-collection-{index}")
                _sequence_item_buttons(values, index, key)
            continue
        raw_item = not isinstance(value, Operand)
        if raw_item:
            value = Operand(
                kind="literal",
                value=value,
                value_type=None,
            )
        previous_payload = value.to_dict()
        with st.container(border=True):
            operand_editor(
                value,
                f"{key}-raw-{index}" if raw_item else f"{key}-item-{value.uid}",
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
            if not raw_item or value.to_dict() != previous_payload:
                values[index] = value
            _sequence_item_buttons(values, index, key)
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


def _sequence_item_buttons(values: list[Any], index: int, key: str) -> None:
    """Edit list structure before requesting a Streamlit rerun."""
    if st.button("Remove item", key=f"{key}-remove-{index}"):
        values.pop(index)
        st.rerun()
    move = st.columns(2)
    if move[0].button("Move up", key=f"{key}-up-{index}", disabled=index == 0):
        values[index - 1], values[index] = values[index], values[index - 1]
        st.rerun()
    if move[1].button(
        "Move down", key=f"{key}-down-{index}", disabled=index == len(values) - 1
    ):
        values[index + 1], values[index] = values[index], values[index + 1]
        st.rerun()


def _collection_argument_input(current: Any, key: str) -> Any:
    """Edit recursive function arguments using canonical operand mappings."""
    payload = _argument_to_payload(current)
    expected = dict if isinstance(current, Mapping) else list
    edited = _json_literal_input(payload, expected, f"{key}-collection", "Function argument JSON")
    return current if edited == payload else _argument_from_payload(edited)


def _literal_argument_input(argument: Mapping[str, Any], current: Any, key: str) -> Any:
    """Render a literal-only argument from its registry contract."""
    argument_name = str(argument["name"])
    argument_type_hint = str(argument["type_hint"])
    label = f"{argument_name} · {argument_type_hint}"
    if argument.get("allowed_values") is not None:
        values = list(argument["allowed_values"])
        if current not in values:
            values.append(current)
        return st.selectbox(
            label,
            values,
            index=index_of(values, current),
            key=key,
        )
    st.markdown(label)
    literal = current if isinstance(current, Operand) else Operand(
        kind="literal", value=current,
        value_type=_literal_type_for_hint(argument_type_hint, current),
    )
    if literal.kind != "literal":
        st.error(f"`{argument_name}` requires a literal value.")
        return current
    edited = literal_input(literal, key)
    if isinstance(current, Operand):
        literal.value = edited
        return literal
    return edited


def _default_for_hint(type_hint: str) -> Any:
    """Return a neutral editable literal for one registry argument type hint."""
    if type_hint in {"integer", "number", "decimal", "double"}:
        return 0
    if type_hint == "boolean":
        return False
    if type_hint in type_compatibility.SEQUENCE_HINTS | {"array"}:
        return []
    if type_hint in {"mapping", "struct"}:
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
        "ordered_sequence": "array",
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
        options = [
            kind for kind in type_compatibility.literal_type_options(allowed_types)
            if kind != "null"
        ]
        default_type = options[0] if options else "string"
        operand.default_if_null = Operand(
            kind="literal", value=_default_for_hint(default_type), value_type=default_type
        )
    fallback = operand.default_if_null
    _literal_editor(
        fallback, f"{key}-default", allowed_types=allowed_types, fallback=True,
    )


def _literal_editor(
    operand: Operand,
    key: str,
    *,
    allowed_types: frozenset[str] | None,
    fallback: bool = False,
) -> None:
    """Edit value shape separately from optional canonical scalar type metadata."""
    inferred = infer_literal_type(operand.value)
    current_type = (
        inferred if inferred in {"array", "struct"}
        else normalize_literal_editor_type(operand.value_type, operand.value)
    )
    literal_types = type_compatibility.literal_type_options(allowed_types, current_type)
    if fallback:
        literal_types = [kind for kind in literal_types if kind != "null" or kind == current_type]
    selected_type = st.selectbox(
        "Default type" if fallback else "Literal type",
        literal_types,
        index=index_of(literal_types, current_type),
        key=f"{key}-type" if fallback else f"{key}-vtype",
        label_visibility="collapsed",
        format_func=lambda value: _type_option_label(value, current_type, allowed_types),
    )
    if selected_type != current_type:
        operand.value_type = selected_type
        if selected_type in {"array", "struct"}:
            operand.value = [] if selected_type == "array" else {}
    if selected_type in {"array", "struct"}:
        hint = operand.value_type if operand.value_type not in {"array", "struct", "list"} else None
        hints = list(dict.fromkeys([None, *SCALAR_LITERAL_TYPES, *([hint] if hint else [])]))
        selected_hint = st.selectbox(
            "Element type",
            hints,
            index=index_of(hints, hint),
            key=f"{key}-element-type",
            format_func=lambda value: "Infer each value" if value is None else value,
            help="A declared type applies to every scalar inside this collection.",
        )
        if selected_hint != hint:
            operand.value_type = selected_hint
    editor_operand = Operand(kind="literal", value=operand.value, value_type=selected_type)
    operand.value = literal_input(editor_operand, f"{key}-value")
    if fallback and operand.value is None:
        st.error("A null fallback must contain a non-null literal.")


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
        selected = st.checkbox("True", value=current, key=key)
        return operand.value if selected == current else selected
    if kind == "integer":
        return _numeric_literal_input(operand.value, key, "integer")
    if kind == "double":
        return _numeric_literal_input(operand.value, key, "double")
    if kind == "decimal":
        return _numeric_literal_input(operand.value, key, "decimal")
    if kind in {"array", "list"}:
        current = operand.value if isinstance(operand.value, (list, tuple, set)) else []
        return _json_literal_input(current, list, f"{key}-array", "JSON array")
    if kind == "struct":
        current = dict(operand.value) if isinstance(operand.value, dict) else {}
        return _json_literal_input(current, dict, f"{key}-struct", "JSON object")
    placeholder = {
        "date": "2026-08-23",
        "timestamp": "2026-08-23T12:00:00+00:00",
        "timestamp_ntz": "2026-08-23T12:00:00",
    }.get(kind, "value")
    current = "" if operand.value is None else str(operand.value)
    selected = st.text_input(
        "Value",
        value=current,
        key=key,
        placeholder=placeholder,
        label_visibility="collapsed",
    )
    return operand.value if selected == current else selected


def _numeric_literal_input(value: Any, key: str, kind: str) -> Any:
    """Use text to preserve full signed-long and decimal precision in the browser."""
    current = "" if value is None else str(value)
    raw = st.text_input(
        kind.title(), value=current, key=key, label_visibility="collapsed",
        placeholder="0.00" if kind == "decimal" else "0",
    )
    if raw == current:
        editor_error(key, None)
        return value
    try:
        if kind == "integer":
            parsed = int(raw)
        else:
            parsed = Decimal(raw) if kind == "decimal" else float(raw)
        if kind != "integer" and not (
            parsed.is_finite() if isinstance(parsed, Decimal) else math.isfinite(parsed)
        ):
            raise ValueError("Numeric literals must be finite.")
        editor_error(key, None)
        return parsed
    except (ValueError, InvalidOperation):
        editor_error(key, f"Enter a finite {kind} value.")
        # Preserve invalid edits so production validation cannot approve an older value.
        return raw


def _json_literal_input(
    current: list[Any] | tuple[Any, ...] | set[Any] | dict[str, Any],
    expected_type: type[list[Any]] | type[dict[str, Any]],
    key: str,
    label: str,
) -> Any:
    """Render and validate one canonical array or struct literal as JSON."""
    initial_error = None
    try:
        initial = canonical_json_dumps(current)
    except (ValueError, TypeError) as exc:
        initial = json.dumps(current, default=str)
        initial_error = f"Invalid {label}: {exc}."
    raw = st.text_area(
        label,
        value=st.session_state.get("studio_editor_raw", {}).get(key, initial),
        key=key,
        height=112,
        placeholder="[]" if expected_type is list else "{}",
        label_visibility="collapsed",
    )
    if raw == initial:
        editor_error(key, initial_error, raw=raw if initial_error else None)
        return current
    try:
        parsed = decode_json_types(json.loads(raw, parse_float=Decimal, parse_constant=_invalid_json_number))
    except (ValueError, InvalidOperation) as exc:
        editor_error(key, f"Invalid {label}: {exc}.", raw=raw)
        return current
    accepted_types = (list, tuple, set) if expected_type is list else (dict,)
    if not isinstance(parsed, accepted_types):
        editor_error(
            key, f"{label} must contain {'an array' if expected_type is list else 'an object'}.",
            raw=raw,
        )
        return current
    editor_error(key, None)
    return parsed


def _invalid_json_number(value: str) -> Any:
    """Reject JavaScript non-finite constants that canonical literals forbid."""
    raise ValueError(f"Non-finite number {value} is not allowed")


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
