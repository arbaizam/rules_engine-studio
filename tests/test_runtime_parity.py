"""Regression coverage for the refactored engine's Spark and focused contracts."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pyspark.sql import types as T

from rules_engine import FunctionRegistry, register_standard_functions
from rules_engine.registry import CustomFunctionArgSpec, CustomFunctionSpec
from studio import authoring, engine, sample_data, type_compatibility
from studio.schema import Assignment, Condition, ConditionGroup, Operand, Rule, Ruleset
from studio.ui.evaluate import _results_frame


def literal(value):
    """Return a literal whose canonical type is inferred from its Python value."""
    return Operand(value=value, value_type=None)


def draft_rule(name, order, value, *, target="output", left=None, right=None):
    """Return an owned rule with stable identifiers and an equality condition."""
    return Rule(
        rule_id=name,
        rule_name=name,
        rule_order=order,
        conditions=ConditionGroup(
            condition_group_id=f"group:{name}",
            children=[
                Condition(
                    condition_id=f"condition:{name}",
                    left=left or literal(True),
                    operator="eq",
                    right=right or literal(True),
                )
            ],
        ),
        assignments=[
            Assignment(
                assignment_id=f"assignment:{name}",
                target_field=target,
                value=value,
            )
        ],
    )


def draft(*rules):
    """Return a canonical owned draft containing the supplied rules."""
    return Ruleset(
        ruleset_id="parity",
        ruleset_name="Parity",
        version="1",
        owner="Rules team",
        owner_department="Engineering",
        rules=list(rules),
    )


@pytest.mark.parametrize("full_audit", [False, True])
def test_sample_evaluation_runs_custom_functions_once_per_operand(monkeypatch, full_audit):
    """Audit detail must never repeat a function invocation or invent different results."""
    calls = []
    registry = register_standard_functions(FunctionRegistry())

    def observe(*, value):
        calls.append(value)
        return value

    registry.register(
        CustomFunctionSpec(
            function_name="observe",
            implementation_reference="tests.observe",
            arguments=(CustomFunctionArgSpec("value", type_hint="boolean"),),
            allowed_in_condition_flag=True,
            allowed_in_assignment_flag=True,
            return_type_hint="boolean",
        ),
        observe,
    )
    monkeypatch.setattr(authoring, "registry", lambda: registry)
    operand = Operand(kind="custom_function", function="observe", args={"value": literal(True)})
    ruleset = draft(draft_rule("count", 1, operand, left=operand))
    results = engine.evaluate_rows(ruleset, [{}, {}], full_audit=full_audit)
    assert all(result["error"] is None for result in results)
    assert calls == [True] * 4


def test_compact_audit_and_focused_scopes_share_normalized_assignments():
    """Later rules read Spark-normalized assignments in every inspection scope."""
    producer = draft_rule("producer", 1, literal(1), target="amount")
    rendered_amount = Operand(
        kind="custom_function",
        function="to_string",
        args={"value": Operand(kind="assigned", assigned_field="amount")},
    )
    consumer = draft_rule(
        "consumer", 2, rendered_amount, left=rendered_amount, right=literal("1.0")
    )
    ruleset = draft(producer, consumer)
    row = {"amount": 0.5}
    compact = engine.evaluate_row(ruleset, row)
    audit = engine.evaluate_row(ruleset, row, full_audit=True)
    assert compact["error"] is None
    assert compact["matched_rule_ids"] == ["producer", "consumer"]
    assert compact == {name: audit[name] for name in engine.result_fields()}
    assert isinstance(compact["assign"]["amount"]["value"], float)
    focused = engine.evaluate_rule(consumer, row, ruleset=ruleset)
    assert focused["assign"] == {"output": "1.0"}
    condition = consumer.conditions.children[0]
    assert (
        engine.evaluate_condition(condition, row, ruleset=ruleset, owning_rule=consumer)["matched"]
        is True
    )
    assert (
        engine.evaluate_assignment(
            consumer.assignments[0], row, ruleset=ruleset, owning_rule=consumer
        ).value
        == "1.0"
    )


@pytest.mark.parametrize("full_audit", [False, True])
def test_sample_schema_rejects_missing_source_even_when_defaulted(full_audit):
    """A null default cannot create a missing Spark source column."""
    source = Operand(kind="field", field_name="missing", default_if_null=literal(True))
    ruleset = draft(draft_rule("missing", 1, literal(True), left=source))
    result = engine.evaluate_row(ruleset, {}, full_audit=full_audit)
    assert "SPARK_CONDITION_FIELD_MISSING" in result["error"]
    assert result["matched"] is False
    assert engine.evaluate_row(ruleset, {"missing": None})["matched"] is True


def test_assignment_types_are_validated_before_stop_on_match():
    """Spark preflight checks every active rule even when the sample stops early."""
    first = draft_rule("first", 1, literal(1))
    first.stop_on_match = True
    later = draft_rule("later", 2, literal("incompatible"))
    result = engine.evaluate_row(draft(first, later), {})
    assert "SPARK_ASSIGNMENT_TYPE_CONFLICT" in result["error"]
    assert result["matched"] is False


def test_assignment_inspection_skips_unmatched_and_inactive_rules():
    """An operand value must not masquerade as an assignment that never applies."""
    rule = draft_rule("unmatched", 1, literal("proposed"), right=literal(False))
    ruleset = draft(rule)
    with pytest.raises(engine.FocusedEvaluationSkipped, match="does not match"):
        engine.evaluate_assignment(rule.assignments[0], {}, ruleset=ruleset, owning_rule=rule)
    rule.active_flag = False
    ruleset.rules.append(draft_rule("active", 2, literal(True)))
    with pytest.raises(engine.FocusedEvaluationSkipped, match="inactive"):
        engine.evaluate_rule(rule, {}, ruleset=ruleset)


def test_assignment_inspection_respects_atomic_sibling_failure():
    """No selected assignment is reported as committed when its sibling fails."""
    rule = draft_rule("atomic", 1, literal("proposed"))
    rule.assignments.append(
        Assignment(
            assignment_id="assignment:atomic:bad",
            target_field="bad",
            value=Operand(
                kind="custom_function", function="to_integer", args={"value": literal("bad")}
            ),
        )
    )
    with pytest.raises(engine.OperandError, match="integer"):
        engine.evaluate_assignment(rule.assignments[0], {}, ruleset=draft(rule), owning_rule=rule)


def test_inactive_conditions_emit_inactive_traces_without_resolving_fields():
    """Inactive conditions need no source column and still return canonical false."""
    rule = draft_rule(
        "inactive_condition", 1, literal(True), left=Operand(kind="field", field_name="absent")
    )
    condition = rule.conditions.children[0]
    condition.active_flag = False
    result = engine.evaluate_condition(condition, {}, ruleset=draft(rule), owning_rule=rule)
    assert result["active_flag"] is False
    assert result["matched"] is False
    assert result["left"]["evaluated"] is False


def test_sample_schema_preserves_temporal_kind_and_exact_decimal():
    """Naive and offset-aware sample datetimes must not collapse to the same type."""
    schema = engine.sample_schema(
        [
            {
                "wall_clock": datetime(2026, 9, 4),  # noqa: DTZ001 - intentional TimestampNTZ.
                "instant": datetime(2026, 9, 4, tzinfo=timezone.utc),
                "amount": Decimal("12345678901234567890.123456789012345678"),
            }
        ]
    )
    assert isinstance(schema["wall_clock"].dataType, T.TimestampNTZType)
    assert isinstance(schema["instant"].dataType, T.TimestampType)
    assert schema["amount"].dataType == T.DecimalType(38, 18)


def test_mixed_sample_column_is_not_silently_stringified():
    """Ambiguous sample types must produce a useful source-schema error."""
    with pytest.raises(TypeError, match="sample data.value.*incompatible"):
        engine.sample_schema([{"value": 1}, {"value": "two"}])


@pytest.mark.parametrize("prefix", ["", " ", "rules_engine"])
def test_csv_result_projection_rejects_unsafe_output_prefix(prefix):
    """The CSV projection cannot silently overwrite a source audit column."""
    rows = [{"RULES_ENGINE_MATCHED_RULES": "original"}]
    with pytest.raises(ValueError, match="prefix|Prefix"):
        _results_frame(rows, [engine.empty_result()], prefix, full_audit=False)


def test_demo_full_dataset_has_compact_audit_parity():
    """The shipped examples must validate and evaluate under the real Spark schema."""
    rows = type_compatibility.normalized_records(sample_data.demo_frame())
    ruleset = sample_data.demo_ruleset()
    compact = engine.evaluate_rows(ruleset, rows)
    audit = engine.evaluate_rows(ruleset, rows, full_audit=True)
    assert all(result["error"] is None for result in compact + audit)
    assert compact == [{name: result[name] for name in engine.result_fields()} for result in audit]
    assert any(result["matched"] for result in compact)


def test_full_batch_schema_is_used_for_a_null_focused_row():
    """A null sample row retains its column type from the other sample rows."""
    rule = draft_rule("copy", 1, Operand(kind="field", field_name="amount"))
    rows = [{"amount": None}, {"amount": Decimal("2.1")}]
    result = engine.evaluate_rule(rule, rows[0], source_schema=engine.sample_schema(rows))
    assert result["matched"] is True
    assert result["assign"] == {"output": None}


def test_mixed_numeric_samples_are_materialized_with_the_batch_spark_type():
    """A double source column must expose 1.0 consistently to custom functions."""
    rendered = Operand(
        kind="custom_function",
        function="to_string",
        args={"value": Operand(kind="field", field_name="amount")},
    )
    rule = draft_rule("render", 1, rendered)
    rows = [{"amount": 1}, {"amount": 1.5}]
    results = engine.evaluate_rows(draft(rule), rows)
    assert [result["assign"]["output"]["value"] for result in results] == ["1.0", "1.5"]
    focused = engine.evaluate_rule(rule, rows[0], source_schema=engine.sample_schema(rows))
    assert focused["assign"] == {"output": "1.0"}


@pytest.mark.parametrize(
    "rows",
    [
        [{"amount": 2**63}, {"amount": 1}],
        [{"amount": 2**53 + 1}, {"amount": 1.5}],
    ],
)
def test_samples_cannot_overflow_or_lose_integer_precision(rows):
    """Invalid input serialization fails that row without inventing a match."""
    rule = draft_rule("integer", 1, literal(True))
    results = engine.evaluate_rows(draft(rule), rows)
    assert results[0]["error"]
    assert results[0]["matched"] is False
    assert results[1]["error"] is None
    assert results[1]["matched"] is True
