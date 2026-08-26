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
        "EffectiveDate": "8/14/2026",
        "Extract": "FullExtract",
        "LoanNo": "XXXX4",
        "OriginationDate": "1/1/2020",
        "FirstPaymentDate": "1/1/2010",
        "IntRate": 1.50,
        "BackEndDTI": None,
        "CurrentDSCR": 1.12,
        "CurrentDSCRDate": "12/31/2025",
        "OriginalFICO": None,
        "CurrentFICO": None,
        "LoanPurpose": "Purchase",
        "RefinanceType": None,
        "IsDSCR": True,
        "StructColumn": {
            "risk_band": "Low",
            "source": "MockServicing",
            "manual_review": False,
        },
        "ArrayColumn": ["DSCR", "Purchase"],
    },
    {
        "EffectiveDate": "8/14/2026",
        "Extract": "FullExtract",
        "LoanNo": "XXXX5",
        "OriginationDate": "1/1/2006",
        "FirstPaymentDate": None,
        "IntRate": 1.00,
        "BackEndDTI": None,
        "CurrentDSCR": 1.26,
        "CurrentDSCRDate": "12/31/2025",
        "OriginalFICO": None,
        "CurrentFICO": None,
        "LoanPurpose": "Purchase",
        "RefinanceType": "Cash Out",
        "IsDSCR": True,
        "StructColumn": {
            "risk_band": "Medium",
            "source": "MockServicing",
            "manual_review": False,
        },
        "ArrayColumn": ["DSCR", "Purchase", "CashOut"],
    },
    {
        "EffectiveDate": "8/14/2026",
        "Extract": "FullExtract",
        "LoanNo": "XXXX6",
        "OriginationDate": "1/10/2020",
        "FirstPaymentDate": "3/10/2021",
        "IntRate": 5.50,
        "BackEndDTI": None,
        "CurrentDSCR": 1.32,
        "CurrentDSCRDate": "12/31/2025",
        "OriginalFICO": None,
        "CurrentFICO": None,
        "LoanPurpose": "Refinance",
        "RefinanceType": "No Cash Out",
        "IsDSCR": True,
        "StructColumn": {
            "risk_band": "Low",
            "source": "MockServicing",
            "manual_review": False,
        },
        "ArrayColumn": ["DSCR", "Refinance", "NoCashOut"],
    },
    {
        "EffectiveDate": "8/14/2026",
        "Extract": "FullExtract",
        "LoanNo": "XXXX7",
        "OriginationDate": "2/5/2017",
        "FirstPaymentDate": None,
        "IntRate": None,
        "BackEndDTI": None,
        "CurrentDSCR": 1.33,
        "CurrentDSCRDate": "8/29/2025",
        "OriginalFICO": 779,
        "CurrentFICO": None,
        "LoanPurpose": "Refinance",
        "RefinanceType": None,
        "IsDSCR": True,
        "StructColumn": {
            "risk_band": "Low",
            "source": "MockServicing",
            "manual_review": False,
        },
        "ArrayColumn": ["DSCR", "Refinance"],
    },
    {
        "EffectiveDate": "8/14/2026",
        "Extract": "FullExtract",
        "LoanNo": "XXXX8",
        "OriginationDate": "6/1/2017",
        "FirstPaymentDate": None,
        "IntRate": 6.00,
        "BackEndDTI": 23.327,
        "CurrentDSCR": None,
        "CurrentDSCRDate": "3/30/2026",
        "OriginalFICO": 729,
        "CurrentFICO": None,
        "LoanPurpose": "Refinance",
        "RefinanceType": None,
        "IsDSCR": True,
        "StructColumn": {
            "risk_band": "Medium",
            "source": "MockServicing",
            "manual_review": True,
        },
        "ArrayColumn": ["DSCR", "MissingDSCR", "Watch"],
    },
    {
        "EffectiveDate": "8/14/2026",
        "Extract": "FullExtract",
        "LoanNo": "XXXX9",
        "OriginationDate": "1/1/2006",
        "FirstPaymentDate": None,
        "IntRate": 4.99,
        "BackEndDTI": 23.327,
        "CurrentDSCR": None,
        "CurrentDSCRDate": None,
        "OriginalFICO": 690,
        "CurrentFICO": None,
        "LoanPurpose": "Purchase",
        "RefinanceType": None,
        "IsDSCR": False,
        "StructColumn": {
            "risk_band": "High",
            "source": "MockServicing",
            "manual_review": True,
        },
        "ArrayColumn": ["NonDSCR", "Purchase", "Watch"],
    },
    {
        "EffectiveDate": "8/14/2026",
        "Extract": "FullExtract",
        "LoanNo": "XXXX10",
        "OriginationDate": "1/1/2006",
        "FirstPaymentDate": None,
        "IntRate": 4.55,
        "BackEndDTI": 47.957,
        "CurrentDSCR": None,
        "CurrentDSCRDate": None,
        "OriginalFICO": 737,
        "CurrentFICO": None,
        "LoanPurpose": "Purchase",
        "RefinanceType": None,
        "IsDSCR": False,
        "StructColumn": {
            "risk_band": "High",
            "source": "MockServicing",
            "manual_review": True,
        },
        "ArrayColumn": ["NonDSCR", "Purchase", "Watch"],
    },
    {
        "EffectiveDate": "8/14/2026",
        "Extract": "PartialExtract",
        "LoanNo": "XXXX11",
        "OriginationDate": None,
        "FirstPaymentDate": None,
        "IntRate": 6.78,
        "BackEndDTI": 25.6,
        "CurrentDSCR": None,
        "CurrentDSCRDate": None,
        "OriginalFICO": None,
        "CurrentFICO": None,
        "LoanPurpose": "Purchase",
        "RefinanceType": None,
        "IsDSCR": False,
        "StructColumn": {
            "risk_band": "Medium",
            "source": "MockServicing",
            "manual_review": True,
        },
        "ArrayColumn": ["NonDSCR", "PartialExtract"],
    },
    {
        "EffectiveDate": "8/14/2026",
        "Extract": "PartialExtract",
        "LoanNo": "XXXX12",
        "OriginationDate": "1/1/2006",
        "FirstPaymentDate": None,
        "IntRate": 8.85,
        "BackEndDTI": 25.6,
        "CurrentDSCR": None,
        "CurrentDSCRDate": None,
        "OriginalFICO": None,
        "CurrentFICO": None,
        "LoanPurpose": "Refinance",
        "RefinanceType": None,
        "IsDSCR": False,
        "StructColumn": {
            "risk_band": "Medium",
            "source": "MockServicing",
            "manual_review": True,
        },
        "ArrayColumn": ["NonDSCR", "PartialExtract"],
    },
    {
        "EffectiveDate": "8/14/2026",
        "Extract": "PartialExtract",
        "LoanNo": "XXXX13",
        "OriginationDate": None,
        "FirstPaymentDate": None,
        "IntRate": 4.45,
        "BackEndDTI": None,
        "CurrentDSCR": None,
        "CurrentDSCRDate": None,
        "OriginalFICO": None,
        "CurrentFICO": None,
        "LoanPurpose": "Refinance",
        "RefinanceType": None,
        "IsDSCR": False,
        "StructColumn": {
            "risk_band": "High",
            "source": "MockServicing",
            "manual_review": True,
        },
        "ArrayColumn": ["NonDSCR", "PartialExtract", "Watch"],
    },
]


