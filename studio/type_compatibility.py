"""Value-type inference and compatibility guidance for authoring controls.

The production engine remains authoritative for compilation and evaluation.
This module uses the current sample values and engine-owned function contracts
to keep the Studio from offering combinations that are predictably unusable.
Unknown and mixed inputs stay available because sample data is advisory rather
than a persisted schema.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from numbers import Integral, Real
from typing import Any

import pandas as pd

from . import custom_functions
from .schema import LITERAL_TYPES, Operand, Rule, Ruleset

UNKNOWN = "unknown"
MIXED = "mixed"
STRING = "string"
BOOLEAN = "boolean"
INTEGER = "integer"
NUMBER = "number"
DATE = "date"
TIMESTAMP = "timestamp"
TIMESTAMP_NTZ = "timestamp_ntz"
SEQUENCE = "sequence"
MAPPING = "mapping"

CONCRETE_TYPES = frozenset(
    {STRING, BOOLEAN, INTEGER, NUMBER, DATE, TIMESTAMP, TIMESTAMP_NTZ, SEQUENCE, MAPPING}
)
NUMERIC_TYPES = frozenset({INTEGER, NUMBER})
TEMPORAL_TYPES = frozenset({DATE, TIMESTAMP, TIMESTAMP_NTZ})
SCALAR_TYPES = frozenset({STRING, BOOLEAN, INTEGER, NUMBER}) | TEMPORAL_TYPES
SEQUENCE_HINTS = frozenset(
    {"sequence", "ordered_sequence", "string_sequence", "integer_sequence", "date_sequence"}
)

_NULL_OPERATORS = frozenset({"is_null", "is_not_null"})
_STRING_OPERATORS = frozenset(
    {"contains", "not_contains", "starts_with", "ends_with", "like", "not_like"}
)
_ORDERED_OPERATORS = frozenset({"gt", "ge", "lt", "le"})
_RANGE_OPERATORS = frozenset({"between", "not_between"})
_MEMBERSHIP_OPERATORS = frozenset({"in", "not_in"})
_EQUALITY_OPERATORS = frozenset({"eq", "ne"})


@dataclass(frozen=True)
class ValueProfile:
    """Inferred semantic type and nullability for one authored value source."""

    kind: str = UNKNOWN
    nullable: bool = False

    @property
    def label(self) -> str:
        """Return a compact label suitable for select-box options."""
        suffix = " · nullable" if self.nullable else ""
        return f"{self.kind}{suffix}"


def is_missing(value: Any) -> bool:
    """Return whether a scalar value is null without expanding collections."""
    if value is None:
        return True
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return isinstance(missing, bool) and missing


def profile_values(values: Iterable[Any]) -> ValueProfile:
    """Infer one conservative semantic profile from observed sample values."""
    kinds: set[str] = set()
    nullable = False
    for value in values:
        if is_missing(value):
            nullable = True
            continue
        kinds.add(_value_kind(value))
    return _combined_kind(kinds, nullable=nullable)


def column_profiles(frame: pd.DataFrame) -> dict[str, ValueProfile]:
    """Return semantic profiles for every current sample-data column."""
    return {
        str(column): profile_values(frame[column].tolist())
        for column in frame.columns
    }


def normalized_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Return Python rows without pandas nulls or nullable-integer widening."""
    records: list[dict[str, Any]] = []
    for authored in frame.to_dict("records"):
        row: dict[str, Any] = {}
        for column, value in authored.items():
            name = str(column)
            if is_missing(value):
                row[name] = None
                continue
            scalar = _python_scalar(value)
            row[name] = scalar
        records.append(row)
    return records


def operator_options(profile: ValueProfile, names: Sequence[str]) -> list[str]:
    """Exclude only combinations that cannot execute in the canonical runtime."""
    if profile.kind in {BOOLEAN, MAPPING, SEQUENCE}:
        return [name for name in names if name not in _ORDERED_OPERATORS | _RANGE_OPERATORS]
    return list(names)


def left_types_for_operator(operator: str) -> frozenset[str] | None:
    """Return compatible left-side types for one comparison operator."""
    if operator in _ORDERED_OPERATORS | _RANGE_OPERATORS:
        return NUMERIC_TYPES | TEMPORAL_TYPES | {STRING}
    return None


def right_types_for_condition(
    operator: str,
    left_profile: ValueProfile,
) -> frozenset[str] | None:
    """Return compatible right-side types for a condition selection."""
    if operator in _NULL_OPERATORS:
        return frozenset()
    if operator in _STRING_OPERATORS:
        return None
    if operator in _RANGE_OPERATORS | _MEMBERSHIP_OPERATORS:
        return frozenset({SEQUENCE})
    if left_profile.kind in TEMPORAL_TYPES:
        return frozenset({left_profile.kind})
    if operator in _ORDERED_OPERATORS:
        return NUMERIC_TYPES | {STRING} if left_profile.kind in NUMERIC_TYPES | {STRING} else None
    return None


