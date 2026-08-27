"""
Mutable authoring models for Rules Engine Studio.

The production ``rules_engine`` models are frozen compiled metadata. The
studio mirrors that contract with mutable dataclasses so Streamlit widgets can
edit an incomplete draft in place. Conversion to production models always
passes through ``YamlRulesetCompiler``.

Design notes
------------
Only transient widget identifiers are studio-specific. Every persisted field,
operator, operand kind, and YAML key comes from the authoritative engine
contract.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from . import authoring


@dataclass(frozen=True)
class OperatorSpec:
    """
    Display metadata for one canonical comparison operator.

    Parameters
    ----------
    name : str
        Canonical ``ComparisonOperator`` value.
    label : str
        Compact label shown in the condition editor.
    arity : int
        Engine-defined number of operands required by the operator.
    hint : str
        Studio-owned authoring guidance.
    right_operand_shape : str
        Engine-defined right operand shape.
    supports_tolerance : bool
        Whether the engine applies absolute tolerance for the operator.
    """

    name: str
    label: str
    arity: int
    hint: str = ""
    right_operand_shape: str = "any"
    supports_tolerance: bool = False


_OPERATOR_PRESENTATION: dict[str, tuple[str, str]] = {
    "eq": ("equals", ""),
    "ne": ("does not equal", ""),
    "gt": ("is greater than", ""),
    "ge": ("is at least", ""),
    "lt": ("is less than", ""),
    "le": ("is at most", ""),
    "in": ("is one of", "Use a collection literal on the right."),
    "not_in": ("is not one of", "Use a collection literal on the right."),
    "between": ("is between", "Use exactly two literal values."),
    "not_between": ("is not between", "Use exactly two literal values."),
    "like": ("matches SQL pattern", ""),
    "not_like": ("does not match SQL pattern", ""),
    "contains": ("contains", ""),
    "not_contains": ("does not contain", ""),
    "starts_with": ("starts with", ""),
    "ends_with": ("ends with", ""),
    "is_null": ("is null", ""),
    "is_not_null": ("is not null", ""),
}


def _operator_spec(contract: Mapping[str, Any]) -> OperatorSpec:
    """Combine engine behavior with Studio-owned display text."""
    name = str(contract["name"])
    label, hint = _OPERATOR_PRESENTATION.get(name, (name.replace("_", " "), ""))
    return OperatorSpec(
        name=name,
        label=label,
        arity=int(contract["arity"]),
        hint=hint,
        right_operand_shape=str(contract["right_operand_shape"]),
        supports_tolerance=bool(contract["supports_tolerance"]),
    )


OPERATORS: tuple[OperatorSpec, ...] = tuple(
    _operator_spec(contract) for contract in authoring.comparison_operators()
)

OPERATORS_BY_NAME: dict[str, OperatorSpec] = {operator.name: operator for operator in OPERATORS}
OPERATOR_NAMES: list[str] = [operator.name for operator in OPERATORS]
UNARY_OPERATORS = frozenset(operator.name for operator in OPERATORS if operator.arity == 1)
TOLERANCE_OPERATORS = frozenset(
    operator.name for operator in OPERATORS if operator.supports_tolerance
)
SCALAR_LITERAL_TYPES = tuple(
    str(contract["name"]) for contract in authoring.literal_type_hints()
)
# Collections and null are Studio editor shapes, not engine ``value_type`` hints.
STUDIO_LITERAL_SHAPES = ("array", "struct", "null")
LITERAL_TYPES = (*SCALAR_LITERAL_TYPES, *STUDIO_LITERAL_SHAPES)
LOGIC_MODES = authoring.logical_operators()
OPERAND_KINDS = authoring.operand_kinds()


def _uid() -> str:
    """Return a short identifier used only for stable Streamlit widget keys."""
    return uuid.uuid4().hex[:10]


def _copy_argument(value: Any) -> Any:
    """Copy a function argument while preserving nested operand objects."""
    if isinstance(value, Operand):
        return value.copy()
    if isinstance(value, Mapping):
        return {str(key): _copy_argument(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy_argument(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_copy_argument(item) for item in value)
    if isinstance(value, set):
        return {_copy_argument(item) for item in value}
    return deepcopy(value)


def _argument_to_payload(value: Any) -> Any:
    """Convert one custom-function argument into canonical authoring data."""
    if isinstance(value, Operand):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {str(key): _argument_to_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_argument_to_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_argument_to_payload(item) for item in value)
    if isinstance(value, set):
        return {_argument_to_payload(item) for item in value}
    return value


def _argument_from_payload(value: Any) -> Any:
    """Restore nested operand-shaped custom-function argument data."""
    if isinstance(value, Mapping):
        operand_keys = set(OPERAND_KINDS) & set(value)
        if operand_keys:
            return Operand.from_dict(value)
        return {str(key): _argument_from_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_argument_from_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_argument_from_payload(item) for item in value)
    if isinstance(value, set):
        return {_argument_from_payload(item) for item in value}
    return value


@dataclass
class Operand:
    """
    Mutable authoring representation of a canonical rules-engine operand.

    Parameters
    ----------
    kind : str
        One of ``field``, ``assigned``, ``literal``, or ``custom_function``.
    field_name : str
        Incoming field read by a field operand.
    assigned_field : str
        Target committed by an earlier matched rule.
    value : Any
        Literal value.
    value_type : str | None
        Optional literal type hint preserved by the compiler.
    function : str
        Registered custom-function name.
    args : dict[str, Any]
        Named custom-function arguments.
    default_if_null : Operand | None
        Non-null literal fallback applied by the runtime.
    """

    kind: str = "literal"
    field_name: str = ""
    assigned_field: str = ""
    value: Any = None
    value_type: str | None = "string"
    function: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    default_if_null: Operand | None = None
    uid: str = field(default_factory=_uid)

    def describe(self) -> str:
        """Return a compact author-facing operand description."""
        if self.kind == "field":
            return self.field_name or "(no field)"
        if self.kind == "assigned":
            return f"assigned:{self.assigned_field or '(no field)'}"
        if self.kind == "custom_function":
            arguments = ", ".join(
                f"{name}={value.describe() if isinstance(value, Operand) else value!r}"
                for name, value in self.args.items()
            )
            return f"{self.function or '(no function)'}({arguments})"
        if self.value is None:
            return "null"
        if isinstance(self.value, str):
            return f'"{self.value}"'
        return str(self.value)

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical YAML authoring representation."""
        if self.kind == "field":
            payload: dict[str, Any] = {"field": self.field_name}
        elif self.kind == "assigned":
            payload = {"assigned": self.assigned_field}
        elif self.kind == "custom_function":
            payload = {
                "custom_function": {
                    "name": self.function,
                    "args": {
                        str(name): _argument_to_payload(value) for name, value in self.args.items()
                    },
                }
            }
        else:
            payload = {"literal": self.value}
            value_type = authoring.canonical_literal_type_hint(self.value_type or "")
            if value_type and value_type not in {*STUDIO_LITERAL_SHAPES, "list"}:
                payload["value_type"] = value_type
        if self.default_if_null is not None:
            fallback = self.default_if_null.to_dict()
            if set(fallback) == {"literal"} and not isinstance(
                fallback["literal"], Mapping
            ):
                payload["default_if_null"] = fallback["literal"]
            else:
                payload["default_if_null"] = fallback
        return payload

    @classmethod
    def from_dict(cls, data: Any) -> Operand:
        """
        Restore an operand from canonical YAML authoring data.

        Parameters
        ----------
        data : Any
            Canonical operand mapping or a shorthand literal.

        Returns
        -------
        Operand
            Mutable studio operand.
        """
        if not isinstance(data, Mapping):
            return cls(kind="literal", value=data, value_type=infer_literal_type(data))
        default = data.get("default_if_null")
        default_operand = None
        if default is not None:
            default_operand = (
                cls.from_dict(default)
                if isinstance(default, Mapping) and "literal" in default
                else cls(kind="literal", value=default, value_type=infer_literal_type(default))
            )
        if "field" in data:
            return cls(
                kind="field",
                field_name=str(data.get("field") or ""),
                default_if_null=default_operand,
            )
        if "assigned" in data:
            return cls(
                kind="assigned",
                assigned_field=str(data.get("assigned") or ""),
                default_if_null=default_operand,
            )
        if "custom_function" in data:
            function = data.get("custom_function")
            if not isinstance(function, Mapping):
                function = {}
            arguments = function.get("args")
            if not isinstance(arguments, Mapping):
                arguments = {}
            return cls(
                kind="custom_function",
                function=str(function.get("name") or ""),
                args={
                    str(name): _argument_from_payload(value) for name, value in arguments.items()
                },
                default_if_null=default_operand,
            )
        value = data.get("literal")
        return cls(
            kind="literal",
            value=value,
            value_type=normalize_literal_editor_type(data.get("value_type"), value),
            default_if_null=default_operand,
        )

    def copy(self) -> Operand:
        """Return an independent copy with fresh widget identifiers."""
        return Operand(
            kind=self.kind,
            field_name=self.field_name,
            assigned_field=self.assigned_field,
            value=_copy_argument(self.value),
            value_type=self.value_type,
            function=self.function,
            args={str(name): _copy_argument(value) for name, value in self.args.items()},
            default_if_null=self.default_if_null.copy() if self.default_if_null else None,
        )


