"""Production compilation, Spark schema validation, and sample-row evaluation.

The Studio uses the engine's worker adapter for compact and full audit results.
Focused inspections reproduce earlier committed assignments using the same
schema and normalization before invoking the engine's trace helpers.
"""

from __future__ import annotations

import struct
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from typing import Any

from pyspark.sql import types as T

from rules_engine import __version__
from rules_engine.models import Assignment as CompiledAssignment
from rules_engine.models import Condition as CompiledCondition
from rules_engine.models import ConditionGroup as CompiledConditionGroup
from rules_engine.models import Rule as CompiledRule
from rules_engine.models import Ruleset as CompiledRuleset
from rules_engine.runtime import AssignedValue
from rules_engine.serializer import DeltaRowSerializer
from rules_engine.spark_runtime import (
    COMPACT_RESULT_FIELD_NAMES,
    FULL_AUDIT_ONLY_RESULT_FIELD_NAMES,
    SparkRulesEngineRuntime,
    _SparkRowUdfEvaluator,
)
from rules_engine.spark_types import decimal_literal_type, decimal_value_fits
from rules_engine.spark_validator import SparkRulesetCompatibilityValidator

from . import authoring
from .schema import Assignment, Condition, ConditionGroup, Operand, Rule, Ruleset

FULL_AUDIT_ONLY_FIELDS = FULL_AUDIT_ONLY_RESULT_FIELD_NAMES
AUDIT_IDENTITY_FIELDS = ("ruleset", "engine_version")
COMPACT_FIELDS = COMPACT_RESULT_FIELD_NAMES + AUDIT_IDENTITY_FIELDS
FULL_AUDIT_FIELDS = COMPACT_RESULT_FIELD_NAMES + FULL_AUDIT_ONLY_FIELDS + AUDIT_IDENTITY_FIELDS


class OperandError(Exception):
    """Raised when the production compiler or evaluator rejects an inspection."""


class FocusedEvaluationSkipped(OperandError):
    """Raised when the selected object does not execute on the selected row."""


@dataclass
class Resolution:
    """Resolved operand value plus the engine's trace metadata."""

    value: Any
    source: str
    detail: str
    trace: dict[str, Any] | None = None


@dataclass(frozen=True)
class _SparkRow:
    """Expose sample mappings through the production Spark-row contract."""

    values: Mapping[str, Any]
    source_schema: T.StructType | None = None

    def asDict(self, recursive: bool = True) -> dict[str, Any]:  # noqa: N802
        """Return sample values through the pyspark Row method contract."""
        del recursive
        if self.source_schema is not None:
            return _sample_input_value(self.values, self.source_schema)
        return dict(self.values)


@dataclass
class _FocusedContext:
    """One validated rule, source row, and previously committed assignments."""

    rule: CompiledRule
    row: Mapping[str, Any]
    runtime: _SparkRowUdfEvaluator
    assigned: dict[str, AssignedValue]
    assignment_types: dict[str, T.DataType]


def compile_ruleset(ruleset: Ruleset) -> CompiledRuleset:
    """Compile a mutable draft through the canonical YAML compiler."""
    return authoring.compile_payload(ruleset.to_dict())


def sample_schema(rows: list[Mapping[str, Any]]) -> T.StructType:
    """Infer one Spark schema for a complete batch without string fallbacks.

    Sample mappings represent structs and naive datetimes represent TimestampNTZ.
    Mixed or unsupported columns are rejected instead of silently coerced.
    Null-only columns retain NullType so the engine can use authored type hints.
    """
    schema = T.StructType()
    for row in rows:
        schema = _merge_sample_types(schema, _sample_type(row), "sample data")
    return schema


