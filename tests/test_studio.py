"""
Contract tests for Rules Engine Studio.

The tests exercise the Streamlit-free integration boundary: mutable authoring
models, canonical compilation and export, production validation, the standard
function registry, row evaluation, and uploaded test data.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from studio import authoring, custom_functions, engine, expressions, sample_data, state, yaml_io
from studio.schema import (
    LITERAL_TYPES,
    LOGIC_MODES,
    OPERAND_KINDS,
    OPERATOR_NAMES,
    OPERATORS_BY_NAME,
    SCALAR_LITERAL_TYPES,
    TOLERANCE_OPERATORS,
    Assignment,
    Condition,
    ConditionGroup,
    Operand,
    Rule,
    Ruleset,
    normalize_literal_editor_type,
    referenced_columns,
)


def field(name: str, *, default: object | None = None) -> Operand:
    """Return a field operand with an optional non-null literal fallback."""
    fallback = None
    if default is not None:
        fallback = Operand(
            kind="literal",
            value=default,
            value_type=normalize_literal_editor_type(None, default),
        )
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


def test_operand_expressions_cover_sources_fallbacks_functions_and_incomplete_fields():
    """Operand previews must explain every authoring source without evaluating it."""
    source = field("CurrentFICO", default=0)
    function = Operand(
        kind="custom_function",
        function="coalesce",
        args={"values": [field("CurrentFICO"), assigned("fico_band"), literal("")]},
    )

    assert expressions.operand_expression(source) == (
        'input field "CurrentFICO" (use 0 when null)'
    )
    assert expressions.operand_expression(function) == (
        'coalesce(values = [input field "CurrentFICO", '
        'prior assignment "fico_band", empty text ("")])'
    )
    assert expressions.operand_expression(Operand(kind="field")) == "[choose an input field]"
    assert expressions.operand_expression(Operand(kind="custom_function")) == (
        "[choose a function]"
    )
    assert expressions.operand_expression(literal("1.20", "decimal")) == "1.20"
    assert expressions.operand_expression(literal("2026-08-25", "date")) == (
        'date "2026-08-25"'
    )
    assert expressions.operand_expression(literal("", "decimal")) == "[enter a number]"


def test_condition_expressions_include_operator_options_and_active_status():
    """Condition previews must surface behavior that changes comparison semantics."""
    draft = Condition(
        left=field("CurrentFICO"),
        operator="ge",
        right=literal(620, "integer"),
        tolerance_abs=Decimal(5),
        error_on_null=True,
        active_flag=False,
    )

    assert expressions.condition_expression(draft) == (
        'Ignored because this condition is inactive: input field "CurrentFICO" '
        "is at least 620 (absolute tolerance 5); raise an error when an operand is null"
    )
    assert expressions.condition_expression(
        Condition(left=field("ReviewStatus"), operator="is_null", right=None)
    ) == 'input field "ReviewStatus" is null'


def test_group_expressions_preserve_nested_all_any_structure():
    """Group previews must make boolean ownership and nesting unambiguous."""
    draft = ConditionGroup(
        logical_operator="all",
        children=[
            Condition(left=field("CurrentFICO"), operator="ge", right=literal(620)),
            ConditionGroup(
                logical_operator="any",
                children=[
                    Condition(left=field("CurrentDSCR"), operator="ge", right=literal(1.2)),
                    Condition(
                        left=field("ManualReview"),
                        operator="eq",
                        right=literal(True),
                        active_flag=False,
                    ),
                ],
            ),
        ],
    )

    assert expressions.group_expression(draft) == "\n".join(
        [
            "All of the following must be true:",
            '  • input field "CurrentFICO" is at least 620',
            "  • Any of the following must be true:",
            '    • input field "CurrentDSCR" is at least 1.2',
            "    • Ignored because this condition is inactive: "
            'input field "ManualReview" equals true',
        ]
    )
    assert expressions.group_expression(ConditionGroup()) == (
        "Always matches because this group has no conditions."
    )


def test_rule_expressions_compose_conditions_assignments_and_match_behavior():
    """Rule previews must summarize the same IF/THEN model exported to the engine."""
    draft = Rule(
        active_flag=False,
        stop_on_match=True,
        conditions=ConditionGroup(
            children=[Condition(left=field("eligible"), operator="eq", right=literal(True))]
        ),
        assignments=[
            Assignment(target_field="ReviewStatus", value=literal("Approved")),
        ],
    )

    assert expressions.rule_expression(draft) == "\n".join(
        [
            "This rule is inactive and will be skipped.",
            "IF",
            "  All of the following must be true:",
            '    • input field "eligible" equals true',
            "THEN",
            '  • Set output field "ReviewStatus" to "Approved".',
            "After a match, stop before evaluating later rules.",
        ]
    )
    assert "[add an assignment]" in expressions.rule_expression(Rule())


def test_dependency_pin_targets_authoring_contract_commit():
    """Deployments must install the engine revision that exposes the manifest."""
    requirements = (Path(__file__).parents[1] / "requirements.txt").read_text(encoding="utf-8")
    assert "@667f80d5fa9e660687268d9752b53fbaced2e8f1" in requirements
    assert authoring.manifest()["manifest_version"] == 1


def test_studio_manifest_uses_the_shared_registry_and_is_cached():
    """One registry must drive authoring metadata, validation, and evaluation."""
    first = authoring.manifest()
    second = authoring.manifest()

    assert first is second
    assert custom_functions.registry() is authoring.registry()
    assert first["functions"] == list(authoring.function_contracts())


def test_operator_catalogue_and_behavior_come_from_manifest():
    """Operator names, arity, operand shape, and tolerance must stay engine-owned."""
    contracts = {
        contract["name"]: contract for contract in authoring.manifest()["comparison_operators"]
    }

    assert OPERATOR_NAMES == list(contracts)
    assert {
        name: (
            specification.arity,
            specification.right_operand_shape,
            specification.supports_tolerance,
        )
        for name, specification in OPERATORS_BY_NAME.items()
    } == {
        name: (
            contract["arity"],
            contract["right_operand_shape"],
            contract["supports_tolerance"],
        )
        for name, contract in contracts.items()
    }
    assert TOLERANCE_OPERATORS == {
        "eq",
        "ne",
        "gt",
        "ge",
        "lt",
        "le",
        "in",
        "not_in",
    }


def test_literal_hints_aliases_operand_kinds_and_logic_come_from_manifest():
    """Editor validity choices must derive from the installed authoring contract."""
    manifest = authoring.manifest()
    literal_contracts = manifest["literal_type_hints"]

    assert OPERAND_KINDS == tuple(manifest["operand_kinds"])
    assert LOGIC_MODES == tuple(manifest["logical_operators"])
    assert SCALAR_LITERAL_TYPES == tuple(contract["name"] for contract in literal_contracts)
    assert LITERAL_TYPES == (*SCALAR_LITERAL_TYPES, "array", "struct", "null")
    for contract in literal_contracts:
        for alias in contract["aliases"]:
            assert normalize_literal_editor_type(alias, None) == contract["name"]

    restored = Operand.from_dict({"literal": 1.0, "value_type": "int"})
    assert restored.value_type == "integer"
    assert restored.to_dict() == {"literal": 1.0, "value_type": "integer"}


def test_manifest_function_hint_vocabularies_and_dynamic_returns_are_consumed():
    """Function metadata must be interpreted from the manifest without copied vocabularies."""
    manifest = authoring.manifest()
    argument_hints = set(authoring.function_argument_type_hints())
    fixed_returns = set(authoring.fixed_function_return_type_hints())
    dynamic_templates = authoring.dynamic_function_return_type_templates()
    dynamic_prefixes = {template.partition(":")[0] for template in dynamic_templates}

    assert argument_hints == set(manifest["function_argument_type_hints"])
    assert fixed_returns == set(manifest["function_return_type_hints"]["fixed"])
    assert dynamic_templates == (
        "same_as:<argument_name>",
        "common_type:<argument_name>",
    )
    assert all(
        argument["type_hint"] in argument_hints
        for function in custom_functions.specs()
        for argument in function["arguments"]
    )
    assert all(
        return_hint in fixed_returns or return_hint.partition(":")[0] in dynamic_prefixes
        for function in custom_functions.specs()
        if (return_hint := function["return_type_hint"]) is not None
    )
    assert custom_functions.spec("coalesce")["return_type_hint"] == "common_type:values"


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
    assert {kind.value for kind in kinds} == set(OPERAND_KINDS)


def test_all_standard_function_specs_and_implementations_are_registered():
    """The studio registry must incorporate every engine standard function."""
    expected = sorted(
        specification["function_name"]
        for specification in authoring.function_contracts()
        if specification["active_flag"]
    )
    assert custom_functions.names() == expected
    assert len(expected) == 58
    for function_name in expected:
        assert custom_functions.registry().get_spec(function_name).function_name == function_name
        assert callable(custom_functions.registry().get_implementation(function_name))


def test_compiler_literal_type_errors_reach_studio_validation():
    """The Studio must surface strengthened compiler errors without recreating them."""
    draft = ruleset(
        rule(
            "bad_string",
            10,
            [condition("condition:bad_string", field("x"), "eq", literal(1, "string"))],
            [assignment("assignment:bad_string:value", "value", literal("A"))],
        )
    )

    issues = yaml_io.validate(draft)

    assert len(issues) == 1
    assert issues[0].check_name == "RULESET_COMPILATION_FAILED"
    assert "String literal must be a string" in issues[0].message


def test_compile_only_studio_modules_do_not_import_pyspark():
    """Manifest, compilation, and semantic validation must remain Spark-free imports."""
    root = Path(__file__).parents[1]
    script = """
import sys
from studio import authoring, custom_functions, schema, yaml_io
authoring.manifest()
assert custom_functions.names()
assert schema.OPERATOR_NAMES
assert not any(name == 'pyspark' or name.startswith('pyspark.') for name in sys.modules)
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(root), environment.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


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
