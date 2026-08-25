# Rules Engine Studio

Streamlit authoring and test surface for the canonical
[`rules_engine`](https://github.com/arbaizam/rules_engine) metadata contract.

The studio edits mutable drafts, but it does not maintain its own rule dialect.
Every validation, YAML import/export, custom-function contract, and row test is
delegated to the pinned production package. Editor choices are built from the
engine-owned authoring manifest using the same function registry as validation
and evaluation.

## Capabilities

- Author ordered rules with nested `all` / `any` groups.
- Configure all canonical operands: `field`, `assigned`, `literal`, and
  `custom_function`.
- Configure operand null defaults, condition tolerances, null errors, active
  flags, assignment IDs, and stop-on-match behavior.
- Select all 58 standard functions from the engine registry and author their
  exact named argument contracts.
- Upload CSV, TSV, JSON, or Parquet test data and edit it in the browser.
- Evaluate one condition, rule, assignment, row, or the entire uploaded file
  with `SparkRowEvaluator`, the production worker-side row implementation.
- Import and export YAML through `YamlRulesetCompiler` and
  `YamlRulesetExporter`.
- Validate through `RulesetValidator` before export.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\streamlit.exe run app.py
```

The default Streamlit theme is dark. Session data remains in the browser
session; evaluated CSV and canonical YAML are explicit downloads.

## Architecture

| Path | Responsibility |
|---|---|
| `studio/authoring.py` | Cached engine manifest, shared registry, compiler, and semantic validator adapter |
| `studio/schema.py` | Mutable draft models plus Studio-owned labels and widget state |
| `studio/custom_functions.py` | Manifest-backed function metadata and runtime calls |
| `studio/engine.py` | `SparkRowEvaluator` adapter |
| `studio/yaml_io.py` | Production compiler, exporter, and validator adapter |
| `studio/ui/` | Streamlit authoring and test views |
| `studio/sample_data.py` | Valid starter ruleset and representative rows |
| `tests/test_studio.py` | Contract, registry, YAML, CSV, and runtime tests |

The exact `rules_engine` commit used by local and Streamlit Cloud installs is
pinned in `requirements.txt`.

CSV checks describe the uploaded sample only. Exact production Spark-schema
compatibility remains a future integration with a deployed validation endpoint.