def _sample_type(value: Any) -> T.DataType:
    """Infer a sample type while preserving exact decimals and nested structures."""
    if isinstance(value, Decimal):
        inferred = decimal_literal_type(value)
        if inferred is None:
            raise ValueError(f"Sample decimal {value!r} cannot be represented by Spark.")
        return inferred
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("Sample struct and column names must be strings.")
        return T.StructType(
            [T.StructField(key, _sample_type(item), True) for key, item in value.items()]
        )
    if isinstance(value, (list, tuple)):
        element_type: T.DataType = T.NullType()
        for item in value:
            element_type = _merge_sample_types(element_type, _sample_type(item), "array element")
        return T.ArrayType(element_type, True)
    return T._infer_type(value, prefer_timestamp_ntz=True)


def _merge_sample_types(left: T.DataType, right: T.DataType, label: str) -> T.DataType:
    """Merge compatible samples with the production numeric widening rules."""
    if isinstance(left, T.NullType):
        return right
    if isinstance(right, T.NullType) or left == right:
        return left
    if isinstance(left, T.StructType) and isinstance(right, T.StructType):
        fields = {field.name: field.dataType for field in left.fields}
        for field in right.fields:
            fields[field.name] = _merge_sample_types(
                fields.get(field.name, T.NullType()), field.dataType, f"{label}.{field.name}"
            )
        return T.StructType([T.StructField(name, kind, True) for name, kind in fields.items()])
    if isinstance(left, T.ArrayType) and isinstance(right, T.ArrayType):
        return T.ArrayType(
            _merge_sample_types(left.elementType, right.elementType, f"{label}[]"), True
        )
    merged = SparkRulesetCompatibilityValidator(authoring.registry())._common_type(left, right)
    if merged is None:
        raise TypeError(
            f"{label} has incompatible sample types {left.simpleString()} and "
            f"{right.simpleString()}; provide consistently typed test data."
        )
    return merged


def _sample_input_value(value: Any, data_type: T.DataType) -> Any:
    """Materialize samples as typed Spark inputs without losing numeric precision."""
    if value is None:
        return None
    if isinstance(data_type, T.StructType):
        value = {
            field.name: _sample_input_value(value.get(field.name), field.dataType)
            for field in data_type.fields
        }
    elif isinstance(data_type, T.ArrayType):
        value = [_sample_input_value(item, data_type.elementType) for item in value]
    elif isinstance(data_type, T.MapType):
        value = {
            _sample_input_value(key, data_type.keyType): _sample_input_value(
                item, data_type.valueType
            )
            for key, item in value.items()
        }
    elif isinstance(data_type, (T.FloatType, T.DoubleType)) and isinstance(value, (int, float)):
        converted = float(value)
        if isinstance(data_type, T.FloatType):
            converted = struct.unpack("!f", struct.pack("!f", converted))[0]
        if isinstance(value, int) and (isinstance(value, bool) or converted != value):
            raise ValueError(
                f"Sample integer {value!r} cannot widen to a float without precision loss."
            )
        value = converted
    elif isinstance(data_type, T.DecimalType):
        if isinstance(value, int) and not isinstance(value, bool):
            value = Decimal(value)
        if isinstance(value, Decimal) and not decimal_value_fits(value, data_type):
            raise ValueError(f"Sample decimal {value!r} does not fit {data_type.simpleString()}.")
    T._make_type_verifier(data_type)(value)
    return value


def _prepare_schema(ruleset: CompiledRuleset, source_schema: T.StructType) -> dict[str, T.DataType]:
    """Validate metadata and samples using the engine's Spark validator."""
    prepared = SparkRulesetCompatibilityValidator(authoring.registry()).prepare(
        ruleset, source_schema
    )
    if prepared.validation.has_errors():
        raise ValueError(prepared.validation.to_text())
    return {field.name: field.dataType for field in prepared.assignment_schema.fields}


