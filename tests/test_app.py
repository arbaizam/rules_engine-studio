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

    fallback_rule = next(button for button in app.button if button.label.startswith("30"))
    fallback_rule.click()
    app.run()

    assert not app.exception
    function = next(selectbox for selectbox in app.selectbox if selectbox.value == "concat_ws")
    assert len(function.options) == 58
    assert "decimal_safe_divide" in function.options
    assert "last_business_day_of_month" in function.options
    assert len(app.get("file_uploader")) == 2