def profile_matches(
    profile: ValueProfile,
    allowed_types: frozenset[str] | None,
) -> bool:
    """Return whether an inferred profile satisfies an authoring constraint."""
    if allowed_types is None or profile.kind in {UNKNOWN, MIXED}:
        return True
    if profile.kind == INTEGER and NUMBER in allowed_types:
        return True
    return profile.kind in allowed_types


def compatible_names(
    names: Sequence[str],
    profiles: Mapping[str, ValueProfile],
    allowed_types: frozenset[str] | None,
) -> list[str]:
    """Filter named sources while retaining unknown types as editable choices."""
    return [
        name
        for name in names
        if profile_matches(profiles.get(name, ValueProfile()), allowed_types)
    ]


def literal_type_options(
    allowed_types: frozenset[str] | None,
    current: str | None = None,
) -> list[str]:
    """Return literal editors capable of producing the requested value types."""
    if allowed_types is None:
        options = list(LITERAL_TYPES)
    else:
        options = []
        for literal_type in LITERAL_TYPES:
            profile = profile_for_literal_type(literal_type)
            if profile_matches(profile, allowed_types):
                options.append(literal_type)
    if current and current not in options:
        options.append(current)
    return options


def allowed_types_for_hint(type_hint: str) -> frozenset[str] | None:
    """Map an engine function argument hint to Studio semantic types."""
    normalized = type_hint.lower()
    if normalized == "any":
        return None
    if normalized == "number":
        return NUMERIC_TYPES
    if normalized in SEQUENCE_HINTS:
        return frozenset({SEQUENCE})
    if normalized == "timestamp":
        return frozenset({TIMESTAMP, TIMESTAMP_NTZ})
    if normalized == "mapping":
        return frozenset({MAPPING})
    profile = profile_for_literal_type(normalized)
    return None if profile.kind == UNKNOWN else frozenset({profile.kind})


def compatible_function_names(
    names: Sequence[str],
    allowed_types: frozenset[str] | None,
) -> list[str]:
    """Filter fixed-return functions; retain dynamic functions until args resolve."""
    if allowed_types is None:
        return list(names)
    compatible: list[str] = []
    for name in names:
        contract = custom_functions.spec(name)
        return_hint = str(contract.get("return_type_hint") or "any").lower()
        if return_hint == "any" or ":" in return_hint:
            compatible.append(name)
            continue
        if profile_matches(profile_for_literal_type(return_hint), allowed_types):
            compatible.append(name)
    return compatible


def profile_for_operand(
    operand: Operand | None,
    columns: Mapping[str, ValueProfile],
    assigned: Mapping[str, ValueProfile] | None = None,
) -> ValueProfile:
    """Infer an authored operand profile from values and function metadata."""
    if operand is None:
        return ValueProfile()
    assigned_profiles = assigned or {}
    if operand.kind == "field":
        profile = columns.get(operand.field_name, ValueProfile())
    elif operand.kind == "assigned":
        profile = assigned_profiles.get(operand.assigned_field, ValueProfile())
    elif operand.kind == "literal":
        profile = profile_for_literal_type(operand.value_type, operand.value)
    elif operand.kind == "custom_function":
        profile = _function_profile(operand, columns, assigned_profiles)
    else:
        profile = ValueProfile()
    if operand.default_if_null is not None:
        fallback = profile_for_operand(operand.default_if_null, columns, assigned_profiles)
        effective = fallback if profile.kind == UNKNOWN else combine_profiles(profile, fallback)
        return ValueProfile(effective.kind, nullable=fallback.nullable)
    return profile


def assignment_profiles(
    ruleset: Ruleset,
    columns: Mapping[str, ValueProfile],
    *,
    before_rule: Rule | None = None,
) -> dict[str, ValueProfile]:
    """Infer target types committed before an optional selected rule executes."""
    profiles: dict[str, ValueProfile] = {}
    for rule in ruleset.ordered_rules():
        if before_rule is not None and rule.uid == before_rule.uid:
            break
        if not rule.active_flag:
            continue
        pending: dict[str, ValueProfile] = {}
        for assignment in rule.assignments:
            if not assignment.target_field:
                continue
            proposed = profile_for_operand(assignment.value, columns, profiles)
            existing = profiles.get(assignment.target_field)
            pending[assignment.target_field] = (
                proposed if existing is None else combine_profiles(existing, proposed)
            )
        # All assignments in a rule resolve against the same prior-rule snapshot.
        profiles.update(pending)
    return profiles


def combine_profiles(*profiles: ValueProfile) -> ValueProfile:
    """Return a conservative common profile for multiple possible values."""
    kinds = {profile.kind for profile in profiles if profile.kind != UNKNOWN}
    nullable = any(profile.nullable or profile.kind == UNKNOWN for profile in profiles)
    return _combined_kind(kinds, nullable=nullable)