def _worker(
    ruleset: CompiledRuleset,
    source_schema: T.StructType,
    assignment_types: dict[str, T.DataType],
    *,
    full_audit: bool = False,
):
    """Build the canonical Spark worker without starting a local Spark session."""
    worker = SparkRulesEngineRuntime(object(), authoring.registry())._build_row_evaluator(
        ruleset,
        list(assignment_types),
        assignment_types,
        full_audit=full_audit,
        source_schema=source_schema,
    )

    def evaluate(row: _SparkRow) -> dict[str, Any]:
        return worker(_SparkRow(row.values, source_schema))

    return evaluate


def _evaluation_context(
    ruleset: CompiledRuleset,
    rows: list[dict[str, Any]],
    *,
    full_audit: bool,
    source_schema: T.StructType | None,
):
    """Build one validated worker and identity for an entire sample batch."""
    schema = source_schema if source_schema is not None else sample_schema(rows)
    assignment_types = _prepare_schema(ruleset, schema)
    worker = _worker(ruleset, schema, assignment_types, full_audit=full_audit)
    identity = {
        "id": ruleset.ruleset_id,
        "version": ruleset.version,
        "content_hash": DeltaRowSerializer().content_hash(ruleset),
    }
    return worker, identity


def _focused_rule_context(
    ruleset: Ruleset,
    target_rule: Rule,
    row: Mapping[str, Any],
    source_schema: T.StructType | None,
) -> _FocusedContext:
    """Reproduce only values committed before the selected rule is reached."""
    compiled = compile_ruleset(ruleset)
    schema = source_schema if source_schema is not None else sample_schema([row])
    assignment_types = _prepare_schema(compiled, schema)
    ordered = tuple(sorted(compiled.rules, key=lambda item: item.rule_order))
    target_index = next(
        (index for index, rule in enumerate(ordered) if rule.rule_id == target_rule.rule_id), None
    )
    if target_index is None:
        raise KeyError(f"Rule {target_rule.rule_id!r} is absent from the current ruleset.")
    compiled_rule = ordered[target_index]
    if not compiled_rule.active_flag:
        raise FocusedEvaluationSkipped(f"Rule {target_rule.rule_id!r} is inactive and is skipped.")
    prior_rules = ordered[:target_index]
    assigned: dict[str, AssignedValue] = {}
    if prior_rules:
        result = _worker(replace(compiled, rules=prior_rules), schema, assignment_types)(
            _SparkRow(row)
        )
        if result["error"]:
            raise OperandError(result["error"])
        for rule in prior_rules:
            if rule.rule_id not in result["matched_rule_ids"]:
                continue
            if rule.stop_on_match:
                raise FocusedEvaluationSkipped(
                    f"Rule {target_rule.rule_id!r} is not reached because earlier "
                    f"stop-on-match rule {rule.rule_id!r} matched this row."
                )
            for assignment in rule.assignments:
                assigned[assignment.target_field] = AssignedValue(
                    value=result["assign"][assignment.target_field]["value"],
                    rule_id=rule.rule_id,
                    assignment_id=assignment.assignment_id,
                )
    runtime = _SparkRowUdfEvaluator(authoring.registry())
    source_types = {field.name: field.dataType for field in schema.fields}
    normalized = {
        name: runtime._spark_input_value(value, source_types.get(name))
        for name, value in _sample_input_value(row, schema).items()
    }
    return _FocusedContext(compiled_rule, normalized, runtime, assigned, assignment_types)


def _compiled_condition(
    group: CompiledConditionGroup, condition_id: str
) -> tuple[CompiledCondition, CompiledConditionGroup]:
    """Return a compiled condition and its owning group by identifier."""
    for condition in group.conditions:
        if condition.condition_id == condition_id:
            return condition, group
    for nested in group.groups:
        try:
            return _compiled_condition(nested, condition_id)
        except KeyError:
            continue
    raise KeyError(f"Condition {condition_id!r} is absent from the selected rule.")


