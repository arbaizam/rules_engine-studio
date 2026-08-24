"""
Streamlit render tests for Rules Engine Studio.

These checks keep the production-backed controls visible at the application
boundary without requiring a browser or network connection.
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_app_renders_all_function_contracts_and_upload_controls():
    """The rendered app exposes every function and both data/YAML uploaders."""
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=15).run()
    assert not app.exception

    loaded_rule = next(button for button in app.button if button.label.startswith("10"))
    loaded_rule.click()
    app.run()

    assert not app.exception
    function = next(selectbox for selectbox in app.selectbox if selectbox.value == "concat_ws")
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


def test_app_styles_separate_root_groups_and_inputs_from_panels():
    """The authoring surface keeps root groups offset and input borders visible."""
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=15).run()
    styles = next(markdown.value for markdown in app.markdown if "<style>" in markdown.value)
    assert "--studio-input: #3A4B66;" in styles
    assert "--studio-input-border: #B7C4D8;" in styles
    assert "--studio-rule-input: #263449;" in styles
    assert "--studio-rule-input-border: #94A3B8;" in styles
    assert "--studio-rule-input-text: #F8FAFC;" in styles
    assert "border: 2px solid var(--studio-input-border)" in styles
    assert "border: 1px solid var(--studio-rule-input-border)" in styles
    assert "background-color: var(--studio-rule-input)" in styles
    assert "-webkit-text-fill-color: var(--studio-rule-input-text)" in styles
    assert '[data-testid="stSelectbox"]' in styles
    assert '[data-baseweb="select"] {' in styles
    assert "box-shadow: 0 0 0 1px var(--studio-rule-input-border)" in styles
    assert '[class*="st-key-rule_node_"]' in styles
    assert "padding-left: 1.5rem;" in styles
    assert '[class*="st-key-group_depth_0_"]' in styles
    assert "margin-left: 0;" in styles
    assert ".studio-rule-label {" in styles
    assert "margin-bottom: 1rem;" in styles
