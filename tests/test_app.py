"""
Streamlit render tests for Rules Engine Studio.

These checks keep the production-backed controls visible at the application
boundary without requiring a browser or network connection.
"""

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from rules_engine.spark_runtime import (
    ASSIGNMENT_RESULT_STRUCT,
    CONDITION_TRACE_STRUCT,
    MATCHED_RULE_TRACE_STRUCT,
    OPERAND_TRACE_STRUCT,
)
from studio import sample_data, state, yaml_io
from studio.schema import Condition, ConditionGroup
from studio.ui import yaml_preview
from studio.ui.evaluate import _operand_struct_rows, _struct_rows

YAML_PREVIEW_OPEN = yaml_preview.OPEN


def select_rule(app: AppTest, rule_order: int) -> None:
    """Select a draft rule without depending on the browser-only component."""
    rule = next(rule for rule in app.session_state[state.DRAFT].rules if rule.rule_order == rule_order)
    app.session_state[state.SELECTED] = rule.uid
    app.run()


def open_tab(app: AppTest, label: str) -> None:
    """Select one tracked tab and run only that view."""
    app.session_state["studio_tab"] = label
    app.run()


def test_app_renders_function_contracts_and_lazy_upload_views():
    """Each tracked tab exposes its own controls without rendering hidden views."""
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=15).run()
    assert not app.exception
    reorder = next(expander for expander in app.expander if expander.label == "Reorder rules")
    assert reorder.proto.expanded is True
    assert any(button.label == "Move down" for button in reorder.button)
    assert not any(" · " in button.label and button.label[:1].isdigit() for button in app.button)

    assert not app.exception
    function = next(selectbox for selectbox in app.selectbox if selectbox.value == "coalesce")
    assert len(function.options) < 58
    assert "decimal_safe_divide" in function.options
    assert "upper" not in function.options
    assert not app.get("file_uploader")
    assert not app.radio

    open_tab(app, "Sample data")
    assert [uploader.label for uploader in app.get("file_uploader")] == [
        "CSV, TSV, JSON or Parquet"
    ]
    assert not app.radio

    open_tab(app, "Evaluate")
    assert not app.get("file_uploader")
    assert next(radio for radio in app.radio if radio.label == "Result detail").value == (
        "Full audit"
    )

    open_tab(app, "YAML")
    assert [uploader.label for uploader in app.get("file_uploader")] == ["YAML file"]
    assert not app.radio


def test_live_yaml_preview_follows_rule_edits_and_collapses_to_a_status_rail():
    """The right preview stays live and preserves its session-level display preference."""
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=15).run()

    assert not app.exception
    assert app.session_state[YAML_PREVIEW_OPEN] is True
    assert "ruleset_id:" in app.code[0].value
    assert any("Canonical YAML · Live" in markdown.value for markdown in app.markdown)

    rule_id = next(field for field in app.text_input if field.label == "Rule id")
    rule_id.set_value("live_yaml_rule")
    app.run()

    assert not app.exception
    assert "rule_id: live_yaml_rule" in app.code[0].value

    next(button for button in app.button if button.key == "yaml_preview_close_button").click()
    app.run()

    assert not app.exception
    assert app.session_state[YAML_PREVIEW_OPEN] is False
    assert not app.code
    assert any(button.key == "yaml_preview_open_button" for button in app.button)


def test_live_yaml_preview_remains_visible_while_the_draft_is_invalid():
    """A transient compiler error must not blank the adjacent source preview."""
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=15).run()
    rule_id = next(field for field in app.text_input if field.label == "Rule id")
    rule_id.set_value("")
    app.run()

    assert not app.exception
    assert app.code
    assert "rule_id: ''" in app.code[0].value
    assert any("Not exportable" in markdown.value for markdown in app.markdown)


def test_yaml_preview_scroll_anchor_follows_the_selected_ordered_rule():
    """Rule synchronization must target the selected rule's exported YAML block."""
    draft = sample_data.demo_ruleset()
    selected = draft.ordered_rules()[-1]
    selected.rule_order = 500
    document = yaml_io.to_yaml(draft)

    line_number = yaml_preview._selected_rule_line(document, draft, selected.uid)
    anchored_line = document.splitlines()[line_number - 1]

    assert anchored_line.lstrip().startswith("- rule_id:")
    assert selected.rule_id in anchored_line
    assert "scroller.scrollTop =" in yaml_preview._SCROLLER_DEFINITION["js"]
    assert "scroller.clientHeight * 0.16" in yaml_preview._SCROLLER_DEFINITION["js"]


