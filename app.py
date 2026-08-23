"""Rules Engine Studio — professional business rule authoring and testing."""

from __future__ import annotations

import hashlib
import html
import re
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import streamlit as st

from rules_engine.engine import (
    OPERATOR_LABELS,
    TYPE_OPERATORS,
    describe_condition,
    evaluate_rule,
    validate_rule,
)
from rules_engine.examples import TEMPLATES, rule_from_template, starter_rulebook
from rules_engine.models import Condition, FieldDefinition, Outcome, Rule
from rules_engine.storage import (
    deserialize_rulebook,
    load_rulebook,
    save_rulebook,
    serialize_rulebook,
)


APP_DIR = Path(__file__).resolve().parent
RULEBOOK_PATH = APP_DIR / "data" / "rulebook.json"
NAV_OPTIONS = ["Editor", "Test bench", "Rules"]
OUTCOME_KINDS = [
    "Decision",
    "Route to queue",
    "Apply tag",
    "Apply discount",
    "Calculate fee",
    "Send notification",
]


st.set_page_config(
    page_title="Rules Engine Studio",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ink: #182033;
            --muted: #687086;
            --brand: #6655d9;
            --brand-soft: #eeeafd;
            --line: #e4e7ef;
            --success: #13795b;
        }
        .stApp { background: #f7f8fb; }
        [data-testid="stHeader"] { background: transparent; }
        [data-testid="stSidebar"] { border-right: 1px solid var(--line); }
        [data-testid="stSidebar"] > div:first-child { background: #fff; }
        .block-container { max-width: 1280px; padding-top: 1.15rem; padding-bottom: 3rem; }
        h1, h2, h3 { color: var(--ink); letter-spacing: -0.025em; }
        h1 { font-size: 1.65rem !important; }
        h2 { margin-top: 0 !important; }
        p, label { color: var(--ink); }
        .eyebrow {
            color: var(--brand); font-size: .76rem; font-weight: 800;
            letter-spacing: .1em; text-transform: uppercase; margin-bottom: .35rem;
        }
        .workspace-title { margin: 0; font-size: 1.55rem; font-weight: 800; letter-spacing: -.035em; }
        .workspace-meta { color: var(--muted); font-size: .78rem; margin-top: .2rem; }
        .section-kicker { color: var(--muted); font-size: .72rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
        .editor-toolbar { margin: .15rem 0 .8rem; }
        .brand-mark {
            display: inline-grid; place-items: center; width: 34px; height: 34px;
            border-radius: 10px; color: white; background: linear-gradient(135deg, #765ff2, #4c3bb4);
            font-weight: 900; margin-right: 9px; box-shadow: 0 7px 20px rgba(102,85,217,.22);
        }
        .sidebar-brand { font-size: 1.08rem; font-weight: 800; color: var(--ink); margin: .1rem 0 1.4rem; }
        .logic-preview {
            background: #f5f3ff; color: var(--ink); border: 1px solid #ddd7ff;
            border-radius: 10px; padding: .78rem .9rem; margin: .65rem 0 .8rem;
        }
        .logic-preview .logic-label { color: #6655d9; font-size: .68rem; font-weight: 800; letter-spacing: .09em; }
        .logic-preview .logic-main { color: var(--ink); font-size: .9rem; font-weight: 650; margin: .2rem 0; line-height: 1.4; }
        .logic-preview .logic-outcome { color: #514a72; font-size: .84rem; }
        .mini-tag {
            display: inline-block; color: #5145a8; background: #f0edff; border-radius: 100px;
            padding: .23rem .58rem; margin: .1rem .2rem .1rem 0; font-size: .72rem; font-weight: 700;
        }
        .status-chip {
            display: inline-block; padding: .24rem .58rem; border-radius: 100px;
            font-size: .72rem; font-weight: 800; margin-left: .3rem;
        }
        .status-live { color: #0f6c50; background: #dff6ec; }
        .status-draft { color: #8a5b00; background: #fff0ca; }
        .trace-pass, .trace-fail {
            border-radius: 10px; padding: .72rem .85rem; margin: .45rem 0;
            font-size: .88rem; border: 1px solid;
        }
        .trace-pass { color: #0f6249; background: #f0faf6; border-color: #c5ebdc; }
        .trace-fail { color: #8b3841; background: #fff6f6; border-color: #f1d3d6; }
        .empty-state {
            text-align: center; padding: 3rem 1rem; border: 1px dashed #cdd2df;
            border-radius: 14px; background: #fff; color: var(--muted);
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--line) !important; border-radius: 14px !important;
            box-shadow: 0 2px 9px rgba(34, 39, 60, .025);
        }
        div[data-testid="stMetric"] {
            background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: .7rem .9rem;
        }
        div[data-testid="stRadio"] > div { gap: .2rem; }
        div[data-testid="stRadio"] label {
            background: #fff; border: 1px solid var(--line); border-radius: 9px;
            padding: .34rem .75rem; margin-right: .25rem;
        }
        .footer-note { text-align: center; color: #9197a8; font-size: .72rem; margin-top: 2rem; }
        @media (max-width: 760px) {
            .block-container { padding-top: 1.2rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def clone_rule(rule: Rule) -> Rule:
    return Rule.from_dict(deepcopy(rule.to_dict()))


def flash(message: str, kind: str = "success") -> None:
    st.session_state["flash"] = (message, kind)


def show_flash() -> None:
    item = st.session_state.pop("flash", None)
    if not item:
        return
    message, kind = item
    if kind == "error":
        st.error(message)
    elif kind == "warning":
        st.warning(message)
    else:
        st.success(message)


def initialise_state() -> None:
    if "rules" not in st.session_state:
        try:
            stored = load_rulebook(RULEBOOK_PATH)
        except (OSError, ValueError):
            stored = None
        if stored:
            name, rules = stored
            st.session_state.workspace_name = name
            st.session_state.rules = rules
        else:
            st.session_state.workspace_name = "My decision rulebook"
            st.session_state.rules = [Rule.from_dict(item) for item in starter_rulebook()]
    if "draft_rule" not in st.session_state:
        if st.session_state.rules:
            st.session_state.draft_rule = clone_rule(st.session_state.rules[0])
        else:
            st.session_state.draft_rule = blank_rule()
    st.session_state.setdefault("draft_revision", 0)
    st.session_state.setdefault("selected_template", "Transaction review")
    st.session_state.setdefault("navigation", NAV_OPTIONS[0])
    st.session_state.setdefault("last_upload", "")
    if st.session_state.pop("go_to_test", False):
        st.session_state.navigation = NAV_OPTIONS[1]
    if st.session_state.pop("go_to_build", False):
        st.session_state.navigation = NAV_OPTIONS[0]


def blank_rule(fields: list[FieldDefinition] | None = None) -> Rule:
    available_fields = deepcopy(fields or [])
    if not available_fields:
        available_fields = [
            FieldDefinition(key="amount", label="Amount", data_type="number", example=100),
            FieldDefinition(key="category", label="Category", data_type="text", example="Standard"),
        ]
    return Rule(
        name="",
        description="",
        fields=available_fields,
        conditions=[Condition(field=available_fields[0].key, operator="equals", value=None)],
        outcome=Outcome(kind="Decision", value="", message=""),
        priority=100,
        enabled=True,
    )


def set_draft(rule: Rule, template_name: str | None = None) -> None:
    st.session_state.draft_rule = clone_rule(rule)
    st.session_state.draft_revision += 1
    if template_name:
        st.session_state.selected_template = template_name


def use_template(template_name: str) -> None:
    set_draft(Rule.from_dict(rule_from_template(template_name)), template_name)
    flash(f"Loaded the {template_name.lower()} starter.")


def edit_rule(rule_id: str) -> None:
    rule = next((item for item in st.session_state.rules if item.id == rule_id), None)
    if rule:
        set_draft(rule)
        st.session_state.go_to_build = True


def safe_persist() -> bool:
    try:
        save_rulebook(
            RULEBOOK_PATH,
            st.session_state.rules,
            st.session_state.workspace_name,
        )
        return True
    except OSError:
        return False


def save_current_rule() -> bool:
    draft: Rule = st.session_state.draft_rule
    errors = validate_rule(draft)
    if errors:
        flash("Please finish the highlighted rule details before saving.", "error")
        return False
    for index, existing in enumerate(st.session_state.rules):
        if existing.id == draft.id:
            st.session_state.rules[index] = clone_rule(draft)
            break
    else:
        st.session_state.rules.append(clone_rule(draft))
    persisted = safe_persist()
    flash(
        "Rule saved to your library."
        if persisted
        else "Rule saved for this session. Export the rulebook to keep a backup.",
        "success" if persisted else "warning",
    )
    return True


def field_by_key(rule: Rule, key: str) -> FieldDefinition:
    return next((field for field in rule.fields if field.key == key), rule.fields[0])


def slugify(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return result[:50]


def rule_sentence(rule: Rule) -> tuple[str, str]:
    joiner = " and " if rule.match == "all" else " or "
    conditions = joiner.join(describe_condition(item, rule.fields) for item in rule.conditions)
    if not conditions:
        conditions = "add a condition"
    result = f"{rule.outcome.kind}: {rule.outcome.value or 'choose an outcome'}"
    return conditions, result


def render_logic_preview(rule: Rule) -> None:
    conditions, result = rule_sentence(rule)
    conditions = html.escape(conditions)
    result = html.escape(result)
    st.markdown(
        f"""
        <div class="logic-preview">
          <div class="logic-label">EFFECTIVE LOGIC</div>
          <div class="logic-main">When {conditions}</div>
          <div class="logic-outcome">Then <b>{result}</b></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    active_count = sum(rule.enabled for rule in st.session_state.rules)
    st.markdown(
        '<div class="workspace-title">Rules Engine Studio</div>'
        f'<div class="workspace-meta">{html.escape(st.session_state.workspace_name)} · '
        f'{active_count}/{len(st.session_state.rules)} active rules</div>',
        unsafe_allow_html=True,
    )
    st.radio(
        "Workspace section",
        NAV_OPTIONS,
        horizontal=True,
        label_visibility="collapsed",
        key="navigation",
    )


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            '<div class="sidebar-brand"><span class="brand-mark">◇</span> Rules Studio</div>',
            unsafe_allow_html=True,
        )
        st.text_input(
            "Rulebook name",
            key="workspace_name",
            help="A rulebook is the collection you will export or share.",
        )

        enabled_count = sum(rule.enabled for rule in st.session_state.rules)
        col_a, col_b = st.columns(2)
        col_a.metric("Rules", len(st.session_state.rules))
        col_b.metric("Active", enabled_count)

        st.markdown("#### Import / export")
        export_content = serialize_rulebook(
            st.session_state.rules,
            st.session_state.workspace_name,
        )
        st.download_button(
            "Download JSON",
            data=export_content,
            file_name=f"{slugify(st.session_state.workspace_name) or 'rulebook'}.json",
            mime="application/json",
            use_container_width=True,
        )
        upload = st.file_uploader(
            "Import rulebook",
            type=["json"],
            help="Import a JSON rulebook previously downloaded from this studio.",
        )
        if upload is not None:
            content = upload.getvalue()
            digest = hashlib.sha256(content).hexdigest()
            if digest != st.session_state.last_upload:
                try:
                    name, rules = deserialize_rulebook(content)
                    st.session_state.workspace_name = name
                    st.session_state.rules = rules
                    st.session_state.last_upload = digest
                    if rules:
                        set_draft(rules[0])
                    safe_persist()
                    flash(f"Imported {len(rules)} rules from {upload.name}.")
                    st.rerun()
                except (UnicodeDecodeError, ValueError) as exc:
                    st.error(f"That file is not a valid rulebook: {exc}")

        st.divider()
        st.caption("JSON is the portable rulebook source of truth.")
        st.caption(f"Runtime store: `{RULEBOOK_PATH.relative_to(APP_DIR)}`")


def render_template_picker() -> None:
    with st.popover("Template", use_container_width=True):
        template_name = st.selectbox(
            "Template",
            list(TEMPLATES),
            index=list(TEMPLATES).index(st.session_state.selected_template),
            label_visibility="collapsed",
        )
        st.caption(TEMPLATES[template_name]["description"])
        if st.button("Load template", type="primary", use_container_width=True):
            use_template(template_name)
            st.rerun()


def render_field_manager(rule: Rule, revision: int) -> None:
    with st.expander(f"Field schema · {len(rule.fields)} fields", expanded=False):
        st.markdown(
            "".join(
                f'<span class="mini-tag">{html.escape(field.label)} · {field.data_type}</span>'
                for field in rule.fields
            ),
            unsafe_allow_html=True,
        )
        st.markdown("**Add field**")
        field_col, type_col, button_col = st.columns([2.1, 1.1, 1])
        new_label = field_col.text_input(
            "Field name",
            placeholder="e.g. Account age in days",
            key=f"new_field_label_{revision}",
        )
        new_type = type_col.selectbox(
            "Type",
            ["text", "number", "boolean", "date"],
            key=f"new_field_type_{revision}",
        )
        button_col.write("")
        button_col.write("")
        if button_col.button("Add field", key=f"add_field_{revision}", use_container_width=True):
            field_key = slugify(new_label)
            if not field_key:
                st.warning("Enter a field name first.")
            elif any(item.key == field_key for item in rule.fields):
                st.warning("That field already exists.")
            else:
                rule.fields.append(FieldDefinition(key=field_key, label=new_label.strip(), data_type=new_type))
                st.rerun()


def render_value_input(
    field: FieldDefinition,
    condition: Condition,
    revision: int,
) -> object:
    key = f"condition_value_{revision}_{condition.id}_{field.key}_{condition.operator}"
    if condition.operator in {"is_empty", "is_not_empty"}:
        st.caption("No comparison value needed")
        return None
    if condition.operator == "in":
        default = condition.value if isinstance(condition.value, list) else []
        if field.choices:
            valid_default = [item for item in default if item in field.choices]
            return st.multiselect("Value", field.choices, default=valid_default, key=key, label_visibility="collapsed")
        text_default = ", ".join(default) if isinstance(default, list) else str(condition.value or "")
        value = st.text_input(
            "Value",
            value=text_default,
            placeholder="Option A, Option B",
            key=key,
            label_visibility="collapsed",
        )
        return [item.strip() for item in value.split(",") if item.strip()]
    if field.data_type == "boolean":
        default = bool(condition.value) if condition.value is not None else True
        return st.selectbox(
            "Value",
            [True, False],
            index=0 if default else 1,
            format_func=lambda item: "Yes" if item else "No",
            key=key,
            label_visibility="collapsed",
        )
    if field.choices and condition.operator in {"equals", "not_equals"}:
        options = field.choices
        default_index = options.index(condition.value) if condition.value in options else 0
        return st.selectbox("Value", options, index=default_index, key=key, label_visibility="collapsed")
    if field.data_type == "number":
        try:
            default_number = float(condition.value) if condition.value not in (None, "") else 0.0
        except (TypeError, ValueError):
            default_number = 0.0
        return st.number_input(
            "Value",
            value=default_number,
            step=1.0,
            key=key,
            label_visibility="collapsed",
        )
    if field.data_type == "date":
        return st.text_input(
            "Value",
            value=str(condition.value or ""),
            placeholder="YYYY-MM-DD",
            key=key,
            label_visibility="collapsed",
        )
    return st.text_input(
        "Value",
        value=str(condition.value or ""),
        placeholder="Enter a comparison value",
        key=key,
        label_visibility="collapsed",
    )


def render_condition_builder(rule: Rule, revision: int) -> None:
    heading_col, match_col = st.columns([2, 1])
    heading_col.markdown("### Conditions")
    rule.match = match_col.selectbox(
        "Match mode",
        ["all", "any"],
        index=0 if rule.match == "all" else 1,
        format_func=lambda value: "ALL conditions" if value == "all" else "ANY condition",
        key=f"match_{revision}",
    )

    if not rule.fields:
        st.warning("Add an available data field before creating a condition.")
        return

    field_keys = [field.key for field in rule.fields]
    for index, condition in enumerate(list(rule.conditions), start=1):
        if condition.field not in field_keys:
            condition.field = field_keys[0]
        with st.container(border=True):
            index_col, field_col, operator_col, value_col, remove_col = st.columns([.18, 1.7, 1.2, 1.1, .3])
            index_col.markdown(f"**{index}**")
            condition.field = field_col.selectbox(
                "Field",
                field_keys,
                index=field_keys.index(condition.field),
                format_func=lambda key: field_by_key(rule, key).label,
                key=f"condition_field_{revision}_{condition.id}",
                label_visibility="collapsed",
            )
            definition = field_by_key(rule, condition.field)
            operators = TYPE_OPERATORS.get(definition.data_type, TYPE_OPERATORS["text"])
            if condition.operator not in operators:
                condition.operator = operators[0]
            condition.operator = operator_col.selectbox(
                "Comparison",
                operators,
                index=operators.index(condition.operator),
                format_func=lambda value: OPERATOR_LABELS[value],
                key=f"condition_operator_{revision}_{condition.id}_{condition.field}",
                label_visibility="collapsed",
            )
            with value_col:
                condition.value = render_value_input(definition, condition, revision)
            if remove_col.button(
                "×",
                key=f"remove_condition_{revision}_{condition.id}",
                help="Remove this condition",
                use_container_width=True,
            ):
                rule.conditions = [item for item in rule.conditions if item.id != condition.id]
                st.rerun()

    if st.button("＋ Add another condition", key=f"add_condition_{revision}"):
        rule.conditions.append(Condition(field=field_keys[0], operator="equals", value=None))
        st.rerun()


def render_outcome_builder(rule: Rule, revision: int) -> None:
    st.markdown("### Outcome")
    current_kind = rule.outcome.kind if rule.outcome.kind in OUTCOME_KINDS else OUTCOME_KINDS[0]
    rule.outcome.kind = st.selectbox(
        "Type",
        OUTCOME_KINDS,
        index=OUTCOME_KINDS.index(current_kind),
        key=f"outcome_kind_{revision}",
    )
    rule.outcome.value = st.text_input(
        "Value",
        value=rule.outcome.value,
        placeholder="e.g. Manual review, Priority support, 15% off",
        key=f"outcome_value_{revision}",
    )
    rule.outcome.message = st.text_area(
        "Message / payload",
        value=rule.outcome.message,
        placeholder="Optional output context",
        key=f"outcome_message_{revision}",
        height=82,
    )


def render_build_page() -> None:
    rule: Rule = st.session_state.draft_rule
    revision: int = st.session_state.draft_revision

    title_col, new_col, template_col, save_col, test_col = st.columns([3, .75, .9, .8, .8])
    with title_col:
        st.markdown("## Rule editor")
        st.caption(f"Rule ID · {rule.id[:12]}")
    if new_col.button("New", use_container_width=True):
        set_draft(blank_rule(rule.fields))
        st.rerun()
    with template_col:
        render_template_picker()
    save_requested = save_col.button("Save", type="primary", use_container_width=True)
    test_requested = test_col.button("Test", use_container_width=True)

    name_col, priority_col, enabled_col = st.columns([3, .7, .7])
    rule.name = name_col.text_input(
        "Rule name",
        value=rule.name,
        placeholder="Rule name",
        key=f"rule_name_{revision}",
    )
    rule.priority = int(
        priority_col.number_input(
            "Priority",
            min_value=1,
            max_value=9999,
            value=int(rule.priority),
            help="Lower values evaluate first.",
            key=f"priority_{revision}",
        )
    )
    with enabled_col:
        st.write("")
        st.write("")
        rule.enabled = st.toggle(
            "Active",
            value=rule.enabled,
            key=f"enabled_{revision}",
        )
    rule.description = st.text_input(
        "Description",
        value=rule.description,
        placeholder="Optional operational context",
        key=f"rule_description_{revision}",
    )

    render_field_manager(rule, revision)

    conditions_col, outcome_col = st.columns([1.75, 1], gap="large")
    with conditions_col:
        render_condition_builder(rule, revision)
    with outcome_col:
        render_outcome_builder(rule, revision)
        render_logic_preview(rule)

    errors = validate_rule(rule)
    if errors:
        with outcome_col.container(border=True):
            st.markdown("**Validation**")
            for error in errors:
                st.markdown(f"- {error}")

    if save_requested:
        save_current_rule()
        st.rerun()
    if test_requested:
        if save_current_rule():
            st.session_state.test_rule_id = rule.id
            st.session_state.go_to_test = True
        st.rerun()


def matching_template(rule: Rule) -> dict | None:
    keys = {field.key for field in rule.fields}
    for template in TEMPLATES.values():
        if keys == {field["key"] for field in template["fields"]}:
            return template
    return None


def load_test_sample(rule: Rule, record: dict) -> None:
    for field in rule.fields:
        st.session_state[f"test_value_{rule.id}_{field.key}"] = record.get(field.key, field.example)


def render_test_input(rule: Rule, field: FieldDefinition) -> object:
    key = f"test_value_{rule.id}_{field.key}"
    default = field.example
    if field.data_type == "number":
        try:
            number = float(default or 0)
        except (TypeError, ValueError):
            number = 0.0
        number_kwargs = {"step": 1.0, "key": key}
        if key not in st.session_state:
            number_kwargs["value"] = number
        return st.number_input(field.label, **number_kwargs)
    if field.data_type == "boolean":
        default_bool = bool(default)
        boolean_kwargs = {
            "format_func": lambda item: "Yes" if item else "No",
            "key": key,
        }
        if key not in st.session_state:
            boolean_kwargs["index"] = 0 if default_bool else 1
        return st.selectbox(field.label, [True, False], **boolean_kwargs)
    if field.choices:
        options = field.choices
        index = options.index(default) if default in options else 0
        choice_kwargs = {"key": key}
        if key not in st.session_state:
            choice_kwargs["index"] = index
        return st.selectbox(field.label, options, **choice_kwargs)
    text_kwargs = {"key": key}
    if key not in st.session_state:
        text_kwargs["value"] = str(default or "")
    return st.text_input(field.label, **text_kwargs)


def render_test_page() -> None:
    st.markdown("## Test bench")
    rules: list[Rule] = st.session_state.rules
    if not rules:
        st.markdown('<div class="empty-state">No saved rules available.</div>', unsafe_allow_html=True)
        return

    rule_ids = [rule.id for rule in rules]
    selected_id = st.session_state.get("test_rule_id")
    if selected_id not in rule_ids:
        selected_id = rule_ids[0]
        st.session_state.test_rule_id = selected_id
    selected_id = st.selectbox(
        "Rule to test",
        rule_ids,
        format_func=lambda rule_id: next(rule.name for rule in rules if rule.id == rule_id),
        key="test_rule_id",
    )
    rule = next(item for item in rules if item.id == selected_id)
    render_logic_preview(rule)

    template = matching_template(rule)
    if template:
        match_col, miss_col, _ = st.columns([.9, .9, 2.2])
        match_col.button(
            "Load match fixture",
            on_click=load_test_sample,
            args=(rule, template["matching_sample"]),
            use_container_width=True,
        )
        miss_col.button(
            "Load miss fixture",
            on_click=load_test_sample,
            args=(rule, template["non_matching_sample"]),
            use_container_width=True,
        )

    input_col, result_col = st.columns([1.1, 1], gap="large")
    with input_col:
        st.markdown("### Input")
        record: dict[str, object] = {}
        for field in rule.fields:
            record[field.key] = render_test_input(rule, field)
        with st.expander("JSON payload"):
            st.json(record)

    with result_col:
        st.markdown("### Decision")
        result = evaluate_rule(rule, record)
        if result.matched:
            st.success(f"Rule matched — {rule.outcome.kind}: {rule.outcome.value}", icon="✅")
            if rule.outcome.message:
                st.info(rule.outcome.message, icon="➡️")
        else:
            st.info("Rule did not match. No outcome was applied.", icon="ℹ️")
        if not rule.enabled:
            st.warning("Inactive rule: excluded from rulebook evaluation.")
        st.markdown("**Condition trace**")
        for condition_result in result.condition_results:
            css_class = "trace-pass" if condition_result.matched else "trace-fail"
            symbol = "✓" if condition_result.matched else "×"
            st.markdown(
                f'<div class="{css_class}"><b>{symbol}</b>&nbsp; {html.escape(condition_result.explanation)}</div>',
                unsafe_allow_html=True,
            )
        match_word = "every" if rule.match == "all" else "at least one"
        st.caption(f"Match mode: {match_word} condition must pass.")


def duplicate_rule(rule: Rule) -> None:
    copy = clone_rule(rule)
    copy.id = uuid4().hex
    copy.name = f"{copy.name} (copy)"
    for condition in copy.conditions:
        condition.id = uuid4().hex[:10]
    st.session_state.rules.append(copy)
    safe_persist()
    flash(f"Duplicated “{rule.name}”.")


def delete_rule(rule_id: str) -> None:
    rule = next((item for item in st.session_state.rules if item.id == rule_id), None)
    st.session_state.rules = [item for item in st.session_state.rules if item.id != rule_id]
    safe_persist()
    if rule:
        flash(f"Deleted “{rule.name}”.", "warning")


def render_library_page() -> None:
    title_col, button_col = st.columns([3, 1])
    with title_col:
        st.markdown("## Rules")
    with button_col:
        st.write("")
        if st.button("＋ New rule", type="primary", use_container_width=True):
            current_fields = st.session_state.draft_rule.fields
            set_draft(blank_rule(current_fields))
            st.session_state.go_to_build = True
            st.rerun()

    rules: list[Rule] = sorted(st.session_state.rules, key=lambda item: item.priority)
    if not rules:
        st.markdown(
            '<div class="empty-state">No rules in this rulebook.</div>',
            unsafe_allow_html=True,
        )
        return

    active = sum(rule.enabled for rule in rules)
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Total rules", len(rules))
    col_b.metric("Active", active)
    col_c.metric("Next priority", min(rule.priority for rule in rules))
    st.write("")

    for rule in rules:
        with st.container(border=True):
            content_col, priority_col, action_col = st.columns([4, .8, 1.45])
            with content_col:
                status_class = "status-live" if rule.enabled else "status-draft"
                status_text = "ACTIVE" if rule.enabled else "INACTIVE"
                st.markdown(
                    f"### {html.escape(rule.name)} <span class=\"status-chip {status_class}\">{status_text}</span>",
                    unsafe_allow_html=True,
                )
                if rule.description:
                    st.caption(rule.description)
                conditions, result = rule_sentence(rule)
                st.markdown(f"**When** {conditions}  \n**Then** {result}")
                if rule.tags:
                    st.markdown(
                        "".join(f'<span class="mini-tag">{html.escape(tag)}</span>' for tag in rule.tags),
                        unsafe_allow_html=True,
                    )
            with priority_col:
                st.caption("PRIORITY")
                st.markdown(f"### {rule.priority}")
            with action_col:
                if st.button("Edit", key=f"edit_{rule.id}", use_container_width=True):
                    edit_rule(rule.id)
                    st.rerun()
                copy_col, delete_col = st.columns(2)
                if copy_col.button("Copy", key=f"copy_{rule.id}", use_container_width=True):
                    duplicate_rule(rule)
                    st.rerun()
                with delete_col.popover("Delete", use_container_width=True):
                    st.markdown(f"Delete **{rule.name}**?")
                    st.caption("This removes it from the local rulebook.")
                    if st.button("Yes, delete", key=f"confirm_delete_{rule.id}", type="primary"):
                        delete_rule(rule.id)
                        st.rerun()


def main() -> None:
    inject_styles()
    initialise_state()
    render_sidebar()
    render_header()
    show_flash()

    if st.session_state.navigation == NAV_OPTIONS[0]:
        render_build_page()
    elif st.session_state.navigation == NAV_OPTIONS[1]:
        render_test_page()
    else:
        render_library_page()

    st.markdown(
        '<div class="footer-note">Rules Engine Studio</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
