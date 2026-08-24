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


def inject_styles() -> None:
    """Apply the studio's dark, high-contrast authoring surface."""
    st.markdown(
        """
        <style>
        :root {
            --studio-panel: #121824;
            --studio-panel-raised: #182131;
            --studio-input: #3A4B66;
            --studio-input-border: #B7C4D8;
            --studio-border: #61718B;
            --studio-rule: #38BDF8;
            --studio-rule-input: #263449;
            --studio-rule-input-border: #94A3B8;
            --studio-rule-input-text: #F8FAFC;
            --studio-group: #A78BFA;
            --studio-condition: #F59E0B;
            --studio-assignment: #34D399;
        }

        [data-testid="stSidebar"] {
            background: #0C111B;
            border-right: 1px solid var(--studio-border);
        }

        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            gap: 0.7rem;
        }

        [data-testid="stTextInput"] [data-baseweb="input"],
        [data-testid="stNumberInput"] [data-baseweb="input"],
        [data-testid="stTextArea"] textarea,
        [data-testid="stSelectbox"] [data-baseweb="select"] > div,
        [data-testid="stFileUploader"] section,
        [data-testid="stDataEditor"] {
            background: var(--studio-input) !important;
            border: 2px solid var(--studio-input-border) !important;
            box-shadow: inset 0 0 0 1px rgba(248, 250, 252, 0.12);
        }

        [data-testid="stTextInput"] input,
        [data-testid="stNumberInput"] input,
        [data-testid="stTextArea"] textarea,
        [data-testid="stSelectbox"] [data-baseweb="select"] > div {
            color: #F8FAFC !important;
        }

        [data-testid="stTextInput"] input::placeholder,
        [data-testid="stNumberInput"] input::placeholder,
        [data-testid="stTextArea"] textarea::placeholder {
            color: #D4DDEA !important;
            opacity: 0.9;
        }

        [data-testid="stTextInput"] [data-baseweb="input"]:hover,
        [data-testid="stNumberInput"] [data-baseweb="input"]:hover,
        [data-testid="stTextArea"] textarea:hover,
        [data-testid="stSelectbox"] [data-baseweb="select"] > div:hover {
            border-color: #B0BED2 !important;
        }

        [data-testid="stTextInput"] [data-baseweb="input"]:focus-within,
        [data-testid="stNumberInput"] [data-baseweb="input"]:focus-within,
        [data-testid="stTextArea"] textarea:focus,
        [data-testid="stSelectbox"] [data-baseweb="select"] > div:focus-within {
            border-color: #C4B5FD !important;
            box-shadow: 0 0 0 2px rgba(167, 139, 250, 0.55) !important;
        }

        [data-testid="stVerticalBlockBorderWrapper"] {
            border-color: #42506A !important;
            background: var(--studio-panel);
        }

        [class*="st-key-rule_node_"] {
            border-left: 4px solid var(--studio-rule);
            box-sizing: border-box;
            padding-left: 1.5rem;
        }

        [class*="st-key-rule_node_"] [data-testid="stTextInput"] [data-baseweb="input"],
        [class*="st-key-rule_node_"] [data-testid="stNumberInput"] [data-baseweb="input"],
        [class*="st-key-rule_node_"] [data-testid="stTextArea"] textarea,
        [class*="st-key-rule_node_"] [data-testid="stSelectbox"] [data-baseweb="select"] > div,
        [class*="st-key-rule_node_"] [data-testid="stMultiSelect"] [data-baseweb="select"] > div,
        [class*="st-key-rule_node_"] [data-testid="stDateInput"] [data-baseweb="input"],
        [class*="st-key-rule_node_"] [data-testid="stTimeInput"] [data-baseweb="input"] {
            background-color: var(--studio-rule-input) !important;
            border: 1px solid var(--studio-rule-input-border) !important;
            box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15) !important;
        }

        [class*="st-key-rule_node_"] [data-testid="stTextInput"] [data-baseweb="base-input"],
        [class*="st-key-rule_node_"] [data-testid="stNumberInput"] [data-baseweb="base-input"],
        [class*="st-key-rule_node_"] [data-testid="stTextInput"] input,
        [class*="st-key-rule_node_"] [data-testid="stNumberInput"] input,
        [class*="st-key-rule_node_"] [data-testid="stTextArea"] textarea {
            background-color: var(--studio-rule-input) !important;
            color: var(--studio-rule-input-text) !important;
            -webkit-text-fill-color: var(--studio-rule-input-text) !important;
        }

        [class*="st-key-rule_node_"] [data-testid="stTextInput"] input,
        [class*="st-key-rule_node_"] [data-testid="stNumberInput"] input {
            outline: 1px solid var(--studio-rule-input-border) !important;
            outline-offset: -1px;
        }

        [class*="st-key-rule_node_"] [data-testid="stSelectbox"] [data-baseweb="select"],
        [class*="st-key-rule_node_"] [data-testid="stMultiSelect"] [data-baseweb="select"] {
            border-radius: 0.55rem !important;
            box-shadow: 0 0 0 1px var(--studio-rule-input-border) !important;
        }

        [class*="st-key-rule_node_"] [data-testid="stSelectbox"] [data-baseweb="select"] > div,
        [class*="st-key-rule_node_"] [data-testid="stMultiSelect"] [data-baseweb="select"] > div {
            background-color: var(--studio-rule-input) !important;
        }

        [class*="st-key-rule_node_"] [data-testid="stTextInput"] input::placeholder,
        [class*="st-key-rule_node_"] [data-testid="stNumberInput"] input::placeholder,
        [class*="st-key-rule_node_"] [data-testid="stTextArea"] textarea::placeholder {
            color: #AEBBCD !important;
            -webkit-text-fill-color: #AEBBCD !important;
        }

        [class*="st-key-rule_node_"] [data-testid="stNumberInput"] button {
            background-color: #33445C !important;
            color: var(--studio-rule-input-text) !important;
            border-left: 1px solid #718198 !important;
        }

        [class*="st-key-rule_node_"] [data-testid="stTextInput"] [data-baseweb="input"]:hover,
        [class*="st-key-rule_node_"] [data-testid="stNumberInput"] [data-baseweb="input"]:hover,
        [class*="st-key-rule_node_"] [data-testid="stTextArea"] textarea:hover,
        [class*="st-key-rule_node_"] [data-testid="stSelectbox"] [data-baseweb="select"] > div:hover,
        [class*="st-key-rule_node_"] [data-testid="stMultiSelect"] [data-baseweb="select"] > div:hover {
            border-color: #C4CFDD !important;
        }

        [class*="st-key-rule_node_"] [data-testid="stSelectbox"] [data-baseweb="select"]:hover,
        [class*="st-key-rule_node_"] [data-testid="stMultiSelect"] [data-baseweb="select"]:hover {
            box-shadow: 0 0 0 1px #C4CFDD !important;
        }

        [class*="st-key-rule_node_"] [data-testid="stTextInput"] [data-baseweb="input"]:focus-within,
        [class*="st-key-rule_node_"] [data-testid="stNumberInput"] [data-baseweb="input"]:focus-within,
        [class*="st-key-rule_node_"] [data-testid="stTextArea"] textarea:focus,
        [class*="st-key-rule_node_"] [data-testid="stSelectbox"] [data-baseweb="select"] > div:focus-within,
        [class*="st-key-rule_node_"] [data-testid="stMultiSelect"] [data-baseweb="select"] > div:focus-within,
        [class*="st-key-rule_node_"] [data-testid="stTextInput"] input:focus,
        [class*="st-key-rule_node_"] [data-testid="stNumberInput"] input:focus {
            border-color: #B8A7FF !important;
            outline-color: #A78BFA !important;
            box-shadow: 0 0 0 2px rgba(167, 139, 250, 0.5) !important;
        }

        [class*="st-key-rule_node_"] [data-testid="stSelectbox"] [data-baseweb="select"]:focus-within,
        [class*="st-key-rule_node_"] [data-testid="stMultiSelect"] [data-baseweb="select"]:focus-within {
            box-shadow: 0 0 0 2px rgba(167, 139, 250, 0.65) !important;
        }

        [class*="st-key-group_depth_"] {
            border-left: 4px solid var(--studio-group);
            background: var(--studio-panel-raised);
        }

        [class*="st-key-condition_"] {
            margin-left: 1rem;
            width: calc(100% - 1rem);
            border-left: 4px solid var(--studio-condition);
            background: #171C26;
        }

        [class*="st-key-assignment_"] {
            margin-left: 1rem;
            width: calc(100% - 1rem);
            border-left: 4px solid var(--studio-assignment);
            background: #131F22;
        }

        [class*="st-key-group_depth_1_"],
        [class*="st-key-group_depth_2_"],
        [class*="st-key-group_depth_3_"] {
            margin-left: 1.25rem;
            width: calc(100% - 1.25rem);
        }

        [class*="st-key-group_depth_0_"] {
            margin-left: 0;
            width: 100%;
        }

        .studio-node-label {
            color: #CBD5E1;
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.11em;
            margin-bottom: 0.2rem;
            text-transform: uppercase;
        }

        .studio-rule-label {
            margin-bottom: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_styles()
state.init()


def sidebar() -> None:
    """Render ruleset metadata, navigation, and validation status."""
    ruleset = state.draft()

    with st.sidebar:
        st.markdown("### Rules Engine Studio")
        st.caption("Draft · test · export")

        with st.expander("Ruleset details", expanded=False):
            ruleset.ruleset_id = st.text_input("Ruleset id", value=ruleset.ruleset_id)
            ruleset.ruleset_name = st.text_input("Ruleset name", value=ruleset.ruleset_name)
            ruleset.version = st.text_input("Version", value=ruleset.version)
            ruleset.description = st.text_area("Description", value=ruleset.description, height=70)
            ruleset.owner = st.text_input("Owner", value=ruleset.owner)
            ruleset.owner_department = st.text_input(
                "Owner department", value=ruleset.owner_department
            )
            st.caption("Owner and owner department are required by the production validator.")

        st.divider()
        st.markdown("**Rules**")
        st.caption("Ruleset → ordered rules")
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

tab_rules, tab_data, tab_eval, tab_yaml = st.tabs(["Rules", "Sample data", "Evaluate", "YAML"])

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
