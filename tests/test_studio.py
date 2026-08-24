"""
Contract tests for Rules Engine Studio.

The tests exercise the Streamlit-free integration boundary: mutable authoring
models, canonical compilation and export, production validation, the standard
function registry, row evaluation, and uploaded test data.
"""

from __future__ import annotations

import ast
from datetime import date
from decimal import Decimal
from pathlib import Path

from rules_engine.enums import ComparisonOperator, OperandKind
from rules_engine.standard_functions import STANDARD_FUNCTION_SPECS

from studio import custom_functions, engine, sample_data, state, yaml_io
from studio.schema import (
    OPERATOR_NAMES,
    Assignment,
    Condition,
    ConditionGroup,
    Operand,
    Rule,
    Ruleset,
    referenced_columns,
)


def field(name: str, *, default: object | None = None) -> Operand:
    """Return a field operand with an optional non-null literal fallback."""
    fallback = None
    if default is not None:
        fallback = Operand(kind="literal", value=default)
    return Operand(kind="field", field_name=name, default_if_null=fallback)


def assigned(name: str) -> Operand:
    """Return an assigned-value operand for an earlier rule target."""
    return Operand(kind="assigned", assigned_field=name)


def literal(value, value_type: str | None = None) -> Operand:
    """Return a literal operand with an optional explicit type hint."""
    return Operand(kind="literal", value=value, value_type=value_type)


def condition(
    condition_id: str,
    left: Operand,
    operator: str,
    right: Operand | None,
    *,
    tolerance_abs: str = "0",
) -> Condition:
    """Return one condition with explicit canonical metadata."""
    return Condition(
        condition_id=condition_id,
        left=left,
        operator=operator,
        right=right,
        tolerance_abs=Decimal(tolerance_abs),
    )


def rule(
    rule_id: str,
    order: int,
    conditions: list[Condition],
    assignments: list[Assignment],
    *,
    stop_on_match: bool = False,
) -> Rule:
    """Return one valid rule with stable group metadata."""
    return Rule(
        rule_id=rule_id,
        rule_name=rule_id.replace("_", " ").title(),
        rule_order=order,
        stop_on_match=stop_on_match,
        conditions=ConditionGroup(
            condition_group_id=f"group:{rule_id}:root",
            logical_operator="all",
            children=conditions,
        ),
        assignments=assignments,
    )


def ruleset(*rules: Rule) -> Ruleset:
    """Return a valid owned ruleset containing the supplied rules."""
    return Ruleset(
        ruleset_id="studio_test",
        ruleset_name="Studio test",
        version="1",
        owner="Rules Team",
        owner_department="Engineering",
        rules=list(rules),
    )


def assignment(assignment_id: str, target: str, value: Operand) -> Assignment:
    """Return one assignment with an explicit ruleset-unique identifier."""
    return Assignment(assignment_id=assignment_id, target_field=target, value=value)


def test_operator_catalogue_exactly_matches_engine_enum():
    """The editor must not expose aliases or omit canonical operators."""
    assert OPERATOR_NAMES == [operator.value for operator in ComparisonOperator]


def test_operand_kinds_compile_to_authoritative_models():
    """Every canonical operand kind must compile through the production compiler."""
    draft = ruleset(
        rule(
            "producer",
            10,
            [condition("condition:producer", field("x"), "eq", literal(1, "integer"))],
            [assignment("assignment:producer:a", "a", literal("A", "string"))],
        ),
        rule(
            "consumer",
            20,
            [condition("condition:consumer", assigned("a"), "eq", literal("A", "string"))],
            [
                assignment(
                    "assignment:consumer:upper",
                    "upper",
                    Operand(
                        kind="custom_function",
                        function="upper",
                        args={"value": field("name")},
                    ),
                )
            ],
        ),
    )
    compiled = engine.compile_ruleset(draft)
    kinds = {
        compiled.rules[0].root_group.conditions[0].left.kind,
        compiled.rules[0].root_group.conditions[0].right.kind,
        compiled.rules[1].root_group.conditions[0].left.kind,
        compiled.rules[1].assignments[0].value.kind,
    }
    assert kinds == {
        OperandKind.FIELD,
        OperandKind.LITERAL,
        OperandKind.ASSIGNED,
        OperandKind.CUSTOM_FUNCTION,
    }