def test_native_rule_reorder_preserves_the_project_and_sample_rows():
    """Reordering must not restore either demo rules or demo sample data."""
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=15).run()
    ruleset_id = next(field for field in app.text_input if field.label == "Ruleset id")
    ruleset_id.set_value("reorder_regression")
    app.run()

    app.session_state["sample_frame"] = pd.DataFrame([{"marker": "custom-row"}])
    first_rule = app.session_state["draft_ruleset"].ordered_rules()[0]
    next(button for button in app.button if button.key == f"reorder-down-{first_rule.uid}").click()
    app.run()

    assert not app.exception
    assert app.session_state["draft_ruleset"].ruleset_id == "reorder_regression"
    assert app.session_state["sample_frame"].to_dict("records") == [{"marker": "custom-row"}]
    assert app.session_state["draft_ruleset"].ordered_rules()[1].uid == first_rule.uid
    assert next(metric for metric in app.metric if metric.label == "Runs at").value == "20"

    app.run()
    assert app.session_state["draft_ruleset"].ordered_rules()[1].uid == first_rule.uid
    assert next(metric for metric in app.metric if metric.label == "Runs at").value == "20"


def test_app_renders_nested_literal_audit_and_hierarchy_controls():
    """The rendered authoring surface exposes structured literals and full audit."""
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=15).run()
    select_rule(app, 20)

    assert not app.exception
    literal_types = {
        selectbox.value for selectbox in app.selectbox if selectbox.label == "Literal type"
    }
    assert {"array", "struct"} <= literal_types
    assert {area.label for area in app.text_area} >= {"JSON array", "JSON object"}

    open_tab(app, "Evaluate")
    assert (
        next(radio for radio in app.radio if radio.label == "Result detail").value == "Full audit"
    )
    assert any(markdown.value == "#### Full audit" for markdown in app.markdown)

    open_tab(app, "Rules")
    select_rule(app, 30)
    assert any("Nested group" in markdown.value for markdown in app.markdown)


def test_full_audit_ui_projects_every_production_struct_field():
    """The structured audit view stays complete as the production schemas evolve."""
    for struct in (
        MATCHED_RULE_TRACE_STRUCT,
        CONDITION_TRACE_STRUCT,
        ASSIGNMENT_RESULT_STRUCT,
    ):
        payload = {field.name: f"value:{field.name}" for field in struct.fields}
        rows = _struct_rows(payload, struct)

        assert [row["field"] for row in rows] == struct.fieldNames()
        assert [row["Spark type"] for row in rows] == [
            field.dataType.simpleString() for field in struct.fields
        ]

    left = {field.name: f"left:{field.name}" for field in OPERAND_TRACE_STRUCT.fields}
    right = {field.name: f"right:{field.name}" for field in OPERAND_TRACE_STRUCT.fields}
    operand_rows = _operand_struct_rows(left, right)

    assert [row["field"] for row in operand_rows] == OPERAND_TRACE_STRUCT.fieldNames()
    assert [row["left"] for row in operand_rows] == [
        f"left:{field.name}" for field in OPERAND_TRACE_STRUCT.fields
    ]
    assert [row["right"] for row in operand_rows] == [
        f"right:{field.name}" for field in OPERAND_TRACE_STRUCT.fields
    ]


def test_root_group_renders_direct_tests_before_nested_groups():
    """Root-level tests render before child groups without changing ownership."""
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=15).run()
    select_rule(app, 30)

    rule = next(rule for rule in app.session_state["draft_ruleset"].rules if rule.rule_order == 30)
    root = rule.conditions
    nested = next(child for child in root.children if isinstance(child, ConditionGroup))
    next(button for button in app.button if button.key == f"gaddc-{root.uid}").click()
    app.run()

    rule = next(rule for rule in app.session_state["draft_ruleset"].rules if rule.rule_order == 30)
    root = rule.conditions
    nested = next(child for child in root.children if isinstance(child, ConditionGroup))
    direct = [child for child in root.children if isinstance(child, Condition)]
    text_input_keys = [widget.key for widget in app.text_input]

    assert len(direct) == 2
    assert len(nested.children) == 2
    assert max(text_input_keys.index(f"cid-{condition.uid}") for condition in direct) < (
        text_input_keys.index(f"gid-{nested.uid}")
    )


