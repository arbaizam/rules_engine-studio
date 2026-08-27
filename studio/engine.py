"""
Production rules-engine integration for authoring-time evaluation.

Every draft is compiled by ``YamlRulesetCompiler`` and every row is evaluated
by ``SparkRowEvaluator``, the same row-level implementation used inside Spark
workers. The studio adds only error capture and presentation-friendly wrappers.
It does not implement comparison, null, assignment, or custom-function
semantics of its own.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from pyspark.sql import types as T

from rules_engine import __version__
from rules_engine.exceptions import RulesEngineError
from rules_engine.models import Assignment as CompiledAssignment
from rules_engine.models import Condition as CompiledCondition
from rules_engine.models import ConditionGroup as CompiledConditionGroup
from rules_engine.models import Operand as CompiledOperand
from rules_engine.models import Rule as CompiledRule
from rules_engine.models import Ruleset as CompiledRuleset
from rules_engine.runtime import AssignedValue, SparkRowEvaluator
from rules_engine.serializer import DeltaRowSerializer
from rules_engine.spark_runtime import SparkRulesEngineRuntime

from . import authoring
from .schema import Assignment, Condition, Operand, Rule, Ruleset

COMPACT_FIELDS = ("error", "matched", "matched_rule_ids", "assign")
FULL_AUDIT_ONLY_FIELDS = ("matched_rules", "assignment_results")
AUDIT_IDENTITY_FIELDS = ("ruleset", "engine_version")
FULL_AUDIT_FIELDS = COMPACT_FIELDS + FULL_AUDIT_ONLY_FIELDS + AUDIT_IDENTITY_FIELDS
_ENGINE_EXCEPTIONS = (ArithmeticError, KeyError, RulesEngineError, TypeError, ValueError)


class OperandError(Exception):
    """Raised when the production compiler or evaluator rejects an authoring operation."""


class FocusedEvaluationSkipped(OperandError):
    """Raised when an earlier stop-on-match rule prevents a focused evaluation."""


@dataclass
class Resolution:
    """
    Resolved operand value plus production trace metadata.

    Parameters
    ----------
    value : Any
        Runtime value produced by the operand.
    source : str
        Canonical operand kind.
    detail : str
        Compact source label.
    children : list[Resolution]
        Reserved for compatibility with existing result views.
    trace : dict[str, Any] | None
        Trace metadata emitted by ``SparkRowEvaluator``.
    """

    value: Any
    source: str
    detail: str
    children: list[Resolution] = field(default_factory=list)
    trace: dict[str, Any] | None = None


@dataclass(frozen=True)
class _SparkRow:
    """Expose a mapping through the Spark-row contract used by the engine worker."""

    values: Mapping[str, Any]

    def asDict(self, recursive: bool = True) -> dict[str, Any]:  # noqa: N802
        """Return row values through the ``pyspark.sql.Row`` method contract."""
        del recursive
        return dict(self.values)


def compile_ruleset(ruleset: Ruleset) -> CompiledRuleset:
    """
    Compile a mutable studio draft through the production YAML compiler.

    Parameters
    ----------
    ruleset : Ruleset
        Mutable authoring draft.

    Returns
    -------
    rules_engine.models.Ruleset
        Canonical compiled ruleset.
    """
    return authoring.compile_payload(ruleset.to_dict())


def _runtime() -> SparkRowEvaluator:
    """Return a production row evaluator bound to all standard functions."""
    return SparkRowEvaluator.without_repository(authoring.registry())


def _focused_rule_context(
    ruleset: Ruleset,
    target_rule: Rule,
    row: Mapping[str, Any],
    runtime: SparkRowEvaluator,
) -> tuple[CompiledRule, dict[str, AssignedValue]]:
    """Compile a rule and reproduce assignments committed before it runs."""
    compiled = compile_ruleset(ruleset)
    ordered = tuple(sorted(compiled.rules, key=lambda item: item.rule_order))
    target_index = next(
        (index for index, rule in enumerate(ordered) if rule.rule_id == target_rule.rule_id),
        None,
    )
    if target_index is None:
        raise KeyError(f"Rule {target_rule.rule_id!r} is absent from the current ruleset.")
    compiled_rule = ordered[target_index]
    prior_rules = ordered[:target_index]
    if not prior_rules:
        return compiled_rule, {}

    context_result = runtime.evaluate_row(
        replace(compiled, rules=prior_rules),
        row,
    )
    matched_by_id = {
        rule.rule_id: rule
        for rule in prior_rules
        if rule.rule_id in context_result["matched_rule_ids"]
    }
    producers: dict[str, tuple[CompiledRule, CompiledAssignment]] = {}
    for rule_id in context_result["matched_rule_ids"]:
        prior_rule = matched_by_id[rule_id]
        for assignment in prior_rule.assignments:
            producers[assignment.target_field] = (prior_rule, assignment)
        if prior_rule.stop_on_match:
            raise FocusedEvaluationSkipped(
                f"Rule {target_rule.rule_id!r} is not reached because earlier "
                f"stop-on-match rule {prior_rule.rule_id!r} matched this row."
            )

    return compiled_rule, {
        target_field: AssignedValue(
            value=context_result["assign"][target_field]["value"],
            rule_id=producer.rule_id,
            assignment_id=assignment.assignment_id,
        )
        for target_field, (producer, assignment) in producers.items()
    }


def _compiled_condition(
    group: CompiledConditionGroup,
    condition_id: str,
) -> tuple[CompiledCondition, CompiledConditionGroup]:
    """Return a compiled condition and its owning group by identifier."""
    for condition in group.conditions:
        if condition.condition_id == condition_id:
            return condition, group
    for nested_group in group.groups:
        try:
            return _compiled_condition(nested_group, condition_id)
        except KeyError:
            continue
    raise KeyError(f"Condition {condition_id!r} is absent from the selected rule.")


def _compiled_assignment(
    rule: CompiledRule,
    assignment_id: str,
) -> CompiledAssignment:
    """Return a compiled assignment by identifier."""
    for assignment in rule.assignments:
        if assignment.assignment_id == assignment_id:
            return assignment
    raise KeyError(f"Assignment {assignment_id!r} is absent from the selected rule.")


def _temporary_ruleset(rule: Rule) -> Ruleset:
    """Wrap one draft rule in the minimum compilable ruleset metadata."""
    return Ruleset(
        ruleset_id="studio_probe",
        ruleset_name="Studio probe",
        version="1",
        owner="Rules Engine Studio",
        owner_department="Authoring",
        rules=[rule],
    )


def _temporary_assignment(operand: Operand) -> Assignment:
    """Wrap one operand in a temporary assignment for public compiler access."""
    return Assignment(
        assignment_id="assignment:studio_probe:value",
        target_field="value",
        value=operand,
    )


def _compile_operand(operand: Operand):
    """Compile one operand by embedding it in a valid public authoring payload."""
    probe = Rule(
        rule_id="studio_probe_rule",
        rule_name="Studio probe rule",
        rule_order=1,
        conditions=_probe_condition_group(),
        assignments=[_temporary_assignment(operand)],
    )
    return compile_ruleset(_temporary_ruleset(probe)).rules[0].assignments[0].value


def _resolved_operand(
    operand: CompiledOperand,
    row: Mapping[str, Any],
    runtime: SparkRowEvaluator,
    assigned_values: Mapping[str, AssignedValue] | None = None,
) -> Resolution:
    """Resolve a compiled operand and adapt its production trace for the UI."""
    resolved = runtime._resolve_operand_resolution(operand, row, assigned_values)
    trace = dict(resolved.trace)
    source = str(trace.get("kind") or "operand")
    detail = str(
        trace.get("field_name")
        or trace.get("target_field")
        or trace.get("function_name")
        or trace.get("value_type")
        or source
    )
    return Resolution(resolved.value, source, detail, trace=trace)


def _probe_condition_group():
    """Return an always-true condition group used by operand probes."""
    from .schema import ConditionGroup

    return ConditionGroup(
        condition_group_id="group:studio_probe",
        children=[
            Condition(
                condition_id="condition:studio_probe",
                left=Operand(kind="literal", value=True, value_type="boolean"),
                operator="eq",
                right=Operand(kind="literal", value=True, value_type="boolean"),
            )
        ],
    )


def resolve_operand(
    operand: Operand,
    row: dict[str, Any],
    functions: Any | None = None,
) -> Resolution:
    """
    Resolve one operand with production runtime behavior.

    Parameters
    ----------
    operand : Operand
        Mutable studio operand.
    row : dict[str, Any]
        Input row values.
    functions : Any | None, default None
        Retained for API compatibility. The authoritative registry is always
        used.

    Returns
    -------
    Resolution
        Resolved value and production trace metadata.
    """
    del functions
    try:
        compiled = _compile_operand(operand)
        return _resolved_operand(compiled, row, _runtime())
    except _ENGINE_EXCEPTIONS as exc:
        raise OperandError(f"{type(exc).__name__}: {exc}") from exc


def evaluate_condition(
    condition: Condition,
    row: dict[str, Any],
    functions: Any | None = None,
    *,
    ruleset: Ruleset | None = None,
    owning_rule: Rule | None = None,
) -> dict[str, Any]:
    """
    Evaluate one condition with production comparison and null semantics.

    Parameters
    ----------
    condition : Condition
        Mutable studio condition.
    row : dict[str, Any]
        Input row values.
    functions : Any | None, default None
        Retained for API compatibility. The authoritative registry is always
        used.

    Returns
    -------
    dict[str, Any]
        Presentation-ready production condition trace.
    """
    del functions
    try:
        runtime = _runtime()
        if ruleset is not None and owning_rule is not None:
            compiled_rule, assigned_values = _focused_rule_context(
                ruleset,
                owning_rule,
                row,
                runtime,
            )
            compiled_condition, compiled_group = _compiled_condition(
                compiled_rule.root_group,
                condition.condition_id,
            )
        elif ruleset is None and owning_rule is None:
            probe = Rule(
                rule_id="studio_condition_probe",
                rule_name="Studio condition probe",
                rule_order=1,
                conditions=_group_for_condition(condition),
                assignments=[
                    Assignment(
                        assignment_id="assignment:studio_condition_probe:matched",
                        target_field="matched",
                        value=Operand(kind="literal", value=True, value_type="boolean"),
                    )
                ],
            )
            compiled_rule = compile_ruleset(_temporary_ruleset(probe)).rules[0]
            compiled_group = compiled_rule.root_group
            compiled_condition = compiled_group.conditions[0]
            assigned_values = None
        else:
            raise TypeError("ruleset and owning_rule must be supplied together.")
        trace = runtime._evaluate_condition(
            compiled_condition,
            compiled_group,
            row,
            assigned_values,
        )
    except _ENGINE_EXCEPTIONS as exc:
        raise OperandError(f"{type(exc).__name__}: {exc}") from exc
    payload = asdict(trace)
    left = payload.get("left") or {}
    right = payload.get("right") or {}
    payload.update(
        expression=condition.describe(),
        matched=payload["passed"],
        left_value=left.get("value"),
        right_value=right.get("value"),
    )
    return payload


def _group_for_condition(condition: Condition):
    """Return a one-condition group with a stable probe identifier."""
    from .schema import ConditionGroup

    return ConditionGroup(
        logical_operator="all",
        condition_group_id="group:studio_condition_probe",
        children=[condition],
    )


def evaluate_rule(
    rule: Rule,
    row: dict[str, Any],
    functions: Any | None = None,
    *,
    ruleset: Ruleset | None = None,
) -> dict[str, Any]:
    """
    Evaluate one rule and return production condition traces.

    Parameters
    ----------
    rule : Rule
        Mutable studio rule.
    row : dict[str, Any]
        Input row values.
    functions : Any | None, default None
        Retained for API compatibility. The authoritative registry is always
        used.

    Returns
    -------
    dict[str, Any]
        Match result, assignments, and production condition traces.
    """
    del functions
    try:
        runtime = _runtime()
        if ruleset is None:
            compiled_rule = compile_ruleset(_temporary_ruleset(rule)).rules[0]
            assigned_values = None
        else:
            compiled_rule, assigned_values = _focused_rule_context(
                ruleset,
                rule,
                row,
                runtime,
            )
        matched, traces = runtime._evaluate_rule(
            compiled_rule,
            row,
            assigned_values,
        )
        assignments = (
            runtime._evaluate_assignments(
                compiled_rule.assignments,
                row,
                assigned_values,
            )
            if matched
            else {}
        )
    except _ENGINE_EXCEPTIONS as exc:
        raise OperandError(f"{type(exc).__name__}: {exc}") from exc
    return {
        "rule_id": compiled_rule.rule_id,
        "rule_order": compiled_rule.rule_order,
        "matched": matched,
        "stop_on_match": compiled_rule.stop_on_match,
        "assign": assignments,
        "condition_trace": [asdict(trace) for trace in traces],
    }


def evaluate_assignment(
    assignment: Assignment,
    row: dict[str, Any],
    functions: Any | None = None,
    *,
    ruleset: Ruleset | None = None,
    owning_rule: Rule | None = None,
) -> Resolution:
    """Resolve one assignment value with production operand behavior."""
    if ruleset is None and owning_rule is None:
        return resolve_operand(assignment.value, row, functions)
    if ruleset is None or owning_rule is None:
        raise OperandError("ruleset and owning_rule must be supplied together.")
    del functions
    try:
        runtime = _runtime()
        compiled_rule, assigned_values = _focused_rule_context(
            ruleset,
            owning_rule,
            row,
            runtime,
        )
        compiled = _compiled_assignment(compiled_rule, assignment.assignment_id)
        return _resolved_operand(
            compiled.value,
            row,
            runtime,
            assigned_values,
        )
    except _ENGINE_EXCEPTIONS as exc:
        raise OperandError(f"{type(exc).__name__}: {exc}") from exc


def result_fields(*, full_audit: bool = False) -> tuple[str, ...]:
    """Return studio output fields for the requested production audit detail."""
    return FULL_AUDIT_FIELDS if full_audit else COMPACT_FIELDS


def empty_result(*, full_audit: bool = False) -> dict[str, Any]:
    """Return the stable studio wrapper around an unevaluated production result."""
    result = {
        "error": None,
        "matched": False,
        "matched_rule_ids": [],
        "assign": {},
    }
    if full_audit:
        result.update(
            matched_rules=[],
            assignment_results=[],
            ruleset=None,
            engine_version=__version__,
        )
    return result


def evaluate_row(
    ruleset: Ruleset,
    row: dict[str, Any],
    functions: Any | None = None,
    *,
    full_audit: bool = False,
) -> dict[str, Any]:
    """
    Evaluate one row using the production worker-side runtime.

    Parameters
    ----------
    ruleset : Ruleset
        Mutable studio draft.
    row : dict[str, Any]
        Input row values.
    functions : Any | None, default None
        Retained for API compatibility. The authoritative registry is always
        used.
    full_audit : bool, default False
        Include production matched-rule traces, assignment provenance, and
        immutable engine identity.

    Returns
    -------
    dict[str, Any]
        Production match and assignment result plus a studio error field.
    """
    return evaluate_rows(
        ruleset,
        [row],
        functions,
        full_audit=full_audit,
    )[0]


def evaluate_rows(
    ruleset: Ruleset,
    rows: list[dict[str, Any]],
    functions: Any | None = None,
    *,
    full_audit: bool = False,
) -> list[dict[str, Any]]:
    """Evaluate rows while compiling and building audit infrastructure once."""
    del functions
    results = [empty_result(full_audit=full_audit) for _ in rows]
    if not rows:
        return results
    try:
        compiled = compile_ruleset(ruleset)
        runtime = _runtime()
    except _ENGINE_EXCEPTIONS as exc:
        error = f"{type(exc).__name__}: {exc}"
        for result in results:
            result["error"] = error
        return results

    compacts: list[dict[str, Any] | None] = []
    for row, result in zip(rows, results, strict=True):
        try:
            compact = runtime.evaluate_row(compiled, row)
        except _ENGINE_EXCEPTIONS as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
            compacts.append(None)
            continue
        compacts.append(compact)
        if not full_audit:
            result.update(compact)

    if not full_audit:
        return results

    successful = [
        (row, compact)
        for row, compact in zip(rows, compacts, strict=True)
        if compact is not None
    ]
    if not successful:
        return results
    try:
        evaluator, identity = _full_audit_context(
            compiled,
            [row for row, _ in successful],
            [compact for _, compact in successful],
        )
    except _ENGINE_EXCEPTIONS as exc:
        error = f"{type(exc).__name__}: {exc}"
        for result, compact in zip(results, compacts, strict=True):
            if compact is not None:
                result["error"] = error
        return results

    for row, compact, result in zip(rows, compacts, results, strict=True):
        if compact is None:
            continue
        try:
            result.update(
                _full_audit_result(
                    row,
                    compact,
                    evaluator=evaluator,
                    identity=identity,
                )
            )
        except _ENGINE_EXCEPTIONS as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
    return results


def _full_audit_context(
    ruleset: CompiledRuleset,
    rows: list[Mapping[str, Any]],
    compacts: list[Mapping[str, Any]],
) -> tuple[Any, dict[str, str]]:
    """Build one full-audit evaluator and immutable identity for a row batch."""
    assignment_fields = sorted(
        {assignment.target_field for rule in ruleset.rules for assignment in rule.assignments}
    )
    assignment_types = {
        field_name: _spark_type_for_assignment_batch(field_name, rows, compacts)
        for field_name in assignment_fields
    }
    evaluator = SparkRulesEngineRuntime(object(), authoring.registry())._build_row_evaluator(
        ruleset,
        assignment_fields,
        assignment_types,
        full_audit=True,
    )
    identity = {
        "id": ruleset.ruleset_id,
        "version": ruleset.version,
        "content_hash": DeltaRowSerializer().content_hash(ruleset),
    }
    return evaluator, identity


def _full_audit_result(
    row: Mapping[str, Any],
    compact: Mapping[str, Any],
    *,
    evaluator: Any,
    identity: Mapping[str, str],
) -> dict[str, Any]:
    """Evaluate one row with the production Spark worker full-audit contract."""
    audit = evaluator(_SparkRow(row))
    for field_name in COMPACT_FIELDS:
        if field_name != "error":
            audit[field_name] = compact[field_name]
    audit.update(
        ruleset=dict(identity),
        engine_version=__version__,
    )
    return audit


def _spark_type_for_assignment_batch(
    field_name: str,
    rows: list[Mapping[str, Any]],
    compacts: list[Mapping[str, Any]],
) -> T.DataType:
    """Infer one stable Spark normalization type across a production row batch."""
    values: list[Any] = []
    for row, compact in zip(rows, compacts, strict=True):
        assignment = compact.get("assign", {}).get(field_name, {})
        values.append(
            assignment.get("value") if assignment.get("applied") else row.get(field_name)
        )
    inferred: list[T.DataType] = []
    for value in values:
        if value is None:
            continue
        try:
            data_type = T._infer_type(value)
        except (TypeError, ValueError):
            continue
        if not isinstance(data_type, T.NullType):
            inferred.append(data_type)
    if not inferred:
        return T.StringType()
    if all(data_type == inferred[0] for data_type in inferred[1:]):
        return inferred[0]
    numeric_types = (
        T.ByteType,
        T.ShortType,
        T.IntegerType,
        T.LongType,
        T.FloatType,
        T.DoubleType,
        T.DecimalType,
    )
    if all(isinstance(data_type, numeric_types) for data_type in inferred):
        if any(isinstance(data_type, T.DecimalType) for data_type in inferred):
            return T.DecimalType(38, 18)
        if any(isinstance(data_type, (T.FloatType, T.DoubleType)) for data_type in inferred):
            return T.DoubleType()
        return T.LongType()
    try:
        merged = inferred[0]
        for data_type in inferred[1:]:
            merged = T._merge_type(merged, data_type)
        return merged
    except (TypeError, ValueError):
        return T.StringType()
