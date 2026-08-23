"""Tests for the Streamlit-free core: schema, YAML round-trip, evaluator.

Run with:  pytest -q
Nothing here imports streamlit, so the core stays testable in CI without a
browser or a Spark session.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from studio import custom_functions, engine, sample_data, yaml_io  # noqa: E402
from studio.schema import (  # noqa: E402
    Assignment,
    Condition,
    ConditionGroup,
    Operand,
    Rule,
    Ruleset,
    referenced_columns,
)
from studio.text_operands import format_operand_text, parse_operand_text  # noqa: E402


def field(name: str) -> Operand:
    return Operand(kind="field", field_name=name)


def lit(value, value_type="string") -> Operand:
    return Operand(kind="literal", value=value, value_type=value_type)


# --------------------------------------------------------------------------
# YAML round-trip
# --------------------------------------------------------------------------


def test_demo_ruleset_round_trips_through_yaml():
    original = sample_data.demo_ruleset()
    restored = yaml_io.from_yaml(yaml_io.to_yaml(original))
    assert restored.to_dict() == original.to_dict()


def test_round_trip_preserves_nested_groups_and_function_operands():
    ruleset = Ruleset(
        ruleset_id="nested",
        version="1.0.0",
        rules=[
            Rule(
                rule_id="r1",
                rule_order=10,
                conditions=ConditionGroup(
                    logic="any",
                    children=[
                        Condition(left=field("a"), operator="equals", right=lit("x")),
                        ConditionGroup(
                            logic="all",
                            children=[
                                Condition(
                                    left=Operand(
                                        kind="function",
                                        function="upper",
                                        args=[field("b")],
                                    ),
                                    operator="equals",
                                    right=lit("Y"),
                                )
                            ],
                        ),
                    ],
                ),
                assignments=[Assignment(target_field="out", value=lit(3, "integer"))],
            )
        ],
    )
    restored = yaml_io.from_yaml(yaml_io.to_yaml(ruleset))
    assert restored.to_dict() == ruleset.to_dict()
    inner = restored.rules[0].conditions.children[1]
    assert isinstance(inner, ConditionGroup)
    assert inner.children[0].left.function == "upper"


def test_unary_operator_drops_the_right_hand_side_on_export():
    condition = Condition(left=field("a"), operator="is_null", right=lit("ignored"))
    assert "right" not in condition.to_dict()


def test_referenced_columns_includes_function_arguments():
    ruleset = sample_data.demo_ruleset()
    assert {"cost_centre", "job_family"} <= referenced_columns(ruleset)


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------


def test_duplicate_rule_ids_are_an_error():
    ruleset = Ruleset(
        rules=[Rule(rule_id="same", rule_order=10), Rule(rule_id="same", rule_order=20)]
    )
    issues = yaml_io.validate(ruleset)
    assert yaml_io.has_errors(issues)
    assert any("used 2 times" in i.message for i in issues)


def test_missing_column_is_a_warning_not_an_error():
    ruleset = Ruleset(
        rules=[
            Rule(
                rule_id="r1",
                rule_order=10,
                conditions=ConditionGroup(
                    children=[Condition(left=field("absent"), operator="equals", right=lit("x"))]
                ),
                assignments=[Assignment(target_field="out", value=lit("v"))],
            )
        ]
    )
    issues = yaml_io.validate(ruleset, columns=["present"])
    assert not yaml_io.has_errors(issues)
    assert any("not in the sample data" in i.message for i in issues)


def test_renumber_produces_a_gapped_sequence():
    ruleset = Ruleset(
        rules=[
            Rule(rule_id="b", rule_order=7),
            Rule(rule_id="a", rule_order=3),
        ]
    )
    yaml_io.renumber(ruleset)
    assert [r.rule_id for r in ruleset.ordered_rules()] == ["a", "b"]
    assert [r.rule_order for r in ruleset.ordered_rules()] == [10, 20]


# --------------------------------------------------------------------------
# mini-syntax
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "field:job_family",
        "str:Engineering",
        "int:5",
        "num:0.8",
        "bool:true",
        "list:a,b,c",
        "null",
        "fn:upper(field:region)",
        "fn:concat(field:a|str:-|fn:upper(field:b))",
    ],
)
def test_mini_syntax_round_trips(text):
    assert format_operand_text(parse_operand_text(text)) == text


def test_bare_text_is_a_string_literal():
    operand = parse_operand_text("Engineering")
    assert operand.kind == "literal"
    assert operand.value == "Engineering"


def test_unbalanced_parentheses_are_rejected():
    with pytest.raises(ValueError):
        parse_operand_text("fn:upper(field:a")


# --------------------------------------------------------------------------
# evaluation semantics
# --------------------------------------------------------------------------


def _row(**kwargs):
    return kwargs


def test_last_assignment_wins_across_rules():
    ruleset = Ruleset(
        rules=[
            Rule(
                rule_id="first",
                rule_order=10,
                conditions=ConditionGroup(children=[]),
                assignments=[Assignment(target_field="tier", value=lit("one"))],
            ),
            Rule(
                rule_id="second",
                rule_order=20,
                conditions=ConditionGroup(children=[]),
                assignments=[Assignment(target_field="tier", value=lit("two"))],
            ),
        ]
    )
    result = engine.evaluate_row(ruleset, _row(x=1), full_audit=True)
    assert result["assign"] == {"tier": "two"}
    assert result["matched_rule_ids"] == ["first", "second"]
    overridden = [a for a in result["assignment_results"] if not a["effective"]]
    assert len(overridden) == 1
    assert overridden[0]["overridden_by"] == "second"


def test_stop_on_match_only_stops_when_the_rule_matched():
    ruleset = Ruleset(
        rules=[
            Rule(
                rule_id="never",
                rule_order=10,
                stop_on_match=True,
                conditions=ConditionGroup(
                    children=[Condition(left=field("x"), operator="equals", right=lit(99, "integer"))]
                ),
                assignments=[Assignment(target_field="out", value=lit("no"))],
            ),
            Rule(
                rule_id="reached",
                rule_order=20,
                conditions=ConditionGroup(children=[]),
                assignments=[Assignment(target_field="out", value=lit("yes"))],
            ),
        ]
    )
    result = engine.evaluate_row(ruleset, _row(x=1))
    assert result["matched_rule_ids"] == ["reached"]
    assert result["assign"] == {"out": "yes"}


def test_stop_on_match_halts_later_rules():
    ruleset = Ruleset(
        rules=[
            Rule(
                rule_id="stopper",
                rule_order=10,
                stop_on_match=True,
                conditions=ConditionGroup(children=[]),
                assignments=[Assignment(target_field="out", value=lit("first"))],
            ),
            Rule(
                rule_id="unreached",
                rule_order=20,
                conditions=ConditionGroup(children=[]),
                assignments=[Assignment(target_field="out", value=lit("second"))],
            ),
        ]
    )
    result = engine.evaluate_row(ruleset, _row(x=1))
    assert result["matched_rule_ids"] == ["stopper"]
    assert result["assign"] == {"out": "first"}


def test_inactive_rules_and_conditions_are_skipped():
    ruleset = Ruleset(
        rules=[
            Rule(
                rule_id="off",
                rule_order=10,
                active_flag=False,
                conditions=ConditionGroup(children=[]),
                assignments=[Assignment(target_field="out", value=lit("no"))],
            ),
            Rule(
                rule_id="on",
                rule_order=20,
                conditions=ConditionGroup(
                    children=[
                        Condition(
                            left=field("x"),
                            operator="equals",
                            right=lit(99, "integer"),
                            active_flag=False,
                        )
                    ]
                ),
                assignments=[Assignment(target_field="out", value=lit("yes"))],
            ),
        ]
    )
    result = engine.evaluate_row(ruleset, _row(x=1))
    assert result["matched_rule_ids"] == ["on"]


def test_error_row_keeps_the_quarantine_shape_under_full_audit():
    ruleset = Ruleset(
        rules=[
            Rule(
                rule_id="boom",
                rule_order=10,
                conditions=ConditionGroup(
                    children=[Condition(left=field("missing"), operator="equals", right=lit("x"))]
                ),
                assignments=[Assignment(target_field="out", value=lit("v"))],
            )
        ]
    )
    result = engine.evaluate_row(ruleset, _row(x=1), full_audit=True)
    assert result["error"] is not None
    assert result["matched"] is False
    assert result["matched_rule_ids"] == []
    assert result["assign"] is None
    assert result["matched_rules"] == []
    assert result["assignment_results"] == []
    assert result["first_matched_rule_trace"] is None


def test_full_audit_does_not_change_the_decision():
    ruleset = sample_data.demo_ruleset()
    rows = sample_data.DEMO_ROWS
    compact = engine.evaluate_rows(ruleset, rows, full_audit=False)
    audited = engine.evaluate_rows(ruleset, rows, full_audit=True)
    for left, right in zip(compact, audited):
        for key in engine.COMPACT_FIELDS:
            assert left[key] == right[key]


def test_null_operand_defaults_to_no_match_and_policy_can_flip_it():
    condition = Condition(left=field("x"), operator="equals", right=lit("a"))
    assert engine.evaluate_condition(condition, {"x": None})["matched"] is False
    condition.null_result = "true"
    assert engine.evaluate_condition(condition, {"x": None})["matched"] is True


def test_any_group_matches_when_one_child_matches():
    group = ConditionGroup(
        logic="any",
        children=[
            Condition(left=field("x"), operator="equals", right=lit(1, "integer")),
            Condition(left=field("x"), operator="equals", right=lit(2, "integer")),
        ],
    )
    assert engine.evaluate_group(group, {"x": 2})["matched"] is True
    assert engine.evaluate_group(group, {"x": 3})["matched"] is False


def test_custom_function_operand_resolves_through_the_registry():
    operand = Operand(kind="function", function="leaf_key", args=[field("a"), field("b")])
    resolution = engine.resolve_operand(operand, {"a": "CC-100", "b": "Engineering"}, custom_functions.registry())
    assert resolution.value == "cc-100/engineering"


def test_unregistered_function_is_reported_not_swallowed():
    operand = Operand(kind="function", function="nope", args=[])
    with pytest.raises(engine.OperandError):
        engine.resolve_operand(operand, {}, custom_functions.registry())


def test_output_columns_follow_the_contract_order():
    assert engine.output_columns("re", full_audit=False) == [
        "re_error",
        "re_matched",
        "re_matched_rule_ids",
        "re_assign",
        "re_ruleset",
        "re_engine_version",
    ]
    audited = engine.output_columns("re", full_audit=True)
    assert audited.index("re_matched_rules") == 4
    assert audited[-2:] == ["re_ruleset", "re_engine_version"]
