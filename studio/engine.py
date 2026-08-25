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
from dataclasses import asdict, dataclass, field
from typing import Any

from pyspark.sql import types as T
from rules_engine.exceptions import RulesEngineError
from rules_engine.models import Ruleset as CompiledRuleset
from rules_engine.runtime import SparkRowEvaluator
from rules_engine.serializer import DeltaRowSerializer
from rules_engine.spark_runtime import SparkRulesEngineRuntime

from rules_engine import __version__

from . import authoring
from .schema import Assignment, Condition, Operand, Rule, Ruleset

COMPACT_FIELDS = ("error", "matched", "matched_rule_ids", "assign")
FULL_AUDIT_ONLY_FIELDS = ("matched_rules", "assignment_results")
AUDIT_IDENTITY_FIELDS = ("ruleset", "engine_version")
FULL_AUDIT_FIELDS = COMPACT_FIELDS + FULL_AUDIT_ONLY_FIELDS + AUDIT_IDENTITY_FIELDS
_ENGINE_EXCEPTIONS = (ArithmeticError, KeyError, RulesEngineError, TypeError, ValueError)


class OperandError(Exception):
    """Raised when the production compiler or evaluator rejects an authoring operation."""


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
        resolved = _runtime()._resolve_operand_resolution(compiled, row)
    except _ENGINE_EXCEPTIONS as exc:
        raise OperandError(f"{type(exc).__name__}: {exc}") from exc
    trace = dict(resolved.trace)
    source = str(trace.get("kind") or operand.kind)
    detail = str(
        trace.get("field_name")
        or trace.get("target_field")
        or trace.get("function_name")
        or trace.get("value_type")
        or source
    )
    return Resolution(resolved.value, source, detail, trace=trace)


def evaluate_condition(
    condition: Condition,
    row: dict[str, Any],
    functions: Any | None = None,
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
    try:
        compiled_rule = compile_ruleset(_temporary_ruleset(probe)).rules[0]
        compiled_group = compiled_rule.root_group
        trace = _runtime()._evaluate_condition(
            compiled_group.conditions[0],
            compiled_group,
            row,
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
        compiled_rule = compile_ruleset(_temporary_ruleset(rule)).rules[0]
        matched, traces = _runtime()._evaluate_rule(compiled_rule, row)
        assignments = (
            _runtime()._evaluate_assignments(compiled_rule.assignments, row) if matched else {}
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
) -> Resolution:
    """Resolve one assignment value with production operand behavior."""
    return resolve_operand(assignment.value, row, functions)


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
    del functions
    result = empty_result(full_audit=full_audit)
    try:
        compiled = compile_ruleset(ruleset)
        compact = _runtime().evaluate_row(compiled, row)
        if full_audit:
            result.update(_full_audit_result(compiled, row, compact))
        else:
            result.update(compact)
    except _ENGINE_EXCEPTIONS as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def evaluate_rows(
    ruleset: Ruleset,
    rows: list[dict[str, Any]],
    functions: Any | None = None,
    *,
    full_audit: bool = False,
) -> list[dict[str, Any]]:
    """Evaluate input rows independently with production row semantics."""
    return [evaluate_row(ruleset, row, functions, full_audit=full_audit) for row in rows]


def _full_audit_result(
    ruleset: CompiledRuleset,
    row: Mapping[str, Any],
    compact: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate one row with the production Spark worker full-audit contract."""
    assignment_fields = sorted(
        {assignment.target_field for rule in ruleset.rules for assignment in rule.assignments}
    )
    assignment_types = {
        field_name: _spark_type_for_assignment(field_name, row, compact)
        for field_name in assignment_fields
    }
    evaluator = SparkRulesEngineRuntime(object(), authoring.registry())._build_row_evaluator(
        ruleset,
        assignment_fields,
        assignment_types,
        full_audit=True,
    )
    audit = evaluator(_SparkRow(row))
    for field_name in COMPACT_FIELDS:
        if field_name != "error":
            audit[field_name] = compact[field_name]
    audit.update(
        ruleset={
            "id": ruleset.ruleset_id,
            "version": ruleset.version,
            "content_hash": DeltaRowSerializer().content_hash(ruleset),
        },
        engine_version=__version__,
    )
    return audit


def _spark_type_for_assignment(
    field_name: str,
    row: Mapping[str, Any],
    compact: Mapping[str, Any],
) -> T.DataType:
    """Infer the Spark normalization type from the production compact result."""
    assignment = compact.get("assign", {}).get(field_name, {})
    value = assignment.get("value") if assignment.get("applied") else row.get(field_name)
    if value is None:
        return T.StringType()
    try:
        inferred = T._infer_type(value)
    except (TypeError, ValueError):
        return T.StringType()
    return T.StringType() if isinstance(inferred, T.NullType) else inferred
