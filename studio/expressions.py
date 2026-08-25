"""Human-readable expressions generated from the Studio authoring model."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from .schema import (
    OPERATORS_BY_NAME,
    Assignment,
    Condition,
    ConditionGroup,
    Operand,
    Rule,
)


def operand_expression(operand: Operand | None) -> str:
    """Describe one operand, including its null fallback, for an author."""
    if operand is None:
        return "[choose a value]"

    if operand.kind == "field":
        expression = (
            f"input field {_quoted(operand.field_name)}"
            if operand.field_name
            else "[choose an input field]"
        )
    elif operand.kind == "assigned":
        expression = (
            f"prior assignment {_quoted(operand.assigned_field)}"
            if operand.assigned_field
            else "[choose a prior assignment]"
        )
    elif operand.kind == "custom_function":
        expression = _function_expression(operand)
    elif operand.kind == "literal":
        expression = _literal_expression(operand)
    else:
        expression = "[choose a value source]"

    if operand.default_if_null is not None:
        fallback = operand_expression(operand.default_if_null)
        expression += f" (use {fallback} when null)"
    return expression


def condition_expression(condition: Condition, *, include_status: bool = True) -> str:
    """Describe one comparison with every runtime-relevant authoring option."""
    specification = OPERATORS_BY_NAME.get(condition.operator)
    operator = specification.label if specification else "[choose a comparison]"
    expression = f"{operand_expression(condition.left)} {operator}"
    if specification is None or specification.arity != 1:
        expression += f" {operand_expression(condition.right)}"

    if (
        specification is not None
        and specification.supports_tolerance
        and Decimal(str(condition.tolerance_abs)) != 0
    ):
        expression += f" (absolute tolerance {condition.tolerance_abs})"
    if condition.error_on_null and condition.operator not in {"is_null", "is_not_null"}:
        expression += "; raise an error when an operand is null"
    if include_status and not condition.active_flag:
        expression = f"Ignored because this condition is inactive: {expression}"
    return expression


def group_expression(group: ConditionGroup) -> str:
    """Describe a nested logical group as an indented, plain-language expression."""
    return "\n".join(_group_lines(group, 0))


def assignment_expression(assignment: Assignment) -> str:
    """Describe one rule result assignment."""
    target = (
        f"output field {_quoted(assignment.target_field)}"
        if assignment.target_field
        else "[choose an output field]"
    )
    return f"Set {target} to {operand_expression(assignment.value)}."


def rule_expression(rule: Rule) -> str:
    """Describe a complete rule as its composed IF/THEN behavior."""
    lines: list[str] = []
    if not rule.active_flag:
        lines.append("This rule is inactive and will be skipped.")
    lines.extend(["IF", *_indent(_group_lines(rule.conditions, 0), 1), "THEN"])
    if rule.assignments:
        lines.extend(f"  • {assignment_expression(item)}" for item in rule.assignments)
    else:
        lines.append("  • [add an assignment]")
    if rule.stop_on_match:
        lines.append("After a match, stop before evaluating later rules.")
    return "\n".join(lines)


def _function_expression(operand: Operand) -> str:
    """Describe a custom-function call and any nested authoring operands."""
    if not operand.function:
        return "[choose a function]"
    arguments = ", ".join(
        f"{name} = {_argument_expression(value)}" for name, value in operand.args.items()
    )
    return f"{operand.function}({arguments})"


def _argument_expression(value: Any) -> str:
    """Describe recursively nested custom-function argument data."""
    if isinstance(value, Operand):
        return operand_expression(value)
    if isinstance(value, Mapping):
        pairs = ", ".join(
            f"{name}: {_argument_expression(item)}" for name, item in value.items()
        )
        return "{" + pairs + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_argument_expression(item) for item in value) + "]"
    if isinstance(value, set):
        return "[" + ", ".join(sorted(_argument_expression(item) for item in value)) + "]"
    return _value_expression(value)


def _group_lines(group: ConditionGroup, depth: int) -> list[str]:
    """Return the recursive lines for one logical group."""
    prefix = "  " * depth
    if not group.children:
        return [f"{prefix}Always matches because this group has no conditions."]

    requirement = (
        "All of the following must be true:"
        if group.logical_operator == "all"
        else "Any of the following are true:"
    )
    lines = [f"{prefix}{requirement}"]
    for child in group.children:
        if isinstance(child, ConditionGroup):
            nested = _group_lines(child, depth + 1)
            lines.append(f"{prefix}  • {nested[0].lstrip()}")
            lines.extend(nested[1:])
        else:
            lines.append(f"{prefix}  • {condition_expression(child)}")
    return lines


def _indent(lines: list[str], levels: int) -> list[str]:
    """Indent already formatted expression lines by a fixed number of levels."""
    prefix = "  " * levels
    return [prefix + line for line in lines]


def _quoted(value: str) -> str:
    """Quote an author-provided identifier without losing Unicode characters."""
    return json.dumps(value, ensure_ascii=False)


def _value_expression(value: Any) -> str:
    """Format a literal value compactly and deterministically."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return 'empty text ("")' if not value else _quoted(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime, time)):
        return _quoted(value.isoformat())
    if isinstance(value, Mapping):
        pairs = ", ".join(
            f"{_quoted(str(name))}: {_value_expression(item)}" for name, item in value.items()
        )
        return "{" + pairs + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_value_expression(item) for item in value) + "]"
    if isinstance(value, set):
        return "[" + ", ".join(sorted(_value_expression(item) for item in value)) + "]"
    return str(value)


def _literal_expression(operand: Operand) -> str:
    """Format a literal using the declared type that the compiler will apply."""
    value = operand.value
    type_hint = operand.value_type or ""
    if type_hint in {"decimal", "double", "integer"}:
        return str(value) if value is not None and value != "" else "[enter a number]"
    if type_hint in {"date", "timestamp", "timestamp_ntz"}:
        if value is None or value == "":
            return f"[enter a {type_hint.replace('_', ' ')}]"
        label = type_hint.replace("_", " ")
        rendered = value.isoformat() if isinstance(value, (date, datetime, time)) else str(value)
        return f"{label} {_quoted(rendered)}"
    return _value_expression(value)


__all__ = [
    "assignment_expression",
    "condition_expression",
    "group_expression",
    "operand_expression",
    "rule_expression",
]
