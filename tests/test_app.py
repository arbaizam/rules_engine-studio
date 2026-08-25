"""
Streamlit render tests for Rules Engine Studio.

These checks keep the production-backed controls visible at the application
boundary without requiring a browser or network connection.
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from studio.schema import Condition, ConditionGroup


def test_app_renders_all_function_contracts_and_upload_controls():
    """The rendered app exposes every function and both data/YAML uploaders."""
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=15).run()
    assert not app.exception
    sorter = next(expander for expander in app.expander if expander.label == "Drag to reorder")
    assert sorter.proto.expanded is True
    assert any(
        caption.value == "Drag rules into order · Up/Down remains available"
        for caption in sorter.caption
    )

    eligibility_rule = next(button for button in app.button if button.label.startswith("10"))
    eligibility_rule.click()
    app.run()

    assert not app.exception
    function = next(selectbox for selectbox in app.selectbox if selectbox.value == "coalesce")
    assert len(function.options) == 58
    assert "decimal_safe_divide" in function.options
    assert "last_business_day_of_month" in function.options
    assert len(app.get("file_uploader")) == 2


def test_app_renders_nested_literal_audit_and_hierarchy_controls():
    """The rendered authoring surface exposes structured literals and full audit."""
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=15).run()
    next(button for button in app.button if button.label.startswith("20")).click()
    app.run()

    assert not app.exception
    literal_types = {
        selectbox.value for selectbox in app.selectbox if selectbox.label == "Literal type"
    }
    assert {"array", "struct"} <= literal_types
    assert {area.label for area in app.text_area} >= {"JSON array", "JSON object"}
    assert (
        next(radio for radio in app.radio if radio.label == "Result detail").value == "Full audit"
    )
    assert any(markdown.value == "#### Full audit" for markdown in app.markdown)

    next(button for button in app.button if button.label.startswith("30")).click()
    app.run()
    assert any("Nested group" in markdown.value for markdown in app.markdown)


def test_root_group_renders_direct_tests_before_nested_groups():
    """Root-level tests render before child groups without changing ownership."""
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=15).run()
    next(button for button in app.button if button.label.startswith("30")).click()
    app.run()

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
    next(button for button in app.button if button.label.startswith("10")).click()
    app.run()

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
