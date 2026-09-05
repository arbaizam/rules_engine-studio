"""Regression coverage for the refactored engine's authoring and persistence contract."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pandas as pd
import pytest
import streamlit as st

from rules_engine.exporter_yaml import YamlRulesetExporter
from studio import authoring, sample_data, state, yaml_io
from studio.schema import Assignment, Operand, Ruleset, infer_literal_type
from studio.ui import browser_state, yaml_preview


def _draft_with_literal(value, value_type=None):
    draft = sample_data.demo_ruleset()
    draft.rules = draft.rules[:1]
    draft.rules[0].assignments = [Assignment("result", Operand(value=value, value_type=value_type))]
    return draft


def _typed_value(value):
    """Compare exact recursive types as well as equality (Decimal equals some floats)."""
    if isinstance(value, dict):
        return (dict, {key: _typed_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return (type(value), [_typed_value(item) for item in value])
    if isinstance(value, set):
        return (set, sorted((_typed_value(item) for item in value), key=repr))
    return type(value), value


@pytest.mark.parametrize(
    ("value", "hint"),
    [
        (None, None),
        (2**63 + 1, None),
        (Decimal("12345678901234567890.12345678901234567890"), None),
        (1.25, "double"),
        (date(2026, 9, 4), None),
        (datetime(2026, 9, 4, 8, 30), None),  # noqa: DTZ001 - canonical timestamp_ntz
        (datetime(2026, 9, 4, 8, 30, tzinfo=timezone.utc), None),
        ((Decimal("1.1"), date(2026, 9, 4)), None),
        ({Decimal("1.1"), Decimal("2.2")}, None),
        ([Decimal("1.10"), Decimal("2.20")], "decimal"),
        ({"prices": [Decimal("1.12345678901234567890")]}, None),
        (3, "long"),
    ],
)
def test_canonical_yaml_round_trip_preserves_value_types_and_hints(value, hint):
    original = authoring.compile_payload(_draft_with_literal(value, hint).to_dict())
    imported = yaml_io.from_yaml(YamlRulesetExporter().export_text(original))
    reopened = authoring.compile_payload(imported.to_dict())
    before = original.rules[0].assignments[0].value
    after = reopened.rules[0].assignments[0].value
    assert after.value_type == before.value_type
    assert _typed_value(after.value) == _typed_value(before.value)
    assert YamlRulesetExporter().export_text(reopened) == YamlRulesetExporter().export_text(
        original
    )


def test_optional_metadata_and_literal_fallbacks_survive_import_exactly():
    draft = _draft_with_literal(None)
    draft.description = ""
    draft.rules[0].description = ""
    operand = draft.rules[0].assignments[0].value
    operand.default_if_null = Operand(value=date(2026, 9, 4), value_type=None)
    document = yaml_io.to_yaml(draft)
    assert yaml_io.to_yaml(yaml_io.from_yaml(document)) == document


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (date(2026, 9, 4), "date"),
        (datetime(2026, 9, 4), "timestamp_ntz"),  # noqa: DTZ001 - explicit naive type
        (datetime(2026, 9, 4, tzinfo=timezone.utc), "timestamp"),
        (1.25, "double"),
        (Decimal("1.25"), "decimal"),
    ],
)
def test_editor_inference_is_separate_from_persisted_type_hint(value, expected):
    operand = Operand.from_dict({"literal": value})
    assert infer_literal_type(operand.value) == expected
    assert operand.value_type is None
    assert operand.to_dict() == {"literal": value}


def test_loading_a_draft_preserves_invalid_metadata_for_engine_diagnostics(monkeypatch):
    draft = sample_data.demo_ruleset()
    draft.rules[1].rule_order = draft.rules[0].rule_order
    condition = next(draft.rules[0].conditions.walk_conditions())
    condition.operator = "is_null"
    condition.error_on_null = True
    condition.tolerance_abs = Decimal("0.5")
    assert condition.right is not None
    monkeypatch.setattr(st, "session_state", {})
    state.set_draft(draft)
    checks = {issue.check_name for issue in yaml_io.validate(state.draft())}
    assert "UNARY_OPERATOR_RIGHT_FORBIDDEN" in checks
    assert "ERROR_ON_NULL_UNARY_FORBIDDEN" in checks
    assert "TOLERANCE_OPERATOR_FORBIDDEN" in checks
    assert draft.rules[1].rule_order == draft.rules[0].rule_order
    assert condition.tolerance_abs == Decimal("0.5")


def test_cached_preview_does_not_repair_empty_required_fields():
    draft = sample_data.demo_ruleset()
    draft.ruleset_id = ""
    snapshot = yaml_preview._cached_snapshot(draft, ())
    assert not snapshot.compiled
    assert not snapshot.exportable
    assert "ruleset_id: ''" in snapshot.document
    assert "ruleset_id must be a non-empty string" in snapshot.issues[0].message


def test_draft_yaml_preserves_exact_literals_when_compilation_is_blocked():
    value = {"price": Decimal("123456789.123456789"), "ids": (1, 2), "tags": {"a", "b"}}
    draft = _draft_with_literal(value)
    draft.ruleset_id = ""
    snapshot = yaml_io.build_snapshot(draft)
    assert not snapshot.exportable
    repaired = snapshot.document.replace("ruleset_id: ''", "ruleset_id: repaired", 1)
    compiled = authoring.compile_text(repaired)
    restored = compiled.rules[0].assignments[0].value.value
    assert _typed_value(restored) == _typed_value(value)


def test_strict_draft_conversion_never_discards_unknown_keys_or_invalid_flags():
    payload = sample_data.demo_ruleset().to_dict()
    payload["unexpected"] = "would have been lost"
    with pytest.raises(ValueError, match="unsupported keys"):
        Ruleset.from_dict(payload)
    del payload["unexpected"]
    payload["rules"][0]["active_flag"] = "false"
    restored = Ruleset.from_dict(payload)
    assert restored.rules[0].active_flag == "false"
    snapshot = yaml_io.build_snapshot(restored)
    assert not snapshot.compiled
    assert "active_flag must be a boolean" in snapshot.issues[0].message
    payload["rules"].append("not a rule")
    with pytest.raises(ValueError, match="must be a mapping"):
        Ruleset.from_dict(payload)


def test_argument_mapping_key_collisions_reach_the_engine_without_data_loss():
    operand = Operand(kind="custom_function", function="abs", args={1: "a", "1": "b"})
    draft = _draft_with_literal(None)
    draft.rules[0].assignments[0].value = operand
    assert len(operand.to_dict()["custom_function"]["args"]) == 2
    assert "both normalize" in yaml_io.build_snapshot(draft).issues[0].message


def test_browser_recovery_preserves_containers_reserved_maps_precision_and_selection(monkeypatch):
    value = {
        "tuple": (Decimal("1.12345678901234567890"), date(2026, 9, 4)),
        "set": {"a", "b"},
        "float": 1.25,
        "old_tag_collision": {"__studio_type__": "date", "value": "literal text"},
        "tag_collision": {"$rules_engine_type": "date", "value": "literal text"},
    }
    draft = _draft_with_literal(value)
    second = draft.rules[0].copy()
    second.rule_order += 10
    draft.rules.append(second)
    draft.ruleset_id = ""
    session = {
        state.DRAFT: draft,
        state.SAMPLE: pd.DataFrame([{"large": 2**63 - 1}, {"large": None}], dtype=object),
        state.SELECTED: second.uid,
        state.PREFIX: "",
    }
    monkeypatch.setattr(st, "session_state", session)
    encoded = browser_state.snapshot_json()
    browser_state.restore_json(encoded)
    restored = state.draft()
    assert restored.ruleset_id == ""
    assert state.selected_rule() is restored.rules[1]
    assert session[state.PREFIX] == ""
    assert _typed_value(restored.rules[0].assignments[0].value.value) == _typed_value(value)
    assert type(state.rows()[0]["large"]) is int
    assert state.rows()[0]["large"] == 2**63 - 1
    assert state.rows()[1]["large"] is None
    assert session["sample_editor_revision"] == 1


def test_invalid_browser_rows_do_not_replace_either_live_draft_or_frame(monkeypatch):
    draft = sample_data.demo_ruleset()
    frame = sample_data.demo_frame()
    monkeypatch.setattr(st, "session_state", {state.DRAFT: draft, state.SAMPLE: frame})
    payload = json.loads(browser_state.snapshot_json())
    payload["sample"]["rows"] = [42]
    with pytest.raises(ValueError, match="sample data is invalid"):
        browser_state.restore_json(json.dumps(payload))
    assert state.draft() is draft
    assert state.frame() is frame


def test_invalid_editor_input_blocks_live_export_and_stale_browser_autosave(monkeypatch):
    draft = sample_data.demo_ruleset()
    session = {
        state.DRAFT: draft,
        state.SAMPLE: sample_data.demo_frame(),
        state.EDITOR_ERRORS: {"bad-json": "JSON literal is incomplete."},
    }
    monkeypatch.setattr(st, "session_state", session)
    snapshot = yaml_preview.current_snapshot()
    assert not snapshot.exportable
    assert any(issue.check_name == "INPUT_PARSE_FAILED" for issue in snapshot.issues)
    with pytest.raises(ValueError, match="paused"):
        browser_state.snapshot_json()
    state.set_draft(draft)
    assert state.editor_errors() == {}
