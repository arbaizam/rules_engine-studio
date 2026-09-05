"""Snapshot integrity and sample values that matter to canonical evaluation."""

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from rules_engine import __version__
from studio import authoring, expressions, sample_data, type_compatibility, yaml_io
from studio.schema import Operand
from studio.ui import yaml_tab


def test_vendored_engine_is_the_complete_pinned_snapshot():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "docs/rules_engine_snapshot.json").read_text())
    assert manifest["commit"] == "ad26d54a8b57fd359b3ff3c0b9addf87f9b43f3f"
    actual = {
        path.relative_to(root / "rules_engine").as_posix(): hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        for path in (root / "rules_engine").rglob("*.py")
    }
    assert actual == manifest["files"]
    assert authoring.manifest()["engine_version"] == __version__ == "3.0"


def test_json_import_keeps_exact_numbers_and_nullable_large_integers():
    frame = sample_data.read_pasted_json(
        '[{"amount":12345678901234567890.123456789012345678,"id":9007199254740993},'
        '{"amount":null,"id":null}]'
    )
    rows = type_compatibility.normalized_records(frame)
    assert rows == [
        {"amount": Decimal("12345678901234567890.123456789012345678"), "id": 9007199254740993},
        {"amount": None, "id": None},
    ]


@pytest.mark.parametrize("text", ['[{"x":1,"x":2}]', '[{"x":NaN}]', '[1]', 'null'])
def test_invalid_json_samples_are_rejected(text):
    with pytest.raises(ValueError):
        sample_data.read_pasted_json(text)


def test_single_row_json_file_and_paste_have_the_same_shape():
    text = '{"x":1,"values":[2,3]}'
    assert sample_data.read_uploaded("row.json", text.encode()).equals(
        sample_data.read_pasted_json(text)
    )


def test_csv_nullable_integer_never_widens_through_float():
    frame = sample_data.read_uploaded("rows.csv", b"name,id\nA,9007199254740993\nB,\n")
    assert type_compatibility.normalized_records(frame) == [
        {"name": "A", "id": 9007199254740993}, {"name": "B", "id": None},
    ]


def test_normalization_keeps_integral_float_sample_types():
    frame = sample_data.normalize_frame(pd.DataFrame({"value": [1.0, None]}))
    row = type_compatibility.normalized_records(frame)[0]
    assert type(row["value"]) is float
    assert row["value"] == 1.0


def test_bad_dates_and_timestamp_strings_are_not_erased_or_truncated():
    frame = sample_data.read_uploaded(
        "sample.csv",
        b"EventDate,UpdateDate\n2026-09-04,2026-09-04T12:45:00+02:00\ninvalid,\n",
    )
    assert frame.loc[0, "EventDate"] == "2026-09-04"
    assert frame.loc[1, "EventDate"] == "invalid"
    assert frame.loc[0, "UpdateDate"] == "2026-09-04T12:45:00+02:00"


def test_typed_timestamp_sample_keeps_time_and_timezone():
    value = datetime(2026, 9, 4, 12, 45, tzinfo=timezone.utc)
    frame = sample_data.normalize_frame(pd.DataFrame({"UpdateDate": [value]}))
    assert type_compatibility.normalized_records(frame)[0]["UpdateDate"] == value


@pytest.mark.parametrize("data", [b"x,x\n1,2", b"x,\n1,2"])
def test_csv_does_not_silently_rename_ambiguous_columns(data):
    with pytest.raises(ValueError, match="column"):
        sample_data.read_uploaded("rows.csv", data)


def test_export_header_cannot_change_multiline_metadata_into_yaml_content():
    draft = sample_data.demo_ruleset()
    draft.version = "release\nnext"
    text = yaml_tab._with_header(yaml_io.to_yaml(draft), draft)
    assert yaml_io.from_yaml(text).version == draft.version


def test_typed_null_expression_describes_a_valid_null_literal():
    assert expressions.operand_expression(Operand(value=None, value_type="integer")) == "null (integer)"
