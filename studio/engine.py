"""Preview evaluator.

This mirrors the semantics documented in the 0.4.0 audit review so authors get
useful feedback while drafting:

  * rules run in ``rule_order``; inactive rules are skipped entirely
  * inactive conditions are skipped; an inactive rule cannot match
  * assignments merge into one dict, last write wins across and within rules
  * ``stop_on_match`` only halts traversal when the rule actually matched
  * a row that raises is quarantined: ``error`` set, ``matched`` False,
    ``matched_rule_ids`` empty, ``assign`` None, full-audit arrays empty
  * ``full_audit`` adds observability only -- it never changes the decision

It is NOT the engine. It runs row-at-a-time in pure Python with no Spark and no
type coercion rules from ``rules_engine``. Treat the output as a drafting aid;
parity is only proven once the studio calls ``evaluate_dataframe`` for real.
See ``docs/PARITY.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from . import custom_functions
from .schema import (
    OPERATORS_BY_NAME,
    Assignment,
    Condition,
    ConditionGroup,
    Operand,
    Rule,
    Ruleset,
)

COMPACT_FIELDS = ("error", "matched", "matched_rule_ids", "assign")
FULL_AUDIT_EXTRA_FIELDS = ("matched_rules", "first_matched_rule_trace", "assignment_results")


class OperandError(Exception):
    """Raised when an operand cannot be resolved for a row."""


@dataclass
class Resolution:
    """What an operand produced, and where it came from."""

    value: Any
    source: str  # field | literal | function
    detail: str
    children: list["Resolution"] = field(default_factory=list)


# --------------------------------------------------------------------------
# operand resolution
# --------------------------------------------------------------------------


def resolve_operand(
    operand: Operand,
    row: dict[str, Any],
    functions: dict[str, Callable[..., Any]] | None = None,
) -> Resolution:
    functions = functions if functions is not None else custom_functions.registry()

    if operand.kind == "field":
        if not operand.field_name:
            raise OperandError("Condition refers to no column.")
        if operand.field_name not in row:
            raise OperandError(f"Column '{operand.field_name}' is not in the data.")
        return Resolution(row[operand.field_name], "field", operand.field_name)

    if operand.kind == "function":
        if operand.function not in functions:
            raise OperandError(f"Custom function '{operand.function}' is not registered.")
        children = [resolve_operand(a, row, functions) for a in operand.args]
        try:
            value = functions[operand.function](*[c.value for c in children])
        except Exception as exc:  # surface the author's bug, don't swallow it
            raise OperandError(f"{operand.function}() raised {type(exc).__name__}: {exc}") from exc
        return Resolution(value, "function", f"{operand.function}()", children)

    return Resolution(coerce_literal(operand), "literal", operand.value_type)


def coerce_literal(operand: Operand) -> Any:
    """Turn the editor's text into the type the author picked."""
    value = operand.value
    kind = operand.value_type

    if kind == "null":
        return None
    if value is None:
        return None
    if kind == "boolean":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "1", "yes", "y")
    if kind == "integer":
        return int(str(value).strip())
    if kind == "number":
        return float(str(value).strip())
    if kind == "list":
        if isinstance(value, (list, tuple)):
            return list(value)
        return [part.strip() for part in str(value).split(",") if part.strip()]
    return value


# --------------------------------------------------------------------------
# comparison
# --------------------------------------------------------------------------


def _is_null(value: Any) -> bool:
    return value is None or (isinstance(value, float) and value != value)


def compare(operator: str, left: Any, right: Any) -> bool | None:
    """Return the boolean result, or ``None`` when a null makes it undefined."""
    if operator == "is_null":
        return _is_null(left)
    if operator == "is_not_null":
        return not _is_null(left)

    if _is_null(left) or _is_null(right):
        return None

    if operator == "equals":
        return left == right
    if operator == "not_equals":
        return left != right
    if operator in ("greater_than", "greater_than_or_equal", "less_than", "less_than_or_equal"):
        try:
            if operator == "greater_than":
                return left > right
            if operator == "greater_than_or_equal":
                return left >= right
            if operator == "less_than":
                return left < right
            return left <= right
        except TypeError as exc:
            raise OperandError(
                f"Cannot compare {type(left).__name__} with {type(right).__name__}."
            ) from exc
    if operator == "in_list":
        return left in _as_sequence(right)
    if operator == "not_in_list":
        return left not in _as_sequence(right)
    if operator == "contains":
        return str(right) in str(left)
    if operator == "starts_with":
        return str(left).startswith(str(right))
    if operator == "ends_with":
        return str(left).endswith(str(right))
    if operator == "matches_regex":
        return re.search(str(right), str(left)) is not None
    if operator == "between":
        bounds = _as_sequence(right)
        if len(bounds) != 2:
            raise OperandError("'is between' needs exactly two values.")
        low, high = bounds
        return low <= left <= high

    raise OperandError(f"Unknown operator '{operator}'.")


