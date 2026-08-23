"""Rules Engine Studio — draft rules, test them on real rows, export the YAML.

Run locally:   streamlit run app.py
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
    ruleset = state.draft()

    with st.sidebar:
        st.markdown("### Rules Engine Studio")
        st.caption("Draft · test · export")

        with st.expander("Ruleset details", expanded=False):
            ruleset.ruleset_id = st.text_input("Ruleset id", value=ruleset.ruleset_id)
            ruleset.version = st.text_input("Version", value=ruleset.version)
            ruleset.description = st.text_area(
                "Description", value=ruleset.description, height=70
            )
            ruleset.published_by = st.text_input("Published by", value=ruleset.published_by)
            ruleset.published_at = st.text_input(
                "Published at", value=ruleset.published_at, placeholder="2026-08-23"
            )
            st.caption(
                "Published by and published at travel with the file but are excluded "
                "from the engine's content hash."
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
                use_container_width=True,
                type="primary" if selected else "secondary",
            ):
                state.select_rule(rule.uid)
                st.rerun()

        add = st.columns(2)
        if add[0].button("Add rule", use_container_width=True):
            state.queue(state.add_rule)
        current = state.selected_rule()
        if add[1].button("Duplicate", use_container_width=True, disabled=current is None):
            state.queue(lambda uid=current.uid: state.duplicate_rule(uid))

        move = st.columns(3)
        if move[0].button("Up", use_container_width=True, disabled=current is None):
            state.queue(lambda uid=current.uid: state.move_rule(uid, -1))
        if move[1].button("Down", use_container_width=True, disabled=current is None):
            state.queue(lambda uid=current.uid: state.move_rule(uid, 1))
        if move[2].button("Delete", use_container_width=True, disabled=current is None):
            state.queue(lambda uid=current.uid: state.delete_rule(uid))

        st.divider()
        st.markdown("**Output**")
        st.session_state[state.PREFIX] = st.text_input(
            "Column prefix", value=st.session_state[state.PREFIX]
        )
        st.session_state[state.FULL_AUDIT] = st.toggle(
            "full_audit",
            value=st.session_state[state.FULL_AUDIT],
            help="Adds matched_rules, first_matched_rule_trace and assignment_results "
            "to the preview. It never changes what a rule decides.",
        )

        issues = yaml_io.validate(ruleset, state.columns(), state.functions().keys())
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
