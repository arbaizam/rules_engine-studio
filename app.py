"""
Rules Engine Studio application entry point.

The application authors canonical ruleset metadata, evaluates uploaded rows
with the production row runtime, and exports compiler-validated YAML.
"""

from __future__ import annotations

import streamlit as st

from studio import state
from studio.ui import browser_state, data, evaluate, reorder, rules, yaml_preview, yaml_tab

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
            --studio-navy: #003359;
            --studio-blue: #93B1CC;
            --studio-lime: #AAAD00;
            --studio-panel: #082238;
            --studio-panel-raised: #0D2C43;
            --studio-control-bg: #071E2D;
            --studio-control-border: #52758F;
            --studio-control-border-hover: #93B1CC;
            --studio-control-text: #F8FAFC;
            --studio-border: #456A85;
            --studio-section-border: #52758F;
            --studio-table-border: #7194AE;
            --studio-rule: #058AA8;
            --studio-group: #93B1CC;
            --studio-condition: #AAAD00;
            --studio-assignment: #6D97B8;
        }

        [data-testid="stMainBlockContainer"] {
            padding-left: 1.25rem !important;
            padding-right: 1.25rem !important;
            padding-top: 3.5rem !important;
        }

        [data-testid="stSidebar"] {
            background: #001F35;
            border-right: 1px solid var(--studio-border);
        }

        [data-testid="stSidebarHeader"] {
            margin-bottom: 0 !important;
        }

        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            gap: 0.7rem;
        }

        [class*="st-key-sidebar_brand"] h2 {
            font-size: 1.5rem !important;
            font-weight: 800 !important;
            line-height: 1.2 !important;
            padding: 0 0 0.15rem !important;
            white-space: nowrap;
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
            color: #AFC1CF !important;
            -webkit-text-fill-color: #AFC1CF !important;
            opacity: 0.9;
        }

        [data-testid="stNumberInput"] button {
            background-color: transparent !important;
            color: var(--studio-control-text) !important;
            border-left: 1px solid var(--studio-table-border) !important;
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
            border-color: var(--studio-lime) !important;
            box-shadow: 0 0 0 2px rgba(170, 173, 0, 0.45) !important;
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
            box-shadow: 0 0 0 1px rgba(147, 177, 204, 0.22) !important;
        }

        [data-testid="stExpander"] > details {
            border-color: var(--studio-section-border) !important;
            border-width: 2px !important;
        }

        [data-testid="stTabs"] [role="tablist"] {
            border-bottom: 2px solid var(--studio-section-border) !important;
        }

        [data-testid="stTabs"] [role="tab"] {
            height: 3.25rem;
            padding-left: 1rem;
            padding-right: 1rem;
        }

        [data-testid="stTabs"] [role="tab"] p {
            font-size: 1.25rem !important;
            font-weight: 750 !important;
        }

        [data-testid="stTabs"] [role="tab"][aria-selected="true"] p {
            color: #CFD23A !important;
        }

        [data-testid="stTabs"] [data-baseweb="tab-highlight"] {
            background-color: var(--studio-lime) !important;
        }

        [data-testid="stBaseButton-primary"] {
            background-color: var(--studio-lime) !important;
            border-color: var(--studio-lime) !important;
            color: #071722 !important;
        }

        [data-testid="stBaseButton-primary"] p {
            color: #071722 !important;
            font-weight: 750 !important;
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
            background: #0A2436;
        }

        [class*="st-key-condition_"] > div > [data-testid="stVerticalBlock"] {
            gap: 0.7rem;
        }

        [class*="st-key-condition-footer-"] [data-testid="stButton"] button,
        [class*="st-key-assignment-footer-"] [data-testid="stButton"] button {
            padding-left: 0.4rem;
            padding-right: 0.4rem;
            width: 100%;
        }

        [class*="st-key-condition-footer-"] [data-testid="stButton"] button p,
        [class*="st-key-assignment-footer-"] [data-testid="stButton"] button p {
            white-space: nowrap;
        }

        [data-testid="stHorizontalBlock"]:has([class*="st-key-condition-footer-"])
            [class*="st-key-expression_"],
        [data-testid="stHorizontalBlock"]:has([class*="st-key-assignment-footer-"])
            [class*="st-key-expression_"] {
            margin: 0;
        }

        [class*="st-key-assignment_"] {
            margin-left: 1rem;
            width: calc(100% - 1rem);
            border-left: 4px solid var(--studio-assignment);
            background: #0A2738;
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
            color: #C7D7E3;
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.11em;
            margin-bottom: 0.2rem;
            text-transform: uppercase;
        }

        .studio-rule-label {
            margin-bottom: 1rem;
        }

        .studio-expression-label {
            color: var(--studio-blue);
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.06em;
            margin-bottom: 0.35rem;
            text-transform: uppercase;
        }

        .studio-expression-text {
            color: #F8FAFC;
            font-size: 0.95rem;
            line-height: 1.55;
            overflow-wrap: anywhere;
            padding: 0 0.15rem 0.25rem;
            white-space: pre-wrap;
        }

        .studio-inline-control-label {
            display: flex;
            min-height: 2.25rem;
            align-items: center;
            color: var(--studio-control-text);
            font-size: 0.875rem;
            line-height: 1.25rem;
            white-space: nowrap;
        }

        [data-testid="stMarkdownContainer"]:has(> .studio-inline-control-label) {
            margin-bottom: 0;
        }

        [class*="st-key-delete_selected_rule"] button,
        [class*="st-key-delete_selected_rule"] button:hover,
        [class*="st-key-delete_selected_rule"] button:active,
        [class*="st-key-delete_selected_rule"] button:focus-visible,
        [class*="st-key-delete_selected_rule"] button:disabled {
            background-color: #9A0000 !important;
            border-color: #9A0000 !important;
            color: #FFFFFF !important;
        }

        [class*="st-key-delete_selected_rule"] button p {
            color: #FFFFFF !important;
        }

        [class*="st-key-expression_"] {
            margin: 0.35rem 0 0.75rem;
        }

        [class*="st-key-yaml_preview_panel"] {
            background: var(--studio-panel);
            border-color: var(--studio-section-border) !important;
            border-width: 2px !important;
            box-sizing: border-box;
            height: calc(100vh - 5rem);
            max-height: calc(100vh - 5rem);
            overflow: hidden;
        }

        [data-testid="stLayoutWrapper"]:has(> [class*="st-key-yaml_preview_panel"]) {
            margin-bottom: 1rem;
            margin-top: 0;
            position: sticky;
            top: 4rem;
            z-index: 2;
        }

        [class*="st-key-yaml_preview_header"] h3 {
            margin: 0;
            white-space: nowrap;
        }

        [class*="st-key-yaml_preview_close_button"] button {
            color: var(--studio-blue) !important;
            padding-left: 0.55rem;
            padding-right: 0.55rem;
        }

        .studio-yaml-status {
            align-items: center;
            background: #071E2D;
            border: 1px solid var(--studio-control-border);
            border-radius: 999px;
            color: #D9E5ED;
            display: flex;
            font-size: 0.78rem;
            font-weight: 700;
            gap: 0.5rem;
            line-height: 1.2;
            margin: 0.1rem 0 0.75rem;
            padding: 0.42rem 0.65rem;
        }

        .studio-yaml-status span,
        .studio-yaml-rail-status {
            border-radius: 50%;
            display: inline-block;
            flex: 0 0 auto;
            height: 0.55rem;
            width: 0.55rem;
        }

        .studio-yaml-status.ready span,
        .studio-yaml-rail-status.ready {
            background: var(--studio-lime);
            box-shadow: 0 0 0 3px rgba(170, 173, 0, 0.18);
        }

        .studio-yaml-status.blocked span,
        .studio-yaml-rail-status.blocked {
            background: #FF806B;
            box-shadow: 0 0 0 3px rgba(255, 128, 107, 0.18);
        }

        [class*="st-key-yaml_preview_panel"] [data-testid="stCode"] {
            border: 1px solid var(--studio-control-border);
            border-radius: 0.55rem;
            height: calc(100vh - 17rem) !important;
            max-height: none !important;
            min-height: 16rem;
        }

        [class*="st-key-yaml_preview_panel"] [data-testid="stCode"] pre {
            height: 100% !important;
            max-height: none !important;
        }

        [class*="st-key-yaml_preview_rail"] {
            align-items: center;
            background: var(--studio-panel);
            border: 2px solid var(--studio-section-border);
            border-radius: 0.55rem;
            display: flex;
            flex-direction: column;
            min-height: 14rem;
        }

        [data-testid="stLayoutWrapper"]:has(> [class*="st-key-yaml_preview_rail"]) {
            position: sticky;
            top: calc(50vh - 7rem);
            z-index: 2;
        }

        [class*="st-key-yaml_preview_rail"] [data-testid="stButton"] {
            flex: 1 1 auto;
            width: 100%;
        }

        [class*="st-key-yaml_preview_rail"] [data-testid="stButton"] button {
            height: 100%;
            min-height: 11.5rem;
            padding: 0.6rem 0.2rem;
        }

        [class*="st-key-yaml_preview_rail"] [data-testid="stButton"] button p {
            font-size: 0.8rem;
            font-weight: 800;
            letter-spacing: 0.12em;
            transform: rotate(180deg);
            writing-mode: vertical-rl;
        }

        .studio-yaml-rail-status {
            margin: 0.65rem auto;
        }

        @media (max-width: 1050px) {
            [class*="st-key-yaml_preview_panel"] {
                height: auto;
                max-height: none;
            }

            [data-testid="stLayoutWrapper"]:has(> [class*="st-key-yaml_preview_panel"]),
            [data-testid="stLayoutWrapper"]:has(> [class*="st-key-yaml_preview_rail"]) {
                margin-bottom: 0;
                margin-top: 0;
                position: relative;
                top: auto;
                z-index: auto;
            }

            [class*="st-key-yaml_preview_panel"] [data-testid="stCode"] {
                height: 30rem !important;
                min-height: 20rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_styles()
state.init()


def sidebar():
    """Render ruleset metadata and navigation, returning its status placeholder."""
    ruleset = state.draft()

    with st.sidebar:
        with st.container(key="sidebar_brand"):
            st.markdown("## Rules Engine Studio")
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
        current = state.selected_rule()
        if ordered and current is not None:
            current_index = next(
                index for index, rule in enumerate(ordered) if rule.uid == current.uid
            )
            with st.expander("Reorder rules", expanded=True):
                reorder.render_drag_sorter(ordered, current.uid)
                st.caption(
                    f"Or move the selected rule: {current.rule_order} · "
                    f"{current.rule_id or 'untitled'}"
                )
                move = st.columns(2)
                if move[0].button(
                    "Move up",
                    key=f"reorder-up-{current.uid}",
                    width="stretch",
                    disabled=len(ordered) == 1 or current_index == 0,
                ):
                    state.queue(lambda uid=current.uid: state.move_rule(uid, -1))
                if move[1].button(
                    "Move down",
                    key=f"reorder-down-{current.uid}",
                    width="stretch",
                    disabled=len(ordered) == 1 or current_index == len(ordered) - 1,
                ):
                    state.queue(lambda uid=current.uid: state.move_rule(uid, 1))

        add = st.columns(2)
        if add[0].button("Add rule", width="stretch"):
            state.queue(state.add_rule)
        if add[1].button("Duplicate", width="stretch", disabled=current is None):
            state.queue(lambda uid=current.uid: state.duplicate_rule(uid))

        if st.button(
            "Delete selected rule",
            key="delete_selected_rule",
            width="stretch",
            disabled=current is None,
        ):
            state.queue(lambda uid=current.uid: state.delete_rule(uid))

        st.divider()
        st.markdown("**Output**")
        st.session_state[state.PREFIX] = st.text_input(
            "Column prefix", value=st.session_state[state.PREFIX]
        )
        return st.empty()


sidebar_status = sidebar()
yaml_preview.init()
workspace, yaml_rail = yaml_preview.workspace_columns()

snapshot = None
with workspace:
    tab_rules, tab_data, tab_eval, tab_yaml = st.tabs(
        ["Rules", "Sample data", "Evaluate", "YAML"],
        key="studio_tab",
        on_change="rerun",
    )

    # Tracked tabs expose which panel is open, so hidden views can stay dormant.
    # YAML is the exception: one cached snapshot feeds the preview, validation,
    # and export state without independently recompiling each surface.
    if tab_rules.open:
        with tab_rules:
            rules.render()
    elif tab_data.open:
        with tab_data:
            data.render()
    elif tab_eval.open:
        with tab_eval:
            evaluate.render()
    elif tab_yaml.open:
        snapshot = yaml_preview.current_snapshot()
        with tab_yaml:
            yaml_tab.render(snapshot)

if snapshot is None:
    # Authoring widgets above mutate the model during render. Taking the
    # snapshot afterward makes the adjacent YAML reflect that same interaction.
    snapshot = yaml_preview.current_snapshot()

with yaml_rail:
    yaml_preview.render(snapshot)

with sidebar_status.container():
    if snapshot.error_count:
        st.error(f"{snapshot.error_count} to fix before export")
    else:
        st.success("Ready to export")

with st.sidebar:
    browser_state.render()

# Structural edits queued during render are applied here, then the page redraws.
if state.flush():
    st.rerun()
