"""Regression checks for canonical function and lossless literal authoring."""

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from streamlit.testing.v1 import AppTest

from studio import custom_functions, state
from studio import type_compatibility as types
from studio.schema import Assignment, Condition, Operand, Rule, Ruleset
from studio.ui import rules, widgets


def test_ordered_function_contracts_keep_authored_operands():
    """Refactored coalesce lists stay ordered and editable during rendering."""
    for function in ("coalesce", "concat_ws", "array_join"):
        contract = custom_functions.spec(function)
        assert next(arg for arg in contract["arguments"] if arg["name"] == "values")[
            "type_hint"
        ] == "ordered_sequence"
    assert types.allowed_types_for_hint("ordered_sequence") == frozenset({types.SEQUENCE})
    app = AppTest.from_string('''
import streamlit as st
from studio.schema import Operand
from studio.ui.widgets import operand_editor
from studio.type_compatibility import NUMERIC_TYPES
if "operand" not in st.session_state:
    st.session_state.operand = Operand(kind="custom_function", function="coalesce", args={
        "values": [Operand(kind="field", field_name="amount"),
                   Operand(kind="literal", value=0, value_type="integer")]})
operand_editor(st.session_state.operand, "test", ["amount"],
               in_assignment=True, allowed_types=NUMERIC_TYPES)
''').run()
    assert not app.exception
    operand = app.session_state.operand
    assert isinstance(operand.args["values"], list)
    assert operand.args["values"][0].field_name == "amount"
    assert operand.args["values"][1].value == 0
    next(button for button in app.button if button.key == "test-arg-values-down-0").click()
    app.run()
    assert not app.exception
    assert app.session_state.operand.args["values"][1].field_name == "amount"


def test_integer_editor_preserves_signed_long_precision():
    """Browser controls must never round long literals through floating point."""
    app = AppTest.from_string('''
import streamlit as st
from studio.schema import Operand
from studio.ui.widgets import operand_editor
if "operand" not in st.session_state:
    st.session_state.operand = Operand(kind="literal", value=9223372036854775807,
                                       value_type="integer")
operand_editor(st.session_state.operand, "integer", [])
''').run()
    assert not app.exception
    assert app.session_state.operand.value == 9223372036854775807
    next(value for value in app.text_input if value.key == "integer-value").set_value(
        "-9223372036854775808"
    )
    app.run()
    assert not app.exception
    assert app.session_state.operand.value == -9223372036854775808


def test_unchanged_literals_preserve_optional_hints_and_typed_collections(monkeypatch):
    """Merely opening an imported literal cannot add a hint or stringify its data."""
    monkeypatch.setattr(widgets.st, "session_state", {})
    monkeypatch.setattr(widgets.st, "selectbox", lambda _label, options, index=0, **_: options[index])
    monkeypatch.setattr(widgets.st, "text_input", lambda _label, value, **_: value)
    monkeypatch.setattr(widgets.st, "text_area", lambda _label, value, **_: value)
    scalar = Operand(kind="literal", value=Decimal("123456789.000000000001"), value_type=None)
    widgets._literal_editor(scalar, "scalar", allowed_types=None)
    assert scalar.value_type is None
    assert scalar.value == Decimal("123456789.000000000001")
    values = [Decimal("1.000000000000000001"), Decimal("2.5")]
    typed = Operand(kind="literal", value=values, value_type="decimal")
    widgets._literal_editor(typed, "array", allowed_types=None)
    assert typed.value_type == "decimal"
    assert typed.value is values
    assert types.profile_for_operand(typed, {}).kind == types.SEQUENCE


def test_collection_json_roundtrip_preserves_extended_types(monkeypatch):
    """Collection editing preserves exact decimals and canonical temporal data."""
    session = {}
    monkeypatch.setattr(widgets.st, "session_state", session)
    original = {"amount": Decimal("1.00000000000000000001"), "date": date(2026, 9, 4),
                "tuple": (1, 2), "set": {"a", "b"}, "double": 1.5}
    monkeypatch.setattr(widgets.st, "text_area", lambda _label, value, **_: value + " ")
    parsed = widgets._json_literal_input(original, dict, "json", "JSON object")
    assert parsed == original
    assert isinstance(parsed["double"], float)
    assert isinstance(parsed["amount"], Decimal)
    monkeypatch.setattr(widgets.st, "text_area", lambda *_, **__: "[0.000000000000000000001]")
    assert widgets._json_literal_input([], list, "array", "JSON array") == [Decimal("1e-21")]


def test_collection_parse_errors_block_until_corrected_or_removed(monkeypatch):
    """A stale valid model must not pass checks while its JSON control is invalid."""
    session = {}
    monkeypatch.setattr(widgets.st, "session_state", session)
    monkeypatch.setattr(widgets.st, "error", lambda *_: None)
    monkeypatch.setattr(widgets.st, "text_area", lambda *_, **__: "[NaN]")
    with widgets.editor_pass("rule"):
        widgets._json_literal_input([1], list, "bad-array", "JSON array")
    assert "bad-array" in session["studio_editor_errors"]
    with widgets.editor_pass("rule"):
        pass
    assert session["studio_editor_errors"] == {}


def test_assignment_profiles_exclude_inactive_and_same_rule_producers():
    """The GUI offers only assignments committed by earlier active rules."""
    inactive = Rule(rule_id="inactive", rule_order=1, active_flag=False, assignments=[
        Assignment(target_field="inactive_target", value=Operand(value="hidden"))])
    first = Rule(rule_id="first", rule_order=2, assignments=[
        Assignment(target_field="first_target", value=Operand(value=5, value_type="integer")),
        Assignment(target_field="same_rule_read", value=Operand(kind="assigned", assigned_field="first_target")),
    ])
    later = Rule(rule_id="later", rule_order=3)
    profiles = types.assignment_profiles(Ruleset(rules=[inactive, first, later]), {}, before_rule=later)
    assert "inactive_target" not in profiles
    assert profiles["first_target"].kind == types.INTEGER
    assert profiles["same_rule_read"].kind == types.UNKNOWN


