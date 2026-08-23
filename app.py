"""
Rules Engine Studio application entry point.

The application authors canonical ruleset metadata, evaluates uploaded rows
with the production row runtime, and exports compiler-validated YAML.
"""

from __future__ import annotations

import streamlit as st

from studio import state, yaml_io
from studio.ui import data, evaluate, rules, yaml_tab

st.set_page_config(
    page_title="Rules Engine Studio",
    page_icon=":material/rule:",
    layout="wide",
    initial_sidebar_state="expanded",
)

state.init()


def sidebar() -> None:
    """Render ruleset metadata, navigation, and validation status."""
    ruleset = state.draft()

    with st.sidebar:
        st.markdown("### Rules Engine Studio")
        st.caption("Draft · test · export")

        with st.expander("Ruleset details", expanded=False):
            ruleset.ruleset_id = st.text_input("Ruleset id", value=ruleset.ruleset_id)
            ruleset.ruleset_name = st.text_input(
                "Ruleset name", value=ruleset.ruleset_name
            )
            ruleset.version = st.text_input("Version", value=ruleset.version)
            ruleset.description = st.text_area(
                "Description", value=ruleset.description, height=70
            )
            ruleset.owner = st.text_input("Owner", value=ruleset.owner)
            ruleset.owner_department = st.text_input(
                "Owner department", value=ruleset.owner_department
            )
            st.caption(
                "Owner and owner department are required by the production validator."
            )

        st.divider()
        st.markdown("**Rules**")
        ordered = ruleset.ordered_rules()

        if not ordered:
            st.caption("None yet.")
        for rule in ordered:
            selected = rule.uid == st.session_state.get(state.SELECTED)
            label = f"{rule.rule_order} · {rule.rule_id or 'untitled'}"
            if not rule.active_flag:
                label += "  (off)"
            if rule.stop_on_match:
                label += "  ⏹"
            if st.button(
                label,
                key=f"pick-{rule.uid}",
                width="stretch",
                type="primary" if selected else "secondary",
            ):
                state.select_rule(rule.uid)
                st.rerun()

        add = st.columns(2)
        if add[0].button("Add rule", width="stretch"):
            state.queue(state.add_rule)
        current = state.selected_rule()
        if add[1].button("Duplicate", width="stretch", disabled=current is None):
            state.queue(lambda uid=current.uid: state.duplicate_rule(uid))

        move = st.columns(3)
        if move[0].button("Up", width="stretch", disabled=current is None):
            state.queue(lambda uid=current.uid: state.move_rule(uid, -1))
        if move[1].button("Down", width="stretch", disabled=current is None):
            state.queue(lambda uid=current.uid: state.move_rule(uid, 1))
        if move[2].button("Delete", width="stretch", disabled=current is None):
            state.queue(lambda uid=current.uid: state.delete_rule(uid))

        st.divider()
        st.markdown("**Output**")
        st.session_state[state.PREFIX] = st.text_input(
            "Column prefix", value=st.session_state[state.PREFIX]
        )
        issues = yaml_io.validate(ruleset, state.columns())
        errors = sum(1 for i in issues if i.severity == "error")
        if errors:
            st.error(f"{errors} to fix before export")
        else:
            st.success("Ready to export")


sidebar()

tab_rules, tab_data, tab_eval, tab_yaml = st.tabs(
    ["Rules", "Sample data", "Evaluate", "YAML"]
)

with tab_rules:
    rules.render()
with tab_data:
    data.render()
with tab_eval:
    evaluate.render()
with tab_yaml:
    yaml_tab.render()

# Structural edits queued during render are applied here, then the page redraws.
if state.flush():
    st.rerun()