def demo_frame() -> pd.DataFrame:
    """Return the editable starter rows as a pandas DataFrame."""
    return _parse_date_columns(pd.DataFrame(DEMO_ROWS))


def _field(name: str) -> Operand:
    """Return a field operand for starter metadata."""
    return Operand(kind="field", field_name=name)


def _lit(value: Any, value_type: str = "string") -> Operand:
    """Return a typed literal operand for starter metadata."""
    return Operand(kind="literal", value=value, value_type=value_type)


def _available_fico() -> Operand:
    """Return the current FICO with original FICO as the fallback."""
    return Operand(
        kind="custom_function",
        function="coalesce",
        args={"values": [_field("CurrentFICO"), _field("OriginalFICO")]},
    )


def demo_ruleset() -> Ruleset:
    """Return a valid canonical starter ruleset with representative behavior."""
    eligibility = Rule(
        rule_id="eligibility",
        rule_name="Eligibility",
        description=(
            "Deem a loan ineligible when its current-or-original FICO is below 620 or "
            "unavailable, or CurrentDSCR is below 1.20."
        ),
        rule_order=10,
        stop_on_match=True,
        conditions=ConditionGroup(
            logical_operator="any",
            children=[
                Condition(
                    condition_id="condition:eligibility:fico_below_minimum",
                    left=_available_fico(),
                    operator="lt",
                    right=_lit(620, "integer"),
                ),
                Condition(
                    condition_id="condition:eligibility:fico_missing",
                    left=_available_fico(),
                    operator="is_null",
                    right=None,
                ),
                Condition(
                    condition_id="condition:eligibility:dscr_below_minimum",
                    left=_field("CurrentDSCR"),
                    operator="lt",
                    right=_lit("1.2", "decimal"),
                ),
            ],
            condition_group_id="group:eligibility:root",
        ),
        assignments=[
            Assignment(
                assignment_id="assignment:eligibility:review_status",
                target_field="ReviewStatus",
                value=_lit("Ineligible"),
            ),
            Assignment(
                assignment_id="assignment:eligibility:audit_tags",
                target_field="AuditTags",
                value=_lit(["Eligibility", "Ineligible"], "array"),
            ),
            Assignment(
                assignment_id="assignment:eligibility:decision_detail",
                target_field="DecisionDetail",
                value=_lit(
                    {
                        "status": "ineligible",
                        "policy": "FICO < 620 or missing, or CurrentDSCR < 1.20",
                    },
                    "struct",
                ),
            ),
        ],
    )

    dscr_coverage = Rule(
        rule_id="dscr_coverage_met",
        rule_name="DSCR coverage met",
        description="Approve current DSCR loans at or above the coverage threshold.",
        rule_order=20,
        conditions=ConditionGroup(
            logical_operator="all",
            children=[
                Condition(
                    condition_id="condition:dscr_coverage_met:is_dscr",
                    left=_field("IsDSCR"),
                    operator="eq",
                    right=_lit(True, "boolean"),
                ),
                Condition(
                    condition_id="condition:dscr_coverage_met:coverage",
                    left=_field("CurrentDSCR"),
                    operator="ge",
                    right=_lit("1.25", "decimal"),
                ),
                Condition(
                    condition_id="condition:dscr_coverage_met:measurement_date",
                    left=_field("CurrentDSCRDate"),
                    operator="ge",
                    right=_lit("2025-01-01", "date"),
                ),
            ],
            condition_group_id="group:dscr_coverage_met:root",
        ),
        assignments=[
            Assignment(
                assignment_id="assignment:dscr_coverage_met:review_status",
                target_field="ReviewStatus",
                value=_lit("Eligible"),
            ),
            Assignment(
                assignment_id="assignment:dscr_coverage_met:audit_tags",
                target_field="AuditTags",
                value=_lit(["DSCR", "CoverageMet"], "array"),
            ),
            Assignment(
                assignment_id="assignment:dscr_coverage_met:decision_detail",
                target_field="DecisionDetail",
                value=_lit(
                    {
                        "status": "eligible",
                        "basis": "CurrentDSCR",
                        "threshold": 1.25,
                    },
                    "struct",
                ),
            ),
        ],
    )

    non_dscr_risk = Rule(
        rule_id="non_dscr_risk_review",
        rule_name="Non-DSCR risk review",
        description="Route non-DSCR loans with elevated DTI or lower FICO to review.",
        rule_order=30,
        conditions=ConditionGroup(
            logical_operator="all",
            children=[
                Condition(
                    condition_id="condition:non_dscr_risk_review:is_dscr",
                    left=_field("IsDSCR"),
                    operator="eq",
                    right=_lit(False, "boolean"),
                ),
                ConditionGroup(
                    condition_group_id="group:non_dscr_risk_review:thresholds",
                    logical_operator="any",
                    children=[
                        Condition(
                            condition_id="condition:non_dscr_risk_review:dti",
                            left=_field("BackEndDTI"),
                            operator="gt",
                            right=_lit(43, "integer"),
                        ),
                        Condition(
                            condition_id="condition:non_dscr_risk_review:fico",
                            left=_field("OriginalFICO"),
                            operator="lt",
                            right=_lit(700, "integer"),
                        ),
                    ],
                ),
            ],
            condition_group_id="group:non_dscr_risk_review:root",
        ),
        assignments=[
            Assignment(
                assignment_id="assignment:non_dscr_risk_review:review_status",
                target_field="ReviewStatus",
                value=_lit("Manual Review"),
            ),
            Assignment(
                assignment_id="assignment:non_dscr_risk_review:audit_tags",
                target_field="AuditTags",
                value=_lit(["NonDSCR", "RiskThreshold"], "array"),
            ),
        ],
    )

    partial_extract = Rule(
        rule_id="partial_extract_review",
        rule_name="Partial extract review",
        description="Require data completion when only a partial extract is available.",
        rule_order=40,
        conditions=ConditionGroup(
            logical_operator="all",
            children=[
                Condition(
                    condition_id="condition:partial_extract_review:extract",
                    left=_field("Extract"),
                    operator="eq",
                    right=_lit("PartialExtract"),
                )
            ],
            condition_group_id="group:partial_extract_review:root",
        ),
        assignments=[
            Assignment(
                assignment_id="assignment:partial_extract_review:review_status",
                target_field="ReviewStatus",
                value=_lit("Data Required"),
            ),
            Assignment(
                assignment_id="assignment:partial_extract_review:audit_tags",
                target_field="AuditTags",
                value=_lit(["PartialExtract", "MissingData"], "array"),
            ),
        ],
    )

    structured_metadata = Rule(
        rule_id="structured_metadata_review",
        rule_name="Structured metadata review",
        description="Exercise array and struct comparisons against mock servicing metadata.",
        rule_order=50,
        conditions=ConditionGroup(
            logical_operator="any",
            children=[
                Condition(
                    condition_id="condition:structured_metadata_review:watch_tag",
                    left=_field("ArrayColumn"),
                    operator="contains",
                    right=_lit("Watch"),
                ),
                Condition(
                    condition_id="condition:structured_metadata_review:high_risk_struct",
                    left=_field("StructColumn"),
                    operator="eq",
                    right=_lit(
                        {
                            "risk_band": "High",
                            "source": "MockServicing",
                            "manual_review": True,
                        },
                        "struct",
                    ),
                ),
            ],
            condition_group_id="group:structured_metadata_review:root",
        ),
        assignments=[
            Assignment(
                assignment_id="assignment:structured_metadata_review:structured_match",
                target_field="StructuredMatch",
                value=_lit(True, "boolean"),
            )
        ],
    )

    return Ruleset(
        ruleset_id="loan_review",
        ruleset_name="Loan review",
        version="0.2.0",
        description="Loan review examples for rule authoring and audit testing.",
        owner="Rules Team",
        owner_department="Credit Risk",
        rules=[
            eligibility,
            dscr_coverage,
            non_dscr_risk,
            partial_extract,
            structured_metadata,
        ],
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
        return _parse_date_columns(pd.read_csv(io.BytesIO(data)))
    if lowered.endswith(".tsv"):
        return _parse_date_columns(pd.read_csv(io.BytesIO(data), sep="\t"))
    if lowered.endswith(".json"):
        return pd.DataFrame(json.loads(data.decode("utf-8")))
    if lowered.endswith(".parquet"):
        return pd.read_parquet(io.BytesIO(data))
    raise ValueError("Supported sample data formats: .csv, .tsv, .json, .parquet")


def _parse_date_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Parse CSV-like columns containing ``date`` into Python date values."""
    parsed_frame = frame.copy()
    for column_name in parsed_frame.columns:
        if "date" not in str(column_name).lower():
            continue
        parsed = pd.to_datetime(
            parsed_frame[column_name],
            errors="coerce",
            format="mixed",
        )
        values = parsed.dt.date.astype("object")
        parsed_frame[column_name] = values.where(parsed.notna(), None)
    return parsed_frame


def read_pasted_json(text: str) -> pd.DataFrame:
    """Parse pasted JSON object or array data into editable test rows."""
    parsed = json.loads(text)
    if isinstance(parsed, dict):
        parsed = [parsed]
    return pd.DataFrame(parsed)