def _as_sequence(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [part.strip() for part in str(value).split(",") if part.strip()]


# --------------------------------------------------------------------------
# conditions
# --------------------------------------------------------------------------


def evaluate_condition(
    condition: Condition,
    row: dict[str, Any],
    functions: dict[str, Callable[..., Any]] | None = None,
) -> dict[str, Any]:
    left = resolve_operand(condition.left, row, functions)
    right = None
    spec = OPERATORS_BY_NAME.get(condition.operator)
    if (spec is None or spec.arity == 2) and condition.right is not None:
        right = resolve_operand(condition.right, row, functions)

    raw = compare(condition.operator, left.value, right.value if right else None)
    if raw is None:
        policy = condition.null_result or "false"
        matched = True if policy == "true" else False
        null_applied = policy
    else:
        matched = bool(raw)
        null_applied = None

    return {
        "condition_id": condition.condition_id or None,
        "expression": condition.describe(),
        "operator": condition.operator,
        "left_value": left.value,
        "right_value": right.value if right else None,
        "matched": matched,
        "null_result_applied": null_applied,
        "left_resolution": left,
        "right_resolution": right,
    }


def evaluate_group(
    group: ConditionGroup,
    row: dict[str, Any],
    functions: dict[str, Callable[..., Any]] | None = None,
) -> dict[str, Any]:
    if not group.active_flag:
        return {"logic": group.logic, "matched": True, "skipped": True, "children": []}

    children: list[dict[str, Any]] = []
    considered: list[bool] = []

    for child in group.children:
        if isinstance(child, ConditionGroup):
            result = evaluate_group(child, row, functions)
            children.append({"kind": "group", **result})
            if not result.get("skipped"):
                considered.append(result["matched"])
            continue
        if not child.active_flag:
            children.append(
                {"kind": "condition", "expression": child.describe(), "skipped": True, "matched": True}
            )
            continue
        result = evaluate_condition(child, row, functions)
        children.append({"kind": "condition", **result})
        considered.append(result["matched"])

    if not considered:
        matched = True  # an empty (or fully inactive) group matches everything
    elif group.logic == "any":
        matched = any(considered)
    else:
        matched = all(considered)

    return {"logic": group.logic, "matched": matched, "skipped": False, "children": children}


# --------------------------------------------------------------------------
# rules and rows
# --------------------------------------------------------------------------


def evaluate_rule(
    rule: Rule,
    row: dict[str, Any],
    functions: dict[str, Callable[..., Any]] | None = None,
) -> dict[str, Any]:
    trace = evaluate_group(rule.conditions, row, functions)
    return {
        "rule_id": rule.rule_id,
        "rule_order": rule.rule_order,
        "matched": trace["matched"],
        "stop_on_match": rule.stop_on_match,
        "condition_trace": trace,
    }


def evaluate_assignment(
    assignment: Assignment,
    row: dict[str, Any],
    functions: dict[str, Callable[..., Any]] | None = None,
) -> Resolution:
    return resolve_operand(assignment.value, row, functions)


def empty_result(full_audit: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "error": None,
        "matched": False,
        "matched_rule_ids": [],
        "assign": None,
    }
    if full_audit:
        result["matched_rules"] = []
        result["first_matched_rule_trace"] = None
        result["assignment_results"] = []
    return result


def evaluate_row(
    ruleset: Ruleset,
    row: dict[str, Any],
    functions: dict[str, Callable[..., Any]] | None = None,
    full_audit: bool = False,
) -> dict[str, Any]:
    result = empty_result(full_audit)
    applied: list[dict[str, Any]] = []
    matched_rule_ids: list[str] = []
    matched_rules: list[dict[str, Any]] = []
    first_trace: dict[str, Any] | None = None
    assignments: dict[str, Any] = {}

    try:
        for rule in ruleset.ordered_rules():
            if not rule.active_flag:
                continue
            outcome = evaluate_rule(rule, row, functions)

            if not outcome["matched"]:
                continue

            matched_rule_ids.append(rule.rule_id)
            if full_audit:
                matched_rules.append(
                    {
                        "rule_id": rule.rule_id,
                        "rule_order": rule.rule_order,
                        "stop_on_match": rule.stop_on_match,
                    }
                )
                if first_trace is None:
                    first_trace = outcome["condition_trace"]

            for assignment in rule.assignments:
                resolution = evaluate_assignment(assignment, row, functions)
                assignments[assignment.target_field] = resolution.value
                applied.append(
                    {
                        "rule_id": rule.rule_id,
                        "target_field": assignment.target_field,
                        "value": resolution.value,
                        "effective": True,
                        "overridden_by": None,
                    }
                )

            if rule.stop_on_match:
                break

    except Exception as exc:  # quarantine the row, keep the sibling shape intact
        result = empty_result(full_audit)
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    result["matched"] = bool(matched_rule_ids)
    result["matched_rule_ids"] = matched_rule_ids
    result["assign"] = assignments or None

    if full_audit:
        _mark_overrides(applied)
        result["matched_rules"] = matched_rules
        result["first_matched_rule_trace"] = first_trace
        result["assignment_results"] = applied

    return result


def _mark_overrides(applied: list[dict[str, Any]]) -> None:
    """Last write per target field is effective; earlier ones name their winner."""
    last_index: dict[str, int] = {}
    for index, item in enumerate(applied):
        last_index[item["target_field"]] = index
    for index, item in enumerate(applied):
        winner = last_index[item["target_field"]]
        if winner != index:
            item["effective"] = False
            item["overridden_by"] = applied[winner]["rule_id"]


def evaluate_rows(
    ruleset: Ruleset,
    rows: list[dict[str, Any]],
    functions: dict[str, Callable[..., Any]] | None = None,
    full_audit: bool = False,
) -> list[dict[str, Any]]:
    functions = functions if functions is not None else custom_functions.registry()
    return [evaluate_row(ruleset, row, functions, full_audit) for row in rows]


def output_columns(column_prefix: str = "rules_engine", full_audit: bool = False) -> list[str]:
    """Column names ``evaluate_dataframe`` appends, in contract order."""
    names = list(COMPACT_FIELDS)
    if full_audit:
        names += list(FULL_AUDIT_EXTRA_FIELDS)
    names += ["ruleset", "engine_version"]
    return [f"{column_prefix}_{name}" for name in names]
