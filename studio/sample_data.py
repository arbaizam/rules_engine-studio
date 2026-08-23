"""Starter content: a small position-hierarchy dataset and a matching ruleset.

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
    return pd.DataFrame(DEMO_ROWS)


def _field(name: str) -> Operand:
    return Operand(kind="field", field_name=name)


def _lit(value: Any, value_type: str = "string") -> Operand:
    return Operand(kind="literal", value=value, value_type=value_type)


def demo_ruleset() -> Ruleset:
    senior_engineering = Rule(
        rule_id="senior_engineering",
        description="Senior engineering roles roll up to the engineering leadership node.",
        rule_order=10,
        stop_on_match=False,
        conditions=ConditionGroup(
            logic="all",
            children=[
                Condition(left=_field("job_family"), operator="equals", right=_lit("Engineering")),
                Condition(
                    left=_field("job_level"),
                    operator="greater_than_or_equal",
                    right=_lit(5, "integer"),
                ),
            ],
        ),
        assignments=[
            Assignment(target_field="hierarchy_node", value=_lit("ENG.LEADERSHIP")),
            Assignment(target_field="review_tier", value=_lit("tier_1")),
        ],
    )

    part_time = Rule(
        rule_id="part_time_override",
        description="Part-time and casual staff are reviewed one tier lower, whatever else matched.",
        rule_order=20,
        conditions=ConditionGroup(
            logic="any",
            children=[
                Condition(
                    left=_field("fte"), operator="less_than", right=_lit(0.8, "number")
                ),
                Condition(
                    left=_field("contract_type"),
                    operator="in_list",
                    right=_lit(["casual", "contractor"], "list"),
                ),
            ],
        ),
        assignments=[Assignment(target_field="review_tier", value=_lit("tier_3"))],
    )

    fallback = Rule(
        rule_id="unclassified_fallback",
        description="Anything still unmatched lands in the review queue and stops here.",
        rule_order=30,
        stop_on_match=True,
        conditions=ConditionGroup(
            logic="all",
            children=[
                Condition(left=_field("job_family"), operator="is_not_null", right=None),
            ],
        ),
        assignments=[
            Assignment(
                target_field="leaf_key",
                value=Operand(
                    kind="function",
                    function="leaf_key",
                    args=[_field("cost_centre"), _field("job_family")],
                ),
            )
        ],
    )

    return Ruleset(
        ruleset_id="position_hierarchy",
        version="0.1.0",
        description="Starter ruleset -- edit or replace with your own.",
        published_by="",
        published_at="",
        rules=[senior_engineering, part_time, fallback],
    )


# --------------------------------------------------------------------------
# import helpers
# --------------------------------------------------------------------------


def read_uploaded(name: str, data: bytes) -> pd.DataFrame:
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
    parsed = json.loads(text)
    if isinstance(parsed, dict):
        parsed = [parsed]
    return pd.DataFrame(parsed)