def profile_for_literal_type(type_hint: str | None, value: Any = None) -> ValueProfile:
    """Map a canonical/alias literal hint or concrete value to a semantic type."""
    if isinstance(value, Mapping):
        return ValueProfile(MAPPING)
    if isinstance(value, (list, tuple, set)):
        return ValueProfile(SEQUENCE)
    normalized = (type_hint or "").lower()
    mapping = {
        "str": STRING,
        "string": STRING,
        "bool": BOOLEAN,
        "boolean": BOOLEAN,
        "int": INTEGER,
        "integer": INTEGER,
        "long": INTEGER,
        "decimal": NUMBER,
        "double": NUMBER,
        "float": NUMBER,
        "number": NUMBER,
        "date": DATE,
        "timestamp": TIMESTAMP,
        "timestamp_ntz": TIMESTAMP_NTZ,
        "array": SEQUENCE,
        "list": SEQUENCE,
        "sequence": SEQUENCE,
        "struct": MAPPING,
        "mapping": MAPPING,
        "null": UNKNOWN,
        "any": UNKNOWN,
    }
    if normalized in mapping:
        return ValueProfile(mapping[normalized], nullable=normalized == "null")
    return ValueProfile(_value_kind(value)) if not is_missing(value) else ValueProfile()


def _function_profile(
    operand: Operand,
    columns: Mapping[str, ValueProfile],
    assigned: Mapping[str, ValueProfile],
) -> ValueProfile:
    """Resolve fixed and argument-derived function return profiles."""
    if not operand.function:
        return ValueProfile()
    try:
        contract = custom_functions.spec(operand.function)
    except StopIteration:
        return ValueProfile()
    hint = str(contract.get("return_type_hint") or "any").lower()
    if ":" not in hint:
        return profile_for_literal_type(hint)
    mode, _, argument_name = hint.partition(":")
    argument = operand.args.get(argument_name)
    if mode == "same_as":
        return _argument_profile(argument, columns, assigned)
    if mode == "common_type":
        if isinstance(argument, Operand) and argument.kind == "literal":
            values = argument.value
            if not isinstance(values, (list, tuple, set)):
                return ValueProfile()
            hint = argument.value_type
            if hint in {"array", "list", "struct"}:
                hint = None
            profiles = [profile_for_literal_type(hint, item) for item in values]
        elif isinstance(argument, (list, tuple, set)):
            profiles = [_argument_profile(item, columns, assigned) for item in argument]
        else:
            return ValueProfile()
        return combine_profiles(*profiles) if profiles else ValueProfile()
    return ValueProfile()


def _argument_profile(
    value: Any,
    columns: Mapping[str, ValueProfile],
    assigned: Mapping[str, ValueProfile],
) -> ValueProfile:
    """Infer one custom-function argument or authored sequence item."""
    if isinstance(value, Operand):
        return profile_for_operand(value, columns, assigned)
    if isinstance(value, (list, tuple, set)):
        return ValueProfile(SEQUENCE, nullable=False)
    return profile_values([value])


def _combined_kind(kinds: set[str], *, nullable: bool) -> ValueProfile:
    """Collapse observed kinds while preserving safe numeric compatibility."""
    kinds.discard(UNKNOWN)
    if not kinds:
        return ValueProfile(UNKNOWN, nullable=nullable)
    if kinds <= NUMERIC_TYPES:
        kind = NUMBER if NUMBER in kinds else INTEGER
        return ValueProfile(kind, nullable=nullable)
    if len(kinds) == 1:
        return ValueProfile(next(iter(kinds)), nullable=nullable)
    return ValueProfile(MIXED, nullable=nullable)


def _value_kind(value: Any) -> str:
    """Return the semantic family for one non-null concrete value."""
    if isinstance(value, bool):
        return BOOLEAN
    if isinstance(value, Integral):
        return INTEGER
    if isinstance(value, Decimal):
        return NUMBER
    if isinstance(value, Real):
        return NUMBER
    if isinstance(value, datetime):
        return TIMESTAMP if value.tzinfo is not None and value.utcoffset() is not None else TIMESTAMP_NTZ
    if isinstance(value, date):
        return DATE
    if isinstance(value, str):
        return STRING
    if isinstance(value, Mapping):
        return MAPPING
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return SEQUENCE
    if isinstance(value, set):
        return SEQUENCE
    return UNKNOWN


def _python_scalar(value: Any) -> Any:
    """Convert NumPy/pandas scalars without changing nested authored values."""
    if isinstance(value, (str, bytes, bytearray, Mapping, Sequence, set)):
        return value
    scalar = getattr(value, "item", None)
    if callable(scalar):
        try:
            return scalar()
        except (TypeError, ValueError):
            return value
    return value


__all__ = [
    "CONCRETE_TYPES",
    "MIXED",
    "NUMERIC_TYPES",
    "SCALAR_TYPES",
    "UNKNOWN",
    "ValueProfile",
    "allowed_types_for_hint",
    "assignment_profiles",
    "column_profiles",
    "combine_profiles",
    "compatible_function_names",
    "compatible_names",
    "is_missing",
    "left_types_for_operator",
    "literal_type_options",
    "normalized_records",
    "operator_options",
    "profile_for_literal_type",
    "profile_for_operand",
    "profile_matches",
    "right_types_for_condition",
]
