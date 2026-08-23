"""Sample data: the rows every preview and test runs against."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import sample_data, state
from ..schema import referenced_columns


def render() -> None:
    st.subheader("Sample data")
    st.caption(
        "A handful of representative rows is enough. Everything the studio evaluates — "
        "single conditions, single rules, the whole ruleset — runs against these."
    )

    _coverage()

    edited = st.data_editor(
        state.frame(),
        num_rows="dynamic",
        use_container_width=True,
        key="sample_editor",
    )
    if isinstance(edited, pd.DataFrame):
        state.set_frame(edited)

    st.divider()
    cols = st.columns([2, 2, 1])

    with cols[0]:
        st.markdown("**Load a file**")
        upload = st.file_uploader(
            "CSV, TSV, JSON or Parquet",
            type=["csv", "tsv", "json", "parquet"],
            key="sample_upload",
            label_visibility="collapsed",
        )
        if upload is not None and st.button("Replace sample data", key="do_upload"):
            try:
                frame = sample_data.read_uploaded(upload.name, upload.getvalue())
            except Exception as exc:
                st.error(f"Could not read {upload.name}: {exc}")
            else:
                state.set_frame(frame)
                st.rerun()

    with cols[1]:
        st.markdown("**Paste rows**")
        pasted = st.text_area(
            "JSON array of objects",
            key="sample_paste",
            height=120,
            placeholder='[{"job_family": "Engineering", "job_level": 5}]',
            label_visibility="collapsed",
        )
        if pasted.strip() and st.button("Use pasted rows", key="do_paste"):
            try:
                frame = sample_data.read_pasted_json(pasted)
            except Exception as exc:
                st.error(f"Could not read that JSON: {exc}")
            else:
                state.set_frame(frame)
                st.rerun()

    with cols[2]:
        st.markdown("**Start over**")
        if st.button("Restore demo rows", key="do_demo"):
            state.set_frame(sample_data.demo_frame())
            st.rerun()

    st.caption(
        "Sample data stays in this browser session. Nothing is written back to a table."
    )


def _coverage() -> None:
    needed = referenced_columns(state.draft())
    have = set(state.columns())
    missing = sorted(needed - have)
    unused = sorted(have - needed)

    cols = st.columns([1, 1, 2])
    cols[0].metric("Rows", len(state.frame()))
    cols[1].metric("Columns read by rules", len(needed))
    with cols[2]:
        if missing:
            st.error("Rules read columns that are not here: " + ", ".join(missing))
        elif needed:
            st.success("Every column the rules read is present.")
        if unused:
            st.caption("Not read by any rule: " + ", ".join(unused))