def _temporary_ruleset(rule: Rule) -> Ruleset:
    """Wrap a focused probe in the minimum valid owned ruleset metadata."""
    return Ruleset(
        ruleset_id="studio_probe",
        ruleset_name="Studio probe",
        version="1",
        owner="Rules Engine Studio",
        owner_department="Authoring",
        rules=[rule],
    )


def _probe_rule(*, condition: Condition | None = None, operand: Operand | None = None) -> Rule:
    """Build a valid focused operand or condition probe."""
    return Rule(
        rule_id="studio_probe",
        rule_name="Studio probe",
        rule_order=1,
        conditions=ConditionGroup(
            condition_group_id="group:studio_probe",
            children=[
                condition
                or Condition(
                    condition_id="condition:studio_probe",
                    left=Operand(value=True, value_type="boolean"),
                    operator="eq",
                    right=Operand(value=True, value_type="boolean"),
                )
            ],
        ),
        assignments=[
            Assignment(
                assignment_id="assignment:studio_probe:value",
                target_field="studio_probe_value",
                value=operand or Operand(value=True, value_type="boolean"),
            )
        ],
    )


def _resolve_assignment(assignment: CompiledAssignment, context: _FocusedContext) -> Resolution:
    """Resolve once and normalize the proposed value to its canonical Spark type."""
    resolved = context.runtime._resolve_operand_resolution(
        assignment.value, context.row, context.assigned
    )
    value = context.runtime._spark_assignment_value(
        resolved.value, context.assignment_types[assignment.target_field]
    )
    trace = dict(resolved.trace)
    source = str(trace.get("kind") or "operand")
    detail = str(
        trace.get("field_name")
        or trace.get("target_field")
        or trace.get("function_name")
        or trace.get("value_type")
        or source
    )
    return Resolution(value, source, detail, trace=trace)


def resolve_operand(
    operand: Operand, row: dict[str, Any], *, source_schema: T.StructType | None = None
) -> Resolution:
    """Resolve an operand in an always-matching, schema-validated production probe."""
    probe = _probe_rule(operand=operand)
    return evaluate_assignment(
        probe.assignments[0],
        row,
        ruleset=_temporary_ruleset(probe),
        owning_rule=probe,
        source_schema=source_schema,
    )


def evaluate_condition(
    condition: Condition,
    row: dict[str, Any],
    *,
    ruleset: Ruleset | None = None,
    owning_rule: Rule | None = None,
    source_schema: T.StructType | None = None,
) -> dict[str, Any]:
    """Inspect one condition with production comparison and prior-rule semantics."""
    try:
        if ruleset is None and owning_rule is None:
            owning_rule = _probe_rule(condition=condition)
            ruleset = _temporary_ruleset(owning_rule)
        if ruleset is None or owning_rule is None:
            raise TypeError("ruleset and owning_rule must be supplied together.")
        context = _focused_rule_context(ruleset, owning_rule, row, source_schema)
        compiled_condition, group = _compiled_condition(
            context.rule.root_group, condition.condition_id
        )
        trace = context.runtime._evaluate_condition(
            compiled_condition, group, context.row, context.assigned
        )
    except OperandError:
        raise
    except Exception as exc:  # noqa: BLE001 - custom-function errors belong in the UI.
        raise OperandError(f"{type(exc).__name__}: {exc}") from exc
    payload = asdict(trace)
    payload.update(
        expression=condition.describe(),
        matched=payload["passed"],
        left_value=(payload.get("left") or {}).get("value"),
        right_value=(payload.get("right") or {}).get("value"),
    )
    return payload


