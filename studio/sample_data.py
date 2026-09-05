"""
Starter data and canonical ruleset metadata for the studio.

The studio opens on something that already evaluates, so the first thing an
author sees is a working example rather than an empty form.
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import date, datetime
from decimal import Decimal
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
    return normalize_frame(pd.DataFrame(DEMO_ROWS, dtype=object))


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
                        "policy": "CurrentDSCR >= 1.25",
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
    if lowered.endswith((".csv", ".tsv")):
        separator = "\t" if lowered.endswith(".tsv") else ","
        text = data.decode("utf-8-sig")
        header = next(csv.reader(io.StringIO(text), delimiter=separator), [])
        if not header or any(not name.strip() for name in header):
            raise ValueError("Sample columns must have non-empty names.")
        if len(header) != len(set(header)):
            raise ValueError("Sample column names must be unique.")
        return normalize_frame(
            pd.read_csv(
                io.StringIO(text), sep=separator, float_precision="round_trip",
                dtype_backend="numpy_nullable",
            )
        )
    if lowered.endswith(".json"):
        return read_pasted_json(data.decode("utf-8-sig"))
    if lowered.endswith(".parquet"):
        return normalize_frame(pd.read_parquet(io.BytesIO(data)))
    raise ValueError("Supported sample data formats: .csv, .tsv, .json, .parquet")


def _parse_date_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Infer date-only columns without discarding invalid text or timestamp information."""
    parsed_frame = frame.copy()
    for column_name in parsed_frame.columns:
        if "date" not in str(column_name).lower():
            continue
        populated = parsed_frame[column_name].dropna()
        if populated.empty or any(isinstance(value, datetime) for value in populated):
            continue
        # CSV date inference is advisory. Leave an entire column untouched if
        # a value is not a date-only string; never turn bad data into a null.
        if not all(
            isinstance(value, date)
            or (
                isinstance(value, str)
                and re.fullmatch(r"(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{4})", value)
            )
            for value in populated
        ):
            continue
        parsed = pd.to_datetime(
            parsed_frame[column_name],
            errors="coerce",
            format="mixed",
        )
        if parsed.loc[populated.index].isna().any():
            continue
        values = parsed.dt.date.astype("object")
        parsed_frame[column_name] = values.where(parsed.notna(), None)
    return parsed_frame


def normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize date columns and retain nullable integer types without widening."""
    if any(not isinstance(name, str) or not name.strip() for name in frame.columns):
        raise ValueError("Sample columns must have non-empty string names.")
    if not frame.columns.is_unique:
        raise ValueError("Sample column names must be unique.")
    normalized = _parse_date_columns(frame)
    for name in normalized.columns:
        populated = normalized[name].dropna()
        if not populated.empty and all(type(value) is int for value in populated):
            if all(-(2**63) <= value < 2**63 for value in populated):
                normalized[name] = pd.array(normalized[name], dtype="Int64")
            # Oversize integers must remain exact so schema validation can
            # report overflow, rather than evaluating a rounded sample value.
            continue
        normalized[name] = normalized[name].convert_dtypes(convert_integer=False)
    return normalized


def read_pasted_json(text: str) -> pd.DataFrame:
    """Parse pasted JSON object or array data into editable test rows."""
    parsed = json.loads(
        text, parse_float=Decimal, parse_constant=_reject_json_constant,
        object_pairs_hook=_unique_json_object,
    )
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list) or any(not isinstance(row, dict) for row in parsed):
        raise ValueError("Sample JSON must be an object or an array of row objects.")
    # Object dtype avoids pandas widening nullable integers through binary floats.
    return normalize_frame(pd.DataFrame(parsed, dtype=object))


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Sample JSON numbers must be finite: {value}")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"Duplicate sample JSON key: {name}")
        result[name] = value
    return result