def test_app_styles_unify_controls_and_separate_root_groups_from_panels():
    """The authoring surface uses one control treatment and offsets root groups."""
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=15).run()
    styles = next(markdown.value for markdown in app.markdown if "<style>" in markdown.value)
    assert "--studio-navy: #003359;" in styles
    assert "--studio-blue: #93B1CC;" in styles
    assert "--studio-lime: #AAAD00;" in styles
    assert "--studio-control-bg: #071E2D;" in styles
    assert "--studio-control-border: #52758F;" in styles
    assert "--studio-control-text: #F8FAFC;" in styles
    assert "--studio-rule: #058AA8;" in styles
    assert "--studio-group: #93B1CC;" in styles
    assert "--studio-condition: #AAAD00;" in styles
    assert "border: 1px solid var(--studio-control-border)" in styles
    assert "background-color: var(--studio-control-bg)" in styles
    assert "-webkit-text-fill-color: var(--studio-control-text)" in styles
    assert '[data-testid="stTextInputRootElement"]' in styles
    assert '[data-testid="stNumberInputContainer"]' in styles
    assert '[data-testid="stTextAreaRootElement"]' in styles
    assert '[data-testid="stSelectbox"]' in styles
    assert '[data-testid="stSelectbox"] > div:last-child' in styles
    assert '[data-testid="stMultiSelect"] > div:last-child' in styles
    assert '[data-testid="stDateInputField"]' in styles
    assert '[data-testid="stTimeInputTimeDisplay"]' in styles
    assert "box-shadow: 0 0 0 1px var(--studio-control-border)" in styles
    assert "--studio-section-border: #52758F;" in styles
    assert "--studio-table-border: #7194AE;" in styles
    assert "border-width: 2px" in styles
    assert '[data-testid="stDataFrame"]' in styles
    assert '[data-testid="stExpander"] > details' in styles
    assert '[data-testid="stTabs"] [role="tablist"]' in styles
    assert '[data-testid="stMainBlockContainer"]' in styles
    assert "padding-left: 1.25rem !important;" in styles
    assert "padding-right: 1.25rem !important;" in styles
    assert "padding-top: 3.5rem !important;" in styles
    assert '[data-testid="stTabs"] [role="tab"] p' in styles
    assert "font-size: 1.25rem !important;" in styles
    assert '[data-testid="stDivider"]' in styles
    assert '[class*="st-key-rule_node_"]' in styles
    assert "padding-left: 1.5rem;" in styles
    assert '[class*="st-key-group_depth_0_"]' in styles
    assert "margin-left: 0;" in styles
    assert ".studio-rule-label {" in styles
    assert "margin-bottom: 1rem;" in styles
    assert '[class*="st-key-expression_"]' in styles
    assert "margin: 0.35rem 0 0.75rem;" in styles
    assert ".studio-expression-preview" not in styles
    assert '[class*="st-key-yaml_preview_panel"]' in styles
    assert '[class*="st-key-yaml_preview_rail"]' in styles
    assert ".studio-yaml-status.ready span" in styles
    assert "height: calc(100vh - 5rem);" in styles
    assert '[data-testid="stLayoutWrapper"]:has(' in styles
    assert "margin-top: 0;" in styles
    assert "top: 4rem;" in styles
    assert "top: calc(50vh - 7rem);" in styles
    assert '[class*="st-key-sidebar_brand"] h2' in styles
    assert "font-size: 1.5rem !important;" in styles
    assert '[class*="st-key-condition-footer-"]' in styles
    assert "white-space: nowrap;" in styles
    assert '[class*="st-key-delete_selected_rule"] button' in styles
    assert "background-color: #9A0000 !important;" in styles
    assert "color: #FFFFFF !important;" in styles

    theme = (Path(__file__).parents[1] / ".streamlit" / "config.toml").read_text(
        encoding="utf-8"
    )
    assert 'primaryColor = "#AAAD00"' in theme
    assert 'secondaryBackgroundColor = "#003359"' in theme


def test_sidebar_rule_labels_do_not_use_a_stop_on_match_glyph():
    """Stop-on-match is edited in the rule form, not shown as a cryptic square."""
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=15).run()

    assert not app.exception
    assert all("⏹" not in button.label for button in app.button)


def test_expression_previews_render_and_follow_condition_edits():
    """Condition, group, and rule previews must render from the live draft model."""
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=15).run()

    assert not app.exception
    labels = [expander.label for expander in app.expander]
    assert any(label.startswith("Rule expression ·") for label in labels)
    assert any(label.startswith("Group expression ·") for label in labels)
    assert any(label.startswith("Condition expression ·") for label in labels)
    assert any(label.startswith("Assignment expression ·") for label in labels)
    assert all(
        expander.proto.expanded is False
        for expander in app.expander
        if " expression ·" in expander.label
    )
    assert all("studio-expression-preview" not in markdown.value for markdown in app.markdown)
    assert any(
        'studio-expression-label">Matches when' in markdown.value
        for markdown in app.markdown
    )

    rule = next(rule for rule in app.session_state["draft_ruleset"].rules if rule.rule_order == 10)
    condition = next(rule.conditions.walk_conditions())
    next(selectbox for selectbox in app.selectbox if selectbox.key == f"cop-{condition.uid}").select(
        "ge"
    )
    app.run()

    assert not app.exception
    assert any(
        "studio-expression-text" in markdown.value and "is at least" in markdown.value
        for markdown in app.markdown
    )


def test_condition_fields_follow_operator_and_sample_value_types():
    """String comparisons must not offer date or numeric input fields."""
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=15).run()
    select_rule(app, 40)
    rule = next(rule for rule in app.session_state[state.DRAFT].rules if rule.rule_order == 40)
    condition = next(rule.conditions.walk_conditions())

    operator = next(
        selectbox for selectbox in app.selectbox if selectbox.key == f"cop-{condition.uid}"
    )
    assert "starts with" in operator.options
    operator.select("starts_with")
    app.run()

    right_kind = next(
        selectbox for selectbox in app.selectbox if selectbox.key == f"cr-{condition.uid}-kind"
    )
    right_kind.select("field")
    app.run()

    right_field = next(
        selectbox for selectbox in app.selectbox if selectbox.key == f"cr-{condition.uid}-field"
    )
    assert any(option.startswith("LoanNo ·") for option in right_field.options)
    assert not any(option.startswith("EffectiveDate ·") for option in right_field.options)
    assert not any(option.startswith("OriginalFICO ·") for option in right_field.options)