def test_timestamp_families_and_common_type_literal_lists():
    """Temporal compatibility respects zones and scalar hints inside collections."""
    aware = datetime(2026, 9, 4, tzinfo=timezone.utc)
    assert types.profile_values([aware]).kind == types.TIMESTAMP
    assert types.profile_values([aware.replace(tzinfo=None)]).kind == types.TIMESTAMP_NTZ
    assert types.allowed_types_for_hint("timestamp") == frozenset({types.TIMESTAMP, types.TIMESTAMP_NTZ})
    values = Operand(value=["1.25", "2.75"], value_type="decimal")
    call = Operand(kind="custom_function", function="coalesce", args={"values": values})
    assert types.profile_for_operand(call, {}).kind == types.NUMBER


def test_unknown_function_renders_without_mutating_imported_arguments():
    """An unregistered imported function remains inspectable and fails validation."""
    app = AppTest.from_string('''
import streamlit as st
from studio.schema import Operand
from studio.ui.widgets import operand_editor
if "operand" not in st.session_state:
    st.session_state.operand = Operand(kind="custom_function", function="unknown", args={"x": 5})
operand_editor(st.session_state.operand, "unknown", [])
''').run()
    assert not app.exception
    assert app.session_state.operand.args == {"x": 5}
    assert any("not registered" in error.value for error in app.error)


def test_condition_controls_normalize_only_on_operator_change():
    """Imported invalid metadata must survive rendering for canonical validation."""
    right = Operand(value=5)
    condition = Condition(operator="is_null", right=right, error_on_null=True, tolerance_abs=Decimal(2))
    rules._normalize_condition_controls(condition, "is_null")
    assert condition.right is right
    assert condition.error_on_null
    assert condition.tolerance_abs == Decimal(2)
    rules._normalize_condition_controls(condition, "eq")
    rules._normalize_condition_controls(condition, "is_null")
    assert condition.right is None
    assert not condition.error_on_null
    assert condition.tolerance_abs == 0


def test_function_render_preserves_raw_arguments_and_explicit_nulls():
    """Opening function controls cannot replace nulls or annotate raw literals."""
    app = AppTest.from_string('''
import streamlit as st
from studio.schema import Operand
from studio.ui.widgets import operand_editor
if "operand" not in st.session_state:
    st.session_state.operand = Operand(kind="custom_function", function="substring",
        args={"value": None, "start": 1})
    st.session_state.coalesce = Operand(kind="custom_function", function="coalesce",
        args={"values": [None, "text"]})
operand_editor(st.session_state.operand, "substring", [])
operand_editor(st.session_state.coalesce, "coalesce", [])
''').run()
    assert not app.exception
    assert app.session_state.operand.args == {"value": None, "start": 1}
    assert app.session_state.coalesce.args == {"values": [None, "text"]}


def test_recursive_function_arguments_and_invalid_numeric_collections_are_editable():
    """Valid nested operands and invalid imported values must not crash rendering."""
    app = AppTest.from_string('''
import streamlit as st
from studio.schema import Operand
from studio.ui.widgets import operand_editor
if "operand" not in st.session_state:
    nested = Operand(kind="field", field_name="amount")
    st.session_state.operand = Operand(kind="custom_function", function="coalesce",
        args={"values": [{"value": nested}, [nested]]})
    st.session_state.invalid = Operand(value={"value": float("nan")}, value_type=None)
operand_editor(st.session_state.operand, "nested", ["amount"])
operand_editor(st.session_state.invalid, "invalid", [])
''').run()
    assert not app.exception
    assert app.session_state.operand.args["values"][0]["value"].field_name == "amount"
    assert app.session_state.operand.args["values"][1][0].field_name == "amount"
    assert app.session_state["studio_editor_errors"]


def test_invalid_json_survives_tab_navigation_and_blocks_export_and_evaluation():
    """Invalid JSON stays visible and blocking until the author repairs it."""
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=15).run()
    assert not app.exception
    rule = next(rule for rule in app.session_state[state.DRAFT].rules
                if rule.uid == app.session_state[state.SELECTED])
    condition = next(rule.conditions.walk_conditions())
    prefix = f"cr-{condition.uid}"
    next(box for box in app.selectbox if box.key == f"cop-{condition.uid}").select("eq")
    app.run()
    next(box for box in app.selectbox if box.key == f"{prefix}-vtype").select("array")
    app.run()
    text_key = f"{prefix}-value-array"
    next(area for area in app.text_area if area.key == text_key).set_value("[")
    app.run()
    assert not app.exception
    assert text_key in app.session_state["studio_editor_errors"]

    app.session_state["studio_tab"] = "YAML"
    app.run()
    assert not app.exception
    assert app.get("download_button")[0].proto.disabled
    app.session_state["studio_tab"] = "Evaluate"
    app.run()
    assert not app.exception
    assert any("invalid editor values" in error.value for error in app.error)

    app.session_state["studio_tab"] = "Rules"
    app.run()
    assert not app.exception
    area = next(area for area in app.text_area if area.key == text_key)
    assert area.value == "["
    assert text_key in app.session_state["studio_editor_errors"]
    area.set_value("[1,2]")
    app.run()
    assert not app.exception
    assert not app.session_state["studio_editor_errors"]
    app.session_state["studio_tab"] = "YAML"
    app.run()
    assert not app.exception
    assert not app.get("download_button")[0].proto.disabled