def test_all_standard_function_specs_and_implementations_are_registered():
    """The studio registry must incorporate every engine standard function."""
    expected = sorted(specification.function_name for specification in STANDARD_FUNCTION_SPECS)
    assert custom_functions.names() == expected
    assert len(expected) == 58
    for function_name in expected:
        assert custom_functions.registry().get_spec(function_name).function_name == function_name
        assert callable(custom_functions.registry().get_implementation(function_name))


def test_demo_ruleset_passes_production_validation():
    """Starter metadata must be immediately valid and evaluable."""
    assert yaml_io.validate(sample_data.demo_ruleset()) == []


def test_demo_eligibility_rule_applies_fico_and_dscr_policy():
    """The first starter rule rejects low or missing FICO and low DSCR."""
    eligibility = sample_data.demo_ruleset().ordered_rules()[0]

    assert eligibility.rule_id == "eligibility"
    assert eligibility.rule_name == "Eligibility"
    assert eligibility.stop_on_match is True
    assert eligibility.conditions.logical_operator == "any"
    assert engine.evaluate_rule(
        eligibility,
        {"CurrentFICO": 619, "OriginalFICO": 700, "CurrentDSCR": 1.2},
    )["matched"]
    assert engine.evaluate_rule(
        eligibility,
        {"CurrentFICO": None, "OriginalFICO": None, "CurrentDSCR": 1.2},
    )["matched"]
    assert engine.evaluate_rule(
        eligibility,
        {"CurrentFICO": 700, "OriginalFICO": 710, "CurrentDSCR": 1.19},
    )["matched"]
    assert not engine.evaluate_rule(
        eligibility,
        {"CurrentFICO": None, "OriginalFICO": 700, "CurrentDSCR": 1.2},
    )["matched"]

    result = engine.evaluate_row(
        sample_data.demo_ruleset(),
        {"CurrentFICO": None, "OriginalFICO": None, "CurrentDSCR": 1.2},
    )
    assert result["matched_rule_ids"] == ["eligibility"]
    assert result["assign"]["ReviewStatus"] == {"applied": True, "value": "Ineligible"}


def test_drag_reorder_preserves_rule_order_slots(monkeypatch):
    """A complete drag order reassigns existing production order values."""
    draft = sample_data.demo_ruleset()
    original_orders = [rule.rule_order for rule in draft.ordered_rules()]
    requested_uids = [rule.uid for rule in reversed(draft.ordered_rules())]
    monkeypatch.setattr(state, "draft", lambda: draft)

    assert state.reorder_rules(requested_uids)
    assert [rule.uid for rule in draft.ordered_rules()] == requested_uids
    assert [rule.rule_order for rule in draft.ordered_rules()] == original_orders


def test_yaml_round_trip_uses_canonical_compiler_and_exporter():
    """Exported YAML must round-trip without a parallel studio dialect."""
    draft = sample_data.demo_ruleset()
    text = yaml_io.to_yaml(draft)
    reopened = yaml_io.from_yaml(text)
    assert yaml_io.to_yaml(reopened) == text
    assert "ruleset_name:" in text
    assert "when:" in text
    assert "assign:" in text
    assert "custom_function:" in text
    assert "conditions:" not in text
    assert "assignments:" not in text


def test_production_validator_reports_unknown_custom_function():
    """Function names are validated against the authoritative registry."""
    draft = ruleset(
        rule(
            "unknown_function",
            10,
            [condition("condition:unknown", field("x"), "eq", literal(1, "integer"))],
            [
                assignment(
                    "assignment:unknown:value",
                    "value",
                    Operand(kind="custom_function", function="not_registered", args={}),
                )
            ],
        )
    )
    issues = yaml_io.validate(draft)
    assert {issue.check_name for issue in issues} == {"CUSTOM_FUNCTION_UNKNOWN"}


def test_production_validator_reports_duplicate_assignment_target():
    """A rule cannot assign the same target twice even though later rules may overwrite it."""
    draft = ruleset(
        rule(
            "duplicate_target",
            10,
            [condition("condition:duplicate", field("x"), "eq", literal(1, "integer"))],
            [
                assignment("assignment:duplicate:first", "value", literal("A")),
                assignment("assignment:duplicate:second", "value", literal("B")),
            ],
        )
    )
    assert "ASSIGNMENT_TARGET_DUPLICATE_WITHIN_RULE" in {
        issue.check_name for issue in yaml_io.validate(draft)
    }


def test_missing_test_field_is_a_warning_after_engine_validation():
    """Sample-data coverage is reported separately from engine errors."""
    issues = yaml_io.validate(sample_data.demo_ruleset(), columns=["employee_id"])
    assert issues
    assert all(issue.severity == "warning" for issue in issues)
    assert all(issue.check_name == "TEST_DATA_FIELD_MISSING" for issue in issues)


