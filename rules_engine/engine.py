"""Small, deterministic rule evaluator with human-readable explanations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import Condition, FieldDefinition, Rule


OPERATOR_LABELS = {
    "equals": "is",
    "not_equals": "is not",
    "greater_than": "is greater than",
    "greater_or_equal": "is at least",
    "less_than": "is less than",
    "less_or_equal": "is at most",
    "contains": "contains",
    "not_contains": "does not contain",
    "starts_with": "starts with",
    "in": "is one of",
    "is_empty": "is empty",
    "is_not_empty": "is not empty",
}

TYPE_OPERATORS = {
    "number": [
        "equals",
        "not_equals",
        "greater_than",
        "greater_or_equal",
        "less_than",
        "less_or_equal",
        "is_empty",
        "is_not_empty",
    ],
    "boolean": ["equals", "not_equals"],
    "text": [
        "equals",
        "not_equals",
        "contains",
        "not_contains",
        "starts_with",
        "in",
        "is_empty",
        "is_not_empty",
    ],
    "date": [
        "equals",
        "not_equals",
        "greater_than",
        "greater_or_equal",
        "less_than",
        "less_or_equal",
        "is_empty",
        "is_not_empty",
    ],
}


@dataclass(frozen=True)
class ConditionResult:
    matched: bool
    field: str
    actual: Any
    expected: Any
    explanation: str


@dataclass(frozen=True)
class EvaluationResult:
    rule_id: str
    rule_name: str
    matched: bool
    condition_results: list[ConditionResult]
    outcome: dict[str, Any] | None


def _field_value(record: dict[str, Any], field_name: str) -> Any:
    """Read flat or dotted fields, returning None when a segment is absent."""
    value: Any = record
    for segment in field_name.split("."):
        if not isinstance(value, dict) or segment not in value:
            return None
        value = value[segment]
    return value


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _equal(actual: Any, expected: Any) -> bool:
    actual_number, expected_number = _number(actual), _number(expected)
    if actual_number is not None and expected_number is not None:
        return actual_number == expected_number
    if isinstance(actual, bool) or isinstance(expected, bool):
        return str(actual).lower() == str(expected).lower()
    return str(actual).casefold() == str(expected).casefold()


def _compare(actual: Any, expected: Any, operator: str) -> bool:
    if operator in {"is_empty", "is_not_empty"}:
        empty = actual is None or actual == "" or actual == []
        return empty if operator == "is_empty" else not empty
    if actual is None:
        return False
    if operator == "equals":
        return _equal(actual, expected)
    if operator == "not_equals":
        return not _equal(actual, expected)
    if operator in {"contains", "not_contains"}:
        if isinstance(actual, (list, tuple, set)):
            contains = any(_equal(item, expected) for item in actual)
        else:
            contains = str(expected).casefold() in str(actual).casefold()
        return contains if operator == "contains" else not contains
    if operator == "starts_with":
        return str(actual).casefold().startswith(str(expected).casefold())
    if operator == "in":
        options = expected if isinstance(expected, list) else str(expected).split(",")
        return any(_equal(actual, item.strip() if isinstance(item, str) else item) for item in options)

    left_number, right_number = _number(actual), _number(expected)
    if left_number is not None and right_number is not None:
        left, right = left_number, right_number
    else:
        left, right = str(actual).casefold(), str(expected).casefold()
    comparisons = {
        "greater_than": left > right,
        "greater_or_equal": left >= right,
        "less_than": left < right,
        "less_or_equal": left <= right,
    }
    return comparisons.get(operator, False)


def display_value(value: Any) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if value is None or value == "":
        return "(blank)"
    return str(value)


def describe_condition(condition: Condition, fields: list[FieldDefinition]) -> str:
    field_label = next(
        (definition.label for definition in fields if definition.key == condition.field),
        condition.field.replace("_", " ").title() or "Choose a field",
    )
    operator_label = OPERATOR_LABELS.get(condition.operator, condition.operator.replace("_", " "))
    if condition.operator in {"is_empty", "is_not_empty"}:
        return f"{field_label} {operator_label}"
    return f"{field_label} {operator_label} {display_value(condition.value)}"


def evaluate_condition(
    condition: Condition, fields: list[FieldDefinition], record: dict[str, Any]
) -> ConditionResult:
    actual = _field_value(record, condition.field)
    matched = _compare(actual, condition.value, condition.operator)
    expectation = describe_condition(condition, fields)
    explanation = (
        f"{expectation} — received {display_value(actual)}"
        if condition.operator not in {"is_empty", "is_not_empty"}
        else f"{expectation} — received {display_value(actual)}"
    )
    return ConditionResult(
        matched=matched,
        field=condition.field,
        actual=actual,
        expected=condition.value,
        explanation=explanation,
    )


def evaluate_rule(rule: Rule, record: dict[str, Any]) -> EvaluationResult:
    results = [evaluate_condition(condition, rule.fields, record) for condition in rule.conditions]
    matched = bool(results) and (
        all(result.matched for result in results)
        if rule.match == "all"
        else any(result.matched for result in results)
    )
    return EvaluationResult(
        rule_id=rule.id,
        rule_name=rule.name,
        matched=matched,
        condition_results=results,
        outcome=rule.outcome.to_dict() if matched else None,
    )


def evaluate_rulebook(rules: list[Rule], record: dict[str, Any]) -> list[EvaluationResult]:
    """Evaluate enabled rules in priority order (lower numbers run first)."""
    enabled_rules = sorted((rule for rule in rules if rule.enabled), key=lambda item: item.priority)
    return [evaluate_rule(rule, record) for rule in enabled_rules]


def validate_rule(rule: Rule) -> list[str]:
    errors: list[str] = []
    if not rule.name.strip():
        errors.append("Give the rule a name.")
    if not rule.conditions:
        errors.append("Add at least one condition.")
    field_keys = {definition.key for definition in rule.fields}
    for index, condition in enumerate(rule.conditions, start=1):
        if condition.field not in field_keys:
            errors.append(f"Condition {index} needs a valid field.")
        if condition.operator not in OPERATOR_LABELS:
            errors.append(f"Condition {index} needs a valid comparison.")
        if condition.operator not in {"is_empty", "is_not_empty"} and (
            condition.value is None or condition.value == "" or condition.value == []
        ):
            errors.append(f"Condition {index} needs a value to compare.")
    if not rule.outcome.value.strip():
        errors.append("Describe what should happen when the rule matches.")
    return errors
