"""
Rules Engine Studio application entry point.

The application authors canonical ruleset metadata, evaluates uploaded rows
with the production row runtime, and exports compiler-validated YAML.
"""

from __future__ import annotations

import streamlit as st
from streamlit_sortables import sort_items

from studio import state, yaml_io
from studio.schema import Rule
from studio.ui import data, evaluate, rules, yaml_tab

st.set_page_config(
    page_title="Rules Engine Studio",
    page_icon=":material/rule:",
    layout="wide",
    initial_sidebar_state="expanded",
)

_RULE_SORT_STYLE = """
.sortable-component {
    background: transparent;
    padding: 0;
}
.sortable-component.vertical {
    gap: 0.35rem;
}
.sortable-component.vertical .sortable-container,
.sortable-container-body {
    background: transparent;
    padding: 0;
}
.sortable-item,
.sortable-item:hover {
    background: #151923;
    border: 2px solid #566780;
    border-radius: 0.55rem;
    color: #F8FAFC;
    cursor: grab;
    font-size: 0.88rem;
    margin: 0.3rem 0;
    padding: 0.55rem 0.65rem;
}
.sortable-item:hover {
    border-color: #94A3B8;
    background: #182131;
}
.sortable-item:active {
    cursor: grabbing;
}
"""


def _render_rule_sorter(ordered: list[Rule]) -> None:
    """Render drag ordering and commit changed positions to rule order values."""
    labels: list[str] = []
    rules_by_label: dict[str, Rule] = {}
    for rule in ordered:
        label = f"{rule.rule_order} · {rule.rule_id} — {rule.rule_name}"
        if label in rules_by_label:
            label = f"{label} · {rule.uid[:6]}"
        labels.append(label)
        rules_by_label[label] = rule
    signature = "-".join(rule.uid for rule in ordered)
    dragged = sort_items(
        labels,
        direction="vertical",
        custom_style=_RULE_SORT_STYLE,
        key=f"rule-order-{signature}",
    )
    if dragged != labels and state.reorder_rules([rules_by_label[label].uid for label in dragged]):
        st.rerun()


