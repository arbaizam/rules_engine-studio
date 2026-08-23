"""Draft-side ruleset model for Rules Engine Studio.

This module is the studio's *editing* model. It is deliberately independent of
``rules_engine`` so the app runs with nothing installed but pandas + PyYAML, and
so an in-progress draft is allowed to be invalid while someone is still typing.

SCHEMA PARITY -- READ THIS FIRST
--------------------------------
The field names below were inferred from the 0.4.0 audit review (models.py line
references for Rule / Condition / Assignment, the operand resolution path in
runtime.py, and the serializer's content-hash exclusions). They have NOT been
checked against the real ``rules_engine.models`` / ``rules_engine.enums``.

Everything version-sensitive is confined to this file plus ``yaml_io.py``:
  * OPERATORS          -- confirm against rules_engine.enums
  * NULL_RESULTS       -- confirm against runtime._resolve_null_result
  * *.to_dict/from_dict -- confirm against the real YAML loader / DeltaRowSerializer

Once the real model is available, reconcile here and the UI follows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

# --------------------------------------------------------------------------
# operators
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class OperatorSpec:
    name: str
    label: str
    arity: int  # 1 = left only (is_null), 2 = left + right
    hint: str = ""


OPERATORS: tuple[OperatorSpec, ...] = (
    OperatorSpec("equals", "equals", 2),
    OperatorSpec("not_equals", "does not equal", 2),
    OperatorSpec("greater_than", "is greater than", 2),
    OperatorSpec("greater_than_or_equal", "is at least", 2),
    OperatorSpec("less_than", "is less than", 2),
    OperatorSpec("less_than_or_equal", "is at most", 2),
    OperatorSpec("in_list", "is one of", 2, "Right side should be a list literal."),
    OperatorSpec("not_in_list", "is not one of", 2, "Right side should be a list literal."),
    OperatorSpec("contains", "contains", 2),
    OperatorSpec("starts_with", "starts with", 2),
    OperatorSpec("ends_with", "ends with", 2),
    OperatorSpec("matches_regex", "matches regex", 2),
    OperatorSpec("between", "is between", 2, "Right side should be a 2-item list literal."),
    OperatorSpec("is_null", "is empty", 1),
    OperatorSpec("is_not_null", "is not empty", 1),
)

OPERATORS_BY_NAME: dict[str, OperatorSpec] = {op.name: op for op in OPERATORS}
OPERATOR_NAMES: list[str] = [op.name for op in OPERATORS]

# How a condition resolves when an operand is null. ``None`` means "engine default".
NULL_RESULTS = ("false", "true", "null")

LITERAL_TYPES = ("string", "number", "integer", "boolean", "date", "list", "null")

LOGIC_MODES = ("all", "any")


def _uid() -> str:
    return uuid.uuid4().hex[:10]


# --------------------------------------------------------------------------
# operands
# --------------------------------------------------------------------------


@dataclass
class Operand:
    """A value source: a column, a literal, or a registered custom function."""

    kind: str = "literal"  # field | literal | function
    field_name: str = ""
    value: Any = None
    value_type: str = "string"
    function: str = ""
    args: list["Operand"] = field(default_factory=list)
    uid: str = field(default_factory=_uid)

    # -- display ----------------------------------------------------------
    def describe(self) -> str:
        if self.kind == "field":
            return self.field_name or "(no column)"
        if self.kind == "function":
            inner = ", ".join(a.describe() for a in self.args)
            return f"{self.function or '(no function)'}({inner})"
        if self.value is None:
            return "null"
        if isinstance(self.value, str):
            return f'"{self.value}"'
        return str(self.value)

    # -- serialisation ----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        if self.kind == "field":
            return {"field": self.field_name}
        if self.kind == "function":
            return {"function": self.function, "args": [a.to_dict() for a in self.args]}
        out: dict[str, Any] = {"literal": self.value}
        if self.value_type in ("date",):  # keep the intent round-trippable
            out["type"] = self.value_type
        return out

    @classmethod
    def from_dict(cls, data: Any) -> "Operand":
        # Bare scalars are treated as literals so hand-written YAML stays terse.
        if not isinstance(data, dict):
            return cls(kind="literal", value=data, value_type=infer_literal_type(data))
        if "field" in data:
            return cls(kind="field", field_name=str(data["field"] or ""))
        if "function" in data:
            raw_args = data.get("args") or []
            return cls(
                kind="function",
                function=str(data["function"] or ""),
                args=[cls.from_dict(a) for a in raw_args],
            )
        value = data.get("literal", data.get("value"))
        return cls(
            kind="literal",
            value=value,
            value_type=str(data.get("type") or infer_literal_type(value)),
        )

    def copy(self) -> "Operand":
        return Operand(
            kind=self.kind,
            field_name=self.field_name,
            value=list(self.value) if isinstance(self.value, list) else self.value,
            value_type=self.value_type,
            function=self.function,
            args=[a.copy() for a in self.args],
        )


def infer_literal_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, (list, tuple)):
        return "list"
    return "string"


# --------------------------------------------------------------------------
# conditions
# --------------------------------------------------------------------------


@dataclass
class Condition:
    left: Operand = field(default_factory=lambda: Operand(kind="field"))
    operator: str = "equals"
    right: Operand | None = field(default_factory=Operand)
    condition_id: str = ""
    active_flag: bool = True
    null_result: str | None = None
    uid: str = field(default_factory=_uid)

    def describe(self) -> str:
        spec = OPERATORS_BY_NAME.get(self.operator)
        label = spec.label if spec else self.operator
        if spec and spec.arity == 1:
            return f"{self.left.describe()} {label}"
        right = self.right.describe() if self.right else "(none)"
        return f"{self.left.describe()} {label} {right}"

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.condition_id:
            out["condition_id"] = self.condition_id
        out["left"] = self.left.to_dict()
        out["operator"] = self.operator
        spec = OPERATORS_BY_NAME.get(self.operator)
        if (spec is None or spec.arity == 2) and self.right is not None:
            out["right"] = self.right.to_dict()
        if not self.active_flag:
            out["active_flag"] = False
        if self.null_result:
            out["null_result"] = self.null_result
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Condition":
        right = data.get("right")
        return cls(
            left=Operand.from_dict(data.get("left")),
            operator=str(data.get("operator") or "equals"),
            right=Operand.from_dict(right) if right is not None else None,
            condition_id=str(data.get("condition_id") or ""),
            active_flag=bool(data.get("active_flag", True)),
            null_result=data.get("null_result"),
        )

    def copy(self) -> "Condition":
        return Condition(
            left=self.left.copy(),
            operator=self.operator,
            right=self.right.copy() if self.right else None,
            condition_id=self.condition_id,
            active_flag=self.active_flag,
            null_result=self.null_result,
        )


@dataclass
class ConditionGroup:
    logic: str = "all"  # all | any
    active_flag: bool = True
    children: list[Any] = field(default_factory=list)  # Condition | ConditionGroup
    uid: str = field(default_factory=_uid)

    def is_empty(self) -> bool:
        return not self.children

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"logic": self.logic}
        if not self.active_flag:
            out["active_flag"] = False
        out["conditions"] = [c.to_dict() for c in self.children]
        return out

    @classmethod
    def from_dict(cls, data: Any) -> "ConditionGroup":
        if data is None:
            return cls()
        if isinstance(data, list):  # a bare list of conditions means "all"
            data = {"logic": "all", "conditions": data}
        children: list[Any] = []
        for raw in data.get("conditions") or []:
            if isinstance(raw, dict) and ("conditions" in raw or "logic" in raw):
                children.append(cls.from_dict(raw))
            else:
                children.append(Condition.from_dict(raw))
        return cls(
            logic=str(data.get("logic") or "all"),
            active_flag=bool(data.get("active_flag", True)),
            children=children,
        )

    def copy(self) -> "ConditionGroup":
        return ConditionGroup(
            logic=self.logic,
            active_flag=self.active_flag,
            children=[c.copy() for c in self.children],
        )

    def walk_conditions(self) -> Iterable[Condition]:
        for child in self.children:
            if isinstance(child, ConditionGroup):
                yield from child.walk_conditions()
            else:
                yield child


# --------------------------------------------------------------------------
# assignments / rules / ruleset
# --------------------------------------------------------------------------


@dataclass
class Assignment:
    """No ``active_flag`` -- per the 0.4.0 audit, only Rule and Condition have one."""

    target_field: str = ""
    value: Operand = field(default_factory=Operand)
    uid: str = field(default_factory=_uid)

    def to_dict(self) -> dict[str, Any]:
        return {"target_field": self.target_field, "value": self.value.to_dict()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Assignment":
        return cls(
            target_field=str(data.get("target_field") or ""),
            value=Operand.from_dict(data.get("value")),
        )

    def copy(self) -> "Assignment":
        return Assignment(target_field=self.target_field, value=self.value.copy())


@dataclass
class Rule:
    rule_id: str = ""
    description: str = ""
    rule_order: int = 0
    active_flag: bool = True
    stop_on_match: bool = False
    conditions: ConditionGroup = field(default_factory=ConditionGroup)
    assignments: list[Assignment] = field(default_factory=list)
    uid: str = field(default_factory=_uid)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "description": self.description,
            "rule_order": self.rule_order,
            "active_flag": self.active_flag,
            "stop_on_match": self.stop_on_match,
            "conditions": self.conditions.to_dict(),
            "assignments": [a.to_dict() for a in self.assignments],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Rule":
        return cls(
            rule_id=str(data.get("rule_id") or ""),
            description=str(data.get("description") or ""),
            rule_order=int(data.get("rule_order") or 0),
            active_flag=bool(data.get("active_flag", True)),
            stop_on_match=bool(data.get("stop_on_match", False)),
            conditions=ConditionGroup.from_dict(data.get("conditions")),
            assignments=[Assignment.from_dict(a) for a in data.get("assignments") or []],
        )

    def copy(self) -> "Rule":
        return Rule(
            rule_id=self.rule_id,
            description=self.description,
            rule_order=self.rule_order,
            active_flag=self.active_flag,
            stop_on_match=self.stop_on_match,
            conditions=self.conditions.copy(),
            assignments=[a.copy() for a in self.assignments],
        )


@dataclass
class Ruleset:
    ruleset_id: str = "untitled_ruleset"
    version: str = "0.1.0"
    description: str = ""
    published_by: str = ""
    published_at: str = ""
    rules: list[Rule] = field(default_factory=list)

    def ordered_rules(self) -> list[Rule]:
        return sorted(self.rules, key=lambda r: (r.rule_order, r.rule_id))

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ruleset_id": self.ruleset_id,
            "version": self.version,
        }
        if self.description:
            out["description"] = self.description
        # Lifecycle metadata is excluded from content_hash by the engine
        # (serializer.py:51-54) but still round-trips through the file.
        if self.published_by:
            out["published_by"] = self.published_by
        if self.published_at:
            out["published_at"] = self.published_at
        out["rules"] = [r.to_dict() for r in self.ordered_rules()]
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Ruleset":
        if not isinstance(data, dict):
            raise ValueError("Ruleset file must contain a mapping at the top level.")
        return cls(
            ruleset_id=str(data.get("ruleset_id") or "untitled_ruleset"),
            version=str(data.get("version") or "0.1.0"),
            description=str(data.get("description") or ""),
            published_by=str(data.get("published_by") or ""),
            published_at=str(data.get("published_at") or ""),
            rules=[Rule.from_dict(r) for r in data.get("rules") or []],
        )


# --------------------------------------------------------------------------
# helpers used by the UI
# --------------------------------------------------------------------------


def new_condition(default_field: str = "") -> Condition:
    return Condition(
        left=Operand(kind="field", field_name=default_field),
        operator="equals",
        right=Operand(kind="literal", value="", value_type="string"),
    )


def new_rule(order: int, default_field: str = "") -> Rule:
    return Rule(
        rule_id=f"rule_{order:03d}",
        rule_order=order,
        conditions=ConditionGroup(children=[new_condition(default_field)]),
        assignments=[],
    )


def referenced_columns(ruleset: Ruleset) -> set[str]:
    """Every source column the ruleset reads, across conditions and assignments."""
    found: set[str] = set()

    def visit(op: Operand) -> None:
        if op.kind == "field" and op.field_name:
            found.add(op.field_name)
        for arg in op.args:
            visit(arg)

    for rule in ruleset.rules:
        for cond in rule.conditions.walk_conditions():
            visit(cond.left)
            if cond.right is not None:
                visit(cond.right)
        for assignment in rule.assignments:
            visit(assignment.value)
    return found


def assigned_fields(ruleset: Ruleset) -> list[str]:
    seen: list[str] = []
    for rule in ruleset.ordered_rules():
        for assignment in rule.assignments:
            if assignment.target_field and assignment.target_field not in seen:
                seen.append(assignment.target_field)
    return seen