def test_referenced_columns_include_nested_function_arguments():
    """Coverage must traverse operand collections inside function arguments."""
    draft = sample_data.demo_ruleset()
    assert {"CurrentFICO", "OriginalFICO", "CurrentDSCR"} <= referenced_columns(draft)


def test_row_evaluation_uses_named_function_arguments():
    """Custom functions execute through the registry's keyword contract."""
    draft = ruleset(
        rule(
            "normalize",
            10,
            [condition("condition:normalize", field("enabled"), "eq", literal(True))],
            [
                assignment(
                    "assignment:normalize:name",
                    "name",
                    Operand(
                        kind="custom_function",
                        function="upper",
                        args={"value": field("name")},
                    ),
                )
            ],
        )
    )
    result = engine.evaluate_row(draft, {"enabled": True, "name": "alpha"})
    assert result["error"] is None
    assert result["assign"]["name"] == {"applied": True, "value": "ALPHA"}


def test_row_evaluation_preserves_assigned_value_chains():
    """Later rules must read values committed by earlier matched rules."""
    draft = ruleset(
        rule(
            "producer",
            10,
            [condition("condition:producer", field("eligible"), "eq", literal(True))],
            [assignment("assignment:producer:bucket", "bucket", literal("A"))],
        ),
        rule(
            "consumer",
            20,
            [condition("condition:consumer", assigned("bucket"), "eq", literal("A"))],
            [assignment("assignment:consumer:result", "result", literal("accepted"))],
        ),
    )
    result = engine.evaluate_row(draft, {"eligible": True})
    assert result["matched_rule_ids"] == ["producer", "consumer"]
    assert result["assign"]["result"] == {"applied": True, "value": "accepted"}


def test_stop_on_match_uses_production_rule_order():
    """A matching stop rule prevents every later rule from running."""
    draft = ruleset(
        rule(
            "stop",
            10,
            [condition("condition:stop", field("x"), "eq", literal(1, "integer"))],
            [assignment("assignment:stop:value", "value", literal("first"))],
            stop_on_match=True,
        ),
        rule(
            "later",
            20,
            [condition("condition:later", field("x"), "eq", literal(1, "integer"))],
            [assignment("assignment:later:value", "value", literal("later"))],
        ),
    )
    result = engine.evaluate_row(draft, {"x": 1})
    assert result["matched_rule_ids"] == ["stop"]
    assert result["assign"]["value"]["value"] == "first"


def test_operand_default_if_null_uses_production_runtime():
    """An operand fallback is applied before the production comparison."""
    draft = ruleset(
        rule(
            "defaulted",
            10,
            [condition("condition:defaulted", field("score", default=0), "eq", literal(0))],
            [assignment("assignment:defaulted:flag", "flag", literal(True))],
        )
    )
    result = engine.evaluate_row(draft, {})
    assert result["matched"] is True
    assert result["assign"]["flag"]["value"] is True


def test_decimal_tolerance_uses_production_comparison():
    """Numeric equality tolerance is interpreted by the engine, not the studio."""
    draft = ruleset(
        rule(
            "tolerance",
            10,
            [
                condition(
                    "condition:tolerance",
                    field("score"),
                    "eq",
                    literal("1.00", "decimal"),
                    tolerance_abs="0.01",
                )
            ],
            [assignment("assignment:tolerance:flag", "flag", literal(True))],
        )
    )
    assert engine.evaluate_row(draft, {"score": Decimal("1.009")})["matched"] is True
    assert engine.evaluate_row(draft, {"score": Decimal("1.02")})["matched"] is False


def test_condition_trace_is_emitted_by_production_runtime():
    """Focused tests expose the engine's resolved values and comparison result."""
    draft_condition = condition(
        "condition:trace",
        field("name"),
        "starts_with",
        literal("A"),
    )
    trace = engine.evaluate_condition(draft_condition, {"name": "Alpha"})
    assert trace["matched"] is True
    assert trace["left_value"] == "Alpha"
    assert trace["right_value"] == "A"
    assert trace["comparison_result"] is True


def test_csv_upload_is_available_for_test_data():
    """CSV bytes must parse into rows without a filesystem round trip."""
    frame = sample_data.read_uploaded("cases.csv", b"case_id,score\nA,1\nB,2\n")
    assert frame.to_dict("records") == [
        {"case_id": "A", "score": 1},
        {"case_id": "B", "score": 2},
    ]