def inject_styles() -> None:
    """Apply the studio's dark, high-contrast authoring surface."""
    st.markdown(
        """
        <style>
        :root {
            --studio-panel: #121824;
            --studio-panel-raised: #182131;
            --studio-control-bg: #151923;
            --studio-control-border: #94A3B8;
            --studio-control-border-hover: #C4CFDD;
            --studio-control-text: #F8FAFC;
            --studio-border: #61718B;
            --studio-section-border: #566780;
            --studio-table-border: #718198;
            --studio-rule: #38BDF8;
            --studio-group: #A78BFA;
            --studio-condition: #F59E0B;
            --studio-assignment: #34D399;
            --studio-expression: #93C5FD;
        }

        [data-testid="stSidebar"] {
            background: #0C111B;
            border-right: 1px solid var(--studio-border);
        }

        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            gap: 0.7rem;
        }

        [data-testid="stTextInputRootElement"],
        [data-testid="stNumberInputContainer"],
        [data-testid="stTextAreaRootElement"],
        [data-testid="stSelectbox"] > div:last-child,
        [data-testid="stMultiSelect"] > div:last-child,
        [data-testid="stDateInputField"],
        [data-testid="stTimeInputTimeDisplay"],
        [data-testid="stTextInput"] [data-baseweb="input"],
        [data-testid="stNumberInput"] [data-baseweb="input"],
        [data-testid="stSelectbox"] [data-baseweb="select"],
        [data-testid="stMultiSelect"] [data-baseweb="select"],
        [data-testid="stFileUploader"] section,
        [data-testid="stDataEditor"] {
            background-color: var(--studio-control-bg) !important;
            border: 1px solid var(--studio-control-border) !important;
            border-radius: 0.55rem !important;
            box-shadow: 0 0 0 1px var(--studio-control-border) !important;
            box-sizing: border-box;
        }

        [data-testid="stTextInputField"],
        [data-testid="stNumberInputField"],
        [data-testid="stTextArea"] textarea,
        [data-testid="stSelectbox"] input,
        [data-testid="stMultiSelect"] input,
        [data-testid="stTextInput"] [data-baseweb="base-input"],
        [data-testid="stNumberInput"] [data-baseweb="base-input"] {
            background-color: transparent !important;
            color: var(--studio-control-text) !important;
            -webkit-text-fill-color: var(--studio-control-text) !important;
        }

        [data-testid="stTextInputField"]::placeholder,
        [data-testid="stNumberInputField"]::placeholder,
        [data-testid="stTextArea"] textarea::placeholder {
            color: #AEBBCD !important;
            -webkit-text-fill-color: #AEBBCD !important;
            opacity: 0.9;
        }

        [data-testid="stNumberInput"] button {
            background-color: transparent !important;
            color: var(--studio-control-text) !important;
            border-left: 1px solid #718198 !important;
        }

        [data-testid="stTextInputRootElement"]:hover,
        [data-testid="stNumberInputContainer"]:hover,
        [data-testid="stTextAreaRootElement"]:hover,
        [data-testid="stSelectbox"] > div:last-child:hover,
        [data-testid="stMultiSelect"] > div:last-child:hover,
        [data-testid="stDateInputField"]:hover,
        [data-testid="stTimeInputTimeDisplay"]:hover,
        [data-testid="stTextInput"] [data-baseweb="input"]:hover,
        [data-testid="stNumberInput"] [data-baseweb="input"]:hover,
        [data-testid="stSelectbox"] [data-baseweb="select"]:hover,
        [data-testid="stMultiSelect"] [data-baseweb="select"]:hover {
            border-color: var(--studio-control-border-hover) !important;
            box-shadow: 0 0 0 1px var(--studio-control-border-hover) !important;
        }

        [data-testid="stTextInputRootElement"]:focus-within,
        [data-testid="stNumberInputContainer"]:focus-within,
        [data-testid="stTextAreaRootElement"]:focus-within,
        [data-testid="stSelectbox"] > div:last-child:focus-within,
        [data-testid="stMultiSelect"] > div:last-child:focus-within,
        [data-testid="stDateInputField"]:focus-within,
        [data-testid="stTimeInputTimeDisplay"]:focus-within,
        [data-testid="stTextInput"] [data-baseweb="input"]:focus-within,
        [data-testid="stNumberInput"] [data-baseweb="input"]:focus-within,
        [data-testid="stSelectbox"] [data-baseweb="select"]:focus-within,
        [data-testid="stMultiSelect"] [data-baseweb="select"]:focus-within {
            border-color: #C4B5FD !important;
            box-shadow: 0 0 0 2px rgba(167, 139, 250, 0.55) !important;
        }

        [data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--studio-section-border) !important;
            border-width: 2px !important;
            background: var(--studio-panel);
        }

        [data-testid="stDataFrame"],
        [data-testid="stDataEditor"] {
            border: 2px solid var(--studio-table-border) !important;
            border-radius: 0.65rem !important;
            box-shadow: 0 0 0 1px rgba(113, 129, 152, 0.22) !important;
        }

        [data-testid="stExpander"] > details {
            border-color: var(--studio-section-border) !important;
            border-width: 2px !important;
        }

        [data-testid="stTabs"] [role="tablist"] {
            border-bottom: 2px solid var(--studio-section-border) !important;
        }

        [data-testid="stDivider"] {
            border-top: 2px solid var(--studio-section-border) !important;
        }

        [class*="st-key-rule_node_"] {
            border-left: 4px solid var(--studio-rule);
            box-sizing: border-box;
            padding-left: 1.5rem;
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

        .studio-expression-preview {
            background: rgba(30, 41, 59, 0.72);
            border: 1px solid #64748B;
            border-left: 3px solid var(--studio-expression);
            border-radius: 0.5rem;
            margin: 0.35rem 0 0.15rem;
            padding: 0.65rem 0.8rem;
        }

        .studio-expression-label {
            color: #BFDBFE;
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.06em;
            margin-bottom: 0.3rem;
            text-transform: uppercase;
        }

        .studio-expression-text {
            color: #F8FAFC;
            font-size: 0.9rem;
            line-height: 1.55;
            overflow-wrap: anywhere;
            white-space: pre-wrap;
        }

        [class*="st-key-expression_"] {
            margin: 0.35rem 0 0.75rem;
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
        elif len(ordered) > 1:
            with st.expander("Drag to reorder", expanded=True):
                st.caption("Drag rules into order · Up/Down remains available")
                _render_rule_sorter(ordered)
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
