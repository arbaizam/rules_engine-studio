"""YAML round-trip and draft validation.

The exported document is the studio's contract with ``rules_engine``. If the
engine's own loader expects a different shape, change ``schema.to_dict`` /
``from_dict`` and this module -- nothing in the UI layer knows the file format.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import yaml

from .schema import (
    OPERATORS_BY_NAME,
    Condition,
    ConditionGroup,
    Operand,
    Rule,
    Ruleset,
)


class _Dumper(yaml.SafeDumper):
    """Block style, two-space indent, no anchors/aliases."""

    def ignore_aliases(self, data: Any) -> bool:  # noqa: D102
        return True

    def increase_indent(self, flow: bool = False, indentless: bool = False):  # noqa: D102
        return super().increase_indent(flow, False)


def to_yaml(ruleset: Ruleset) -> str:
    return yaml.dump(
        ruleset.to_dict(),
        Dumper=_Dumper,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=100,
    )


def from_yaml(text: str) -> Ruleset:
    data = yaml.safe_load(text)
    if data is None:
        raise ValueError("The file is empty.")
    return Ruleset.from_dict(data)


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Issue:
    severity: str  # "error" | "warning"
    where: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{self.where}: {self.message}"


def _check_operand(
    operand: Operand,
    where: str,
    role: str,
    columns: Iterable[str],
    functions: Iterable[str],
    issues: list[Issue],
) -> None:
    columns = list(columns)
    if operand.kind == "field":
        if not operand.field_name:
            issues.append(Issue("error", where, f"{role} has no column selected."))
        elif columns and operand.field_name not in columns:
            issues.append(
                Issue(
                    "warning",
                    where,
                    f"{role} reads '{operand.field_name}', which is not in the sample data.",
                )
            )
    elif operand.kind == "function":
        if not operand.function:
            issues.append(Issue("error", where, f"{role} has no function selected."))
        elif operand.function not in set(functions):
            issues.append(
                Issue(
                    "warning",
                    where,
                    f"{role} calls '{operand.function}', which is not registered in this studio.",
                )
            )
        for arg in operand.args:
            _check_operand(arg, where, f"{role} argument", columns, functions, issues)


def _check_group(
    group: ConditionGroup,
    where: str,
    columns: Iterable[str],
    functions: Iterable[str],
    issues: list[Issue],
) -> None:
    for child in group.children:
        if isinstance(child, ConditionGroup):
            if child.is_empty():
                issues.append(Issue("warning", where, "A condition group is empty."))
            _check_group(child, where, columns, functions, issues)
            continue
        _check_condition(child, where, columns, functions, issues)


def _check_condition(
    condition: Condition,
    where: str,
    columns: Iterable[str],
    functions: Iterable[str],
    issues: list[Issue],
) -> None:
    spec = OPERATORS_BY_NAME.get(condition.operator)
    if spec is None:
        issues.append(
            Issue("error", where, f"Unknown operator '{condition.operator}'.")
        )
    _check_operand(condition.left, where, "Condition left side", columns, functions, issues)
    if spec is not None and spec.arity == 2:
        if condition.right is None:
            issues.append(
                Issue("error", where, f"'{spec.label}' needs a right-hand value.")
            )
        else:
            _check_operand(
                condition.right, where, "Condition right side", columns, functions, issues
            )
        if condition.operator == "between":
            right = condition.right
            if right is not None and right.kind == "literal":
                if not isinstance(right.value, (list, tuple)) or len(right.value) != 2:
                    issues.append(
                        Issue("error", where, "'is between' needs exactly two values.")
                    )


def validate(
    ruleset: Ruleset,
    columns: Iterable[str] = (),
    functions: Iterable[str] = (),
) -> list[Issue]:
    """Return every problem in the draft. Errors block export; warnings do not."""
    issues: list[Issue] = []
    columns = list(columns)
    functions = list(functions)

    if not ruleset.ruleset_id.strip():
        issues.append(Issue("error", "Ruleset", "Give the ruleset an id."))
    if not ruleset.version.strip():
        issues.append(Issue("error", "Ruleset", "Give the ruleset a version."))
    if not ruleset.rules:
        issues.append(Issue("warning", "Ruleset", "No rules yet."))

    seen_ids: dict[str, int] = {}
    seen_orders: dict[int, list[str]] = {}

    for rule in ruleset.ordered_rules():
        where = rule.rule_id or "(unnamed rule)"
        if not rule.rule_id.strip():
            issues.append(Issue("error", where, "Give the rule an id."))
        seen_ids[rule.rule_id] = seen_ids.get(rule.rule_id, 0) + 1
        seen_orders.setdefault(rule.rule_order, []).append(rule.rule_id)

        if rule.conditions.is_empty():
            issues.append(
                Issue("warning", where, "No conditions -- this rule matches every row.")
            )
        _check_group(rule.conditions, where, columns, functions, issues)

        if not rule.assignments:
            issues.append(Issue("warning", where, "No assignments -- this rule sets nothing."))
        targets: set[str] = set()
        for assignment in rule.assignments:
            if not assignment.target_field.strip():
                issues.append(Issue("error", where, "An assignment has no target field."))
            elif assignment.target_field in targets:
                issues.append(
                    Issue(
                        "warning",
                        where,
                        f"'{assignment.target_field}' is assigned twice in this rule; "
                        "the last one wins.",
                    )
                )
            targets.add(assignment.target_field)
            _check_operand(
                assignment.value,
                where,
                f"Assignment to '{assignment.target_field or '?'}'",
                columns,
                functions,
                issues,
            )

    for rule_id, count in seen_ids.items():
        if count > 1 and rule_id:
            issues.append(Issue("error", rule_id, f"Rule id used {count} times."))
    for order, ids in seen_orders.items():
        if len(ids) > 1:
            issues.append(
                Issue(
                    "warning",
                    "Ruleset",
                    f"rule_order {order} is shared by {', '.join(i or '?' for i in ids)}; "
                    "evaluation order between them is not pinned.",
                )
            )

    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity == "error" for i in issues)


def renumber(ruleset: Ruleset, step: int = 10) -> None:
    """Rewrite rule_order to a clean, gapped sequence in current order."""
    for index, rule in enumerate(ruleset.ordered_rules(), start=1):
        rule.rule_order = index * step


__all__ = [
    "Issue",
    "from_yaml",
    "has_errors",
    "renumber",
    "to_yaml",
    "validate",
    "Rule",
]