def test_csv_upload_parses_every_date_named_column():
    """CSV columns containing date are parsed to date values with null blanks."""
    frame = sample_data.read_uploaded(
        "loans.csv",
        b"LoanNo,EffectiveDate,currentdate,StatusFlag\nA,8/14/2026,12/31/2025,yes\nB,,,no\n",
    )
    assert frame.loc[0, "EffectiveDate"] == date(2026, 8, 14)
    assert frame.loc[0, "currentdate"] == date(2025, 12, 31)
    assert frame.loc[1, "EffectiveDate"] is None
    assert frame.loc[0, "StatusFlag"] == "yes"


def test_demo_rows_use_loan_data_with_structs_arrays_and_dates():
    """Starter rows preserve the supplied loan domain and structured test values."""
    frame = sample_data.demo_frame()
    assert frame["LoanNo"].tolist() == [f"XXXX{number}" for number in range(4, 14)]
    assert frame.loc[0, "EffectiveDate"] == date(2026, 8, 14)
    assert isinstance(frame.loc[0, "StructColumn"], dict)
    assert isinstance(frame.loc[0, "ArrayColumn"], list)


def test_struct_and_array_literals_work_in_conditions_and_assignments():
    """Canonical nested literals evaluate and assign without a studio-only dialect."""
    metadata = {"risk_band": "High", "manual_review": True}
    tags = ["NonDSCR", "Watch"]
    draft = ruleset(
        rule(
            "structured",
            10,
            [
                condition(
                    "condition:structured:struct", field("metadata"), "eq", literal(metadata)
                ),
                condition("condition:structured:array", field("tags"), "eq", literal(tags)),
            ],
            [
                assignment("assignment:structured:metadata", "output_metadata", literal(metadata)),
                assignment("assignment:structured:tags", "output_tags", literal(tags)),
            ],
        )
    )
    result = engine.evaluate_row(draft, {"metadata": metadata, "tags": tags})
    assert result["error"] is None
    assert result["matched"] is True
    assert result["assign"]["output_metadata"]["value"] == metadata
    assert result["assign"]["output_tags"]["value"] == tags


def test_full_audit_uses_production_trace_and_override_contract():
    """Full audit exposes matched conditions, provenance, overrides, and identity."""
    draft = ruleset(
        rule(
            "first",
            10,
            [condition("condition:first", field("x"), "eq", literal(1, "integer"))],
            [assignment("assignment:first:status", "status", literal("first"))],
        ),
        rule(
            "second",
            20,
            [condition("condition:second", field("x"), "eq", literal(1, "integer"))],
            [assignment("assignment:second:status", "status", literal("second"))],
        ),
    )
    result = engine.evaluate_row(draft, {"x": 1}, full_audit=True)
    assert result["error"] is None
    assert [item["rule_id"] for item in result["matched_rules"]] == ["first", "second"]
    assert result["matched_rules"][0]["conditions"][0]["passed"] is True
    assert result["assignment_results"][0]["effective"] is False
    assert result["assignment_results"][0]["overridden_by_rule_id"] == "second"
    assert result["assignment_results"][1]["effective"] is True
    assert result["ruleset"]["id"] == "studio_test"
    assert result["ruleset"]["content_hash"]
    assert result["engine_version"]


def test_row_errors_are_captured_without_inventing_results():
    """The studio may capture production errors but must not claim a match."""
    draft = ruleset(
        rule(
            "bad_conversion",
            10,
            [condition("condition:bad", field("enabled"), "eq", literal(True))],
            [
                assignment(
                    "assignment:bad:value",
                    "value",
                    Operand(
                        kind="custom_function",
                        function="to_integer",
                        args={"value": field("text")},
                    ),
                )
            ],
        )
    )
    result = engine.evaluate_row(draft, {"enabled": True, "text": "not-an-integer"})
    assert result["error"]
    assert result["matched"] is False
    assert result["matched_rule_ids"] == []
    assert result["assign"] == {}


def test_python_modules_use_rules_engine_style_module_docstrings():
    """Every Python module must start with a concise descriptive docstring."""
    root = Path(__file__).parents[1]
    for path in [root / "app.py", *sorted((root / "studio").rglob("*.py"))]:
        module = ast.parse(path.read_text(encoding="utf-8"))
        docstring = ast.get_docstring(module, clean=False)
        assert docstring, f"Missing module docstring: {path}"
        assert not docstring.lstrip().startswith(("One-line", "Preview evaluator")), path