def infer_literal_type(value: Any) -> str:
    """Infer a studio input type from a parsed literal value."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, (float, Decimal)):
        return "decimal"
    if isinstance(value, (list, tuple, set)):
        return "array"
    if isinstance(value, Mapping):
        return "struct"
    return "string"


def normalize_literal_editor_type(type_hint: Any, value: Any) -> str:
    """Normalize manifest aliases and Studio collection shapes for editing."""
    if type_hint is None or str(type_hint) == "":
        return infer_literal_type(value)
    normalized = "array" if str(type_hint) == "list" else str(type_hint)
    return authoring.canonical_literal_type_hint(normalized)


@dataclass
class Condition:
    """Mutable authoring representation of one canonical condition."""

    left: Operand = field(default_factory=lambda: Operand(kind="field"))
    operator: str = "eq"
    right: Operand | None = field(default_factory=Operand)
    condition_id: str = field(default_factory=lambda: f"condition:{_uid()}")
    tolerance_abs: Decimal = Decimal(0)
    error_on_null: bool = False
    active_flag: bool = True
    uid: str = field(default_factory=_uid)

    def describe(self) -> str:
        """Return a compact author-facing condition description."""
        spec = OPERATORS_BY_NAME.get(self.operator)
        label = spec.label if spec else self.operator
        if spec and spec.arity == 1:
            return f"{self.left.describe()} {label}"
        right = self.right.describe() if self.right else "(none)"
        return f"{self.left.describe()} {label} {right}"

    def to_dict(self) -> dict[str, Any]:
        """Return canonical condition authoring data."""
        payload: dict[str, Any] = {
            "condition_id": self.condition_id,
            "left": self.left.to_dict(),
            "operator": self.operator,
        }
        if self.operator not in UNARY_OPERATORS and self.right is not None:
            payload["right"] = self.right.to_dict()
        payload["tolerance_abs"] = format(Decimal(str(self.tolerance_abs)), "f")
        if self.error_on_null:
            payload["error_on_null"] = True
        payload["active_flag"] = self.active_flag
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Condition:
        """Restore a condition from canonical authoring data."""
        right = data.get("right")
        return cls(
            left=Operand.from_dict(data.get("left")),
            operator=str(data.get("operator") or "eq"),
            right=Operand.from_dict(right) if right is not None else None,
            condition_id=str(data.get("condition_id") or f"condition:{_uid()}"),
            tolerance_abs=Decimal(str(data.get("tolerance_abs", "0"))),
            error_on_null=bool(data.get("error_on_null", False)),
            active_flag=bool(data.get("active_flag", True)),
        )

    def copy(self) -> Condition:
        """Return an independent copy with fresh widget identifiers."""
        return Condition(
            left=self.left.copy(),
            operator=self.operator,
            right=self.right.copy() if self.right else None,
            condition_id=f"condition:{_uid()}",
            tolerance_abs=self.tolerance_abs,
            error_on_null=self.error_on_null,
            active_flag=self.active_flag,
        )


@dataclass
class ConditionGroup:
    """Mutable tree node for a canonical logical condition group."""

    logical_operator: str = "all"
    condition_group_id: str = field(default_factory=lambda: f"group:{_uid()}")
    children: list[Condition | ConditionGroup] = field(default_factory=list)
    uid: str = field(default_factory=_uid)

    def is_empty(self) -> bool:
        """Return whether the group has no conditions or nested groups."""
        return not self.children

    def to_dict(self) -> dict[str, Any]:
        """Return canonical tree-shaped condition-group authoring data."""
        return {
            "condition_group_id": self.condition_group_id,
            self.logical_operator: [child.to_dict() for child in self.children],
        }

    @classmethod
    def from_dict(cls, data: Any) -> ConditionGroup:
        """Restore a condition group from canonical authoring data."""
        if not isinstance(data, Mapping):
            return cls()
        logical_operator = "any" if "any" in data else "all"
        items = data.get(logical_operator)
        if not isinstance(items, list):
            items = []
        children: list[Condition | ConditionGroup] = []
        for item in items:
            if isinstance(item, Mapping) and ({"all", "any"} & set(item)):
                children.append(cls.from_dict(item))
            elif isinstance(item, Mapping):
                children.append(Condition.from_dict(item))
        return cls(
            logical_operator=logical_operator,
            condition_group_id=str(data.get("condition_group_id") or f"group:{_uid()}"),
            children=children,
        )

    def copy(self) -> ConditionGroup:
        """Return an independent recursive copy with fresh metadata IDs."""
        return ConditionGroup(
            logical_operator=self.logical_operator,
            condition_group_id=f"group:{_uid()}",
            children=[child.copy() for child in self.children],
        )

    def walk_conditions(self) -> Iterable[Condition]:
        """Yield every condition below this group in authoring order."""
        for child in self.children:
            if isinstance(child, ConditionGroup):
                yield from child.walk_conditions()
            else:
                yield child


@dataclass
class Assignment:
    """Mutable authoring representation of one canonical assignment."""

    target_field: str = ""
    value: Operand = field(default_factory=Operand)
    assignment_id: str = field(default_factory=lambda: f"assignment:{_uid()}")
    uid: str = field(default_factory=_uid)

    def to_dict(self) -> dict[str, Any]:
        """Return canonical assignment authoring data."""
        return {
            "assignment_id": self.assignment_id,
            "target_field": self.target_field,
            "value": self.value.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Assignment:
        """Restore an assignment from canonical authoring data."""
        return cls(
            target_field=str(data.get("target_field") or ""),
            value=Operand.from_dict(data.get("value")),
            assignment_id=str(data.get("assignment_id") or f"assignment:{_uid()}"),
        )

    def copy(self) -> Assignment:
        """Return an independent copy with a fresh assignment identifier."""
        return Assignment(
            target_field=self.target_field,
            value=self.value.copy(),
            assignment_id=f"assignment:{_uid()}",
        )


@dataclass
class Rule:
    """Mutable authoring representation of one canonical rule."""

    rule_id: str = ""
    rule_name: str = ""
    description: str = ""
    rule_order: int = 0
    active_flag: bool = True
    stop_on_match: bool = False
    conditions: ConditionGroup = field(default_factory=ConditionGroup)
    assignments: list[Assignment] = field(default_factory=list)
    uid: str = field(default_factory=_uid)

    def to_dict(self) -> dict[str, Any]:
        """Return canonical rule authoring data."""
        payload: dict[str, Any] = {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "rule_order": self.rule_order,
            "active_flag": self.active_flag,
            "stop_on_match": self.stop_on_match,
        }
        if self.description:
            payload["description"] = self.description
        payload["when"] = self.conditions.to_dict()
        payload["assign"] = [assignment.to_dict() for assignment in self.assignments]
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Rule:
        """Restore a rule from canonical authoring data."""
        return cls(
            rule_id=str(data.get("rule_id") or ""),
            rule_name=str(data.get("rule_name") or ""),
            description=str(data.get("description") or ""),
            rule_order=int(data.get("rule_order") or 0),
            active_flag=bool(data.get("active_flag", True)),
            stop_on_match=bool(data.get("stop_on_match", False)),
            conditions=ConditionGroup.from_dict(data.get("when")),
            assignments=[
                Assignment.from_dict(assignment)
                for assignment in data.get("assign", [])
                if isinstance(assignment, Mapping)
            ],
        )

    def copy(self) -> Rule:
        """Return an independent copy with fresh child metadata identifiers."""
        return Rule(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            description=self.description,
            rule_order=self.rule_order,
            active_flag=self.active_flag,
            stop_on_match=self.stop_on_match,
            conditions=self.conditions.copy(),
            assignments=[assignment.copy() for assignment in self.assignments],
        )


@dataclass
class Ruleset:
    """Mutable authoring representation of one canonical ruleset."""

    ruleset_id: str = "untitled_ruleset"
    ruleset_name: str = "Untitled ruleset"
    version: str = "0.1.0"
    description: str = ""
    owner: str = ""
    owner_department: str = ""
    rules: list[Rule] = field(default_factory=list)

    def ordered_rules(self) -> list[Rule]:
        """Return rules in deterministic production evaluation order."""
        return sorted(self.rules, key=lambda rule: (rule.rule_order, rule.rule_id))

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical ruleset authoring payload."""
        payload: dict[str, Any] = {
            "ruleset_id": self.ruleset_id,
            "ruleset_name": self.ruleset_name,
            "version": self.version,
        }
        if self.description:
            payload["description"] = self.description
        if self.owner:
            payload["owner"] = self.owner
        if self.owner_department:
            payload["owner_department"] = self.owner_department
        payload["rules"] = [rule.to_dict() for rule in self.ordered_rules()]
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Ruleset:
        """
        Restore a studio ruleset from canonical authoring data.

        Parameters
        ----------
        data : Mapping[str, Any]
            Payload produced by ``YamlRulesetExporter``.

        Returns
        -------
        Ruleset
            Mutable studio ruleset.
        """
        if not isinstance(data, Mapping):
            raise ValueError("Ruleset file must contain a mapping at the top level.")
        return cls(
            ruleset_id=str(data.get("ruleset_id") or "untitled_ruleset"),
            ruleset_name=str(data.get("ruleset_name") or "Untitled ruleset"),
            version=str(data.get("version") or "0.1.0"),
            description=str(data.get("description") or ""),
            owner=str(data.get("owner") or ""),
            owner_department=str(data.get("owner_department") or ""),
            rules=[
                Rule.from_dict(rule) for rule in data.get("rules", []) if isinstance(rule, Mapping)
            ],
        )


def new_condition(default_field: str = "") -> Condition:
    """Return a new equality condition bound to an optional sample field."""
    return Condition(
        left=Operand(kind="field", field_name=default_field),
        operator="eq",
        right=Operand(kind="literal", value="", value_type="string"),
    )


def new_rule(order: int, default_field: str = "") -> Rule:
    """Return a new rule with one editable condition and no assignments."""
    rule_id = f"rule_{order:03d}"
    return Rule(
        rule_id=rule_id,
        rule_name=rule_id.replace("_", " ").title(),
        rule_order=order,
        conditions=ConditionGroup(children=[new_condition(default_field)]),
    )


def referenced_columns(ruleset: Ruleset) -> set[str]:
    """Return every incoming field referenced by conditions and assignments."""
    found: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, Operand):
            if value.kind == "field" and value.field_name:
                found.add(value.field_name)
            for argument in value.args.values():
                visit(argument)
            return
        if isinstance(value, Mapping):
            for item in value.values():
                visit(item)
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                visit(item)

    for rule in ruleset.rules:
        for condition in rule.conditions.walk_conditions():
            visit(condition.left)
            if condition.right is not None:
                visit(condition.right)
        for assignment in rule.assignments:
            visit(assignment.value)
    return found