def evaluate_rule(
    rule: Rule,
    row: dict[str, Any],
    *,
    ruleset: Ruleset | None = None,
    source_schema: T.StructType | None = None,
) -> dict[str, Any]:
    """Inspect a reached active rule and its atomic, typed proposed assignments."""
    try:
        context = _focused_rule_context(
            ruleset or _temporary_ruleset(rule), rule, row, source_schema
        )
        matched, traces = context.runtime._evaluate_rule(
            context.rule, context.row, context.assigned
        )
        assignments = (
            {
                assignment.target_field: _resolve_assignment(assignment, context).value
                for assignment in context.rule.assignments
            }
            if matched
            else {}
        )
    except OperandError:
        raise
    except Exception as exc:  # noqa: BLE001 - custom-function errors belong in the UI.
        raise OperandError(f"{type(exc).__name__}: {exc}") from exc
    return {
        "rule_id": context.rule.rule_id,
        "rule_order": context.rule.rule_order,
        "matched": matched,
        "stop_on_match": context.rule.stop_on_match,
        "assign": assignments,
        "condition_trace": [asdict(trace) for trace in traces],
    }


def evaluate_assignment(
    assignment: Assignment,
    row: dict[str, Any],
    *,
    ruleset: Ruleset | None = None,
    owning_rule: Rule | None = None,
    source_schema: T.StructType | None = None,
) -> Resolution:
    """Inspect an assignment only when its owning rule can commit successfully."""
    if ruleset is None and owning_rule is None:
        return resolve_operand(assignment.value, row, source_schema=source_schema)
    if ruleset is None or owning_rule is None:
        raise OperandError("ruleset and owning_rule must be supplied together.")
    try:
        context = _focused_rule_context(ruleset, owning_rule, row, source_schema)
        matched, _ = context.runtime._evaluate_rule(context.rule, context.row, context.assigned)
        if not matched:
            raise FocusedEvaluationSkipped(
                f"Assignment {assignment.assignment_id!r} is not applied because "
                f"rule {owning_rule.rule_id!r} does not match this row."
            )
        resolutions = {
            item.assignment_id: _resolve_assignment(item, context)
            for item in context.rule.assignments
        }
        return resolutions[assignment.assignment_id]
    except OperandError:
        raise
    except Exception as exc:  # noqa: BLE001 - custom-function errors belong in the UI.
        raise OperandError(f"{type(exc).__name__}: {exc}") from exc


def result_fields(*, full_audit: bool = False) -> tuple[str, ...]:
    """Return fields in the canonical Spark DataFrame output contract."""
    return FULL_AUDIT_FIELDS if full_audit else COMPACT_FIELDS


def empty_result(*, full_audit: bool = False) -> dict[str, Any]:
    """Return an unevaluated result when preparation fails before a worker exists."""
    result = {
        "error": None,
        "matched": False,
        "matched_rule_ids": [],
        "assign": {},
        "ruleset": None,
        "engine_version": __version__,
    }
    if full_audit:
        result.update(matched_rules=[], assignment_results=[])
    return result


def evaluate_row(
    ruleset: Ruleset,
    row: dict[str, Any],
    *,
    full_audit: bool = False,
    source_schema: T.StructType | None = None,
) -> dict[str, Any]:
    """Evaluate one sample through the schema-validated production Spark worker."""
    return evaluate_rows(ruleset, [row], full_audit=full_audit, source_schema=source_schema)[0]


def evaluate_rows(
    ruleset: Ruleset,
    rows: list[dict[str, Any]],
    *,
    full_audit: bool = False,
    source_schema: T.StructType | None = None,
) -> list[dict[str, Any]]:
    """Compile and validate once, then execute each row exactly once at either detail."""
    if not rows:
        return []
    try:
        compiled = compile_ruleset(ruleset)
        worker, identity = _evaluation_context(
            compiled, rows, full_audit=full_audit, source_schema=source_schema
        )
    except Exception as exc:  # noqa: BLE001 - render compilation and custom binding errors.
        results = [empty_result(full_audit=full_audit) for _ in rows]
        for result in results:
            result["error"] = f"{type(exc).__name__}: {exc}"
        return results
    results = [worker(_SparkRow(row)) for row in rows]
    for result in results:
        result.update(ruleset=dict(identity), engine_version=__version__)
    return results
