"""
Starter data and canonical ruleset metadata for the studio.

The studio opens on something that already evaluates, so the first thing an
author sees is a working example rather than an empty form.
"""

from __future__ import annotations

import io
import json
from typing import Any

import pandas as pd

from .schema import (
    Assignment,
    Condition,
    ConditionGroup,
    Operand,
    Rule,
    Ruleset,
)

DEMO_ROWS: list[dict[str, Any]] = [
    {
        "employee_id": "E1001",
        "job_family": "Engineering",
        "job_level": 5,
        "cost_centre": "CC-100",
        "region": "APAC",
        "fte": 1.0,
        "contract_type": "permanent",
    },
    {
        "employee_id": "E1002",
        "job_family": "Engineering",
        "job_level": 2,
        "cost_centre": "CC-100",
        "region": "EMEA",
        "fte": 0.6,
        "contract_type": "permanent",
    },
    {
        "employee_id": "E1003",
        "job_family": "Finance",
        "job_level": 4,
        "cost_centre": "CC-220",
        "region": "AMER",
        "fte": 1.0,
        "contract_type": "contractor",
    },
    {
        "employee_id": "E1004",
        "job_family": "Support",
        "job_level": 1,
        "cost_centre": "CC-310",
        "region": "APAC",
        "fte": 0.5,
        "contract_type": "casual",
    },
    {
        "employee_id": "E1005",
        "job_family": "Engineering",
        "job_level": 7,
        "cost_centre": "CC-101",
        "region": "AMER",
        "fte": 1.0,
        "contract_type": "permanent",
    },
]


def demo_frame() -> pd.DataFrame:
    """Return the editable starter rows as a pandas DataFrame."""
    return pd.DataFrame(DEMO_ROWS)


def _field(name: str) -> Operand:
    """Return a field operand for starter metadata."""
    return Operand(kind="field", field_name=name)


def _lit(value: Any, value_type: str = "string") -> Operand:
    """Return a typed literal operand for starter metadata."""
    return Operand(kind="literal", value=value, value_type=value_type)


def demo_ruleset() -> Ruleset:
    """Return a valid canonical starter ruleset with representative behavior."""
    senior_engineering = Rule(
        rule_id="senior_engineering",
        rule_name="Senior engineering",
        description="Senior engineering roles roll up to the engineering leadership node.",
        rule_order=10,
        stop_on_match=False,
        conditions=ConditionGroup(
            logical_operator="all",
            children=[
                Condition(
                    condition_id="condition:senior_engineering:family",
                    left=_field("job_family"),
                    operator="eq",
                    right=_lit("Engineering"),
                ),
                Condition(
                    condition_id="condition:senior_engineering:level",
                    left=_field("job_level"),
                    operator="ge",
                    right=_lit(5, "integer"),
                ),
            ],
            condition_group_id="group:senior_engineering:root",
        ),
        assignments=[
            Assignment(
                assignment_id="assignment:senior_engineering:hierarchy_node",
                target_field="hierarchy_node",
                value=_lit("ENG.LEADERSHIP"),
            ),
            Assignment(
                assignment_id="assignment:senior_engineering:review_tier",
                target_field="review_tier",
                value=_lit("tier_1"),
            ),
        ],
    )

    part_time = Rule(
        rule_id="part_time_override",
        rule_name="Part-time override",
        description="Part-time and casual staff are reviewed one tier lower, whatever else matched.",
        rule_order=20,
        conditions=ConditionGroup(
            logical_operator="any",
            children=[
                Condition(
                    condition_id="condition:part_time_override:fte",
                    left=_field("fte"),
                    operator="lt",
                    right=_lit(0.8, "decimal"),
                ),
                Condition(
                    condition_id="condition:part_time_override:contract_type",
                    left=_field("contract_type"),
                    operator="in",
                    right=_lit(["casual", "contractor"], "list"),
                ),
            ],
            condition_group_id="group:part_time_override:root",
        ),
        assignments=[
            Assignment(
                assignment_id="assignment:part_time_override:review_tier",
                target_field="review_tier",
                value=_lit("tier_3"),
            )
        ],
    )

    fallback = Rule(
        rule_id="unclassified_fallback",
        rule_name="Unclassified fallback",
        description="Anything still unmatched lands in the review queue and stops here.",
        rule_order=30,
        stop_on_match=True,
        conditions=ConditionGroup(
            logical_operator="all",
            children=[
                Condition(
                    condition_id="condition:unclassified_fallback:family_present",
                    left=_field("job_family"),
                    operator="is_not_null",
                    right=None,
                ),
            ],
            condition_group_id="group:unclassified_fallback:root",
        ),
        assignments=[
            Assignment(
                assignment_id="assignment:unclassified_fallback:leaf_key",
                target_field="leaf_key",
                value=Operand(
                    kind="custom_function",
                    function="concat_ws",
                    args={
                        "values": [_field("cost_centre"), _field("job_family")],
                        "separator": "/",
                    },
                ),
            )
        ],
    )

    return Ruleset(
        ruleset_id="position_hierarchy",
        ruleset_name="Position hierarchy",
        version="0.1.0",
        description="Starter ruleset -- edit or replace with your own.",
        owner="Rules Team",
        owner_department="People Analytics",
        rules=[senior_engineering, part_time, fallback],
    )


# --------------------------------------------------------------------------
# import helpers
# --------------------------------------------------------------------------


def read_uploaded(name: str, data: bytes) -> pd.DataFrame:
    """
    Parse an uploaded test-data file.

    Parameters
    ----------
    name : str
        Uploaded file name used to select the parser.
    data : bytes
        Uploaded file content.

    Returns
    -------
    pandas.DataFrame
        Parsed test rows.
    """
    lowered = name.lower()
    if lowered.endswith(".csv"):
        return pd.read_csv(io.BytesIO(data))
    if lowered.endswith(".tsv"):
        return pd.read_csv(io.BytesIO(data), sep="\t")
    if lowered.endswith(".json"):
        return pd.DataFrame(json.loads(data.decode("utf-8")))
    if lowered.endswith(".parquet"):
        return pd.read_parquet(io.BytesIO(data))
    raise ValueError("Supported sample data formats: .csv, .tsv, .json, .parquet")


def read_pasted_json(text: str) -> pd.DataFrame:
    """Parse pasted JSON object or array data into editable test rows."""
    parsed = json.loads(text)
    if isinstance(parsed, dict):
        parsed = [parsed]
    return pd.DataFrame(parsed)
