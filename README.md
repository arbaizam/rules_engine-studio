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
- Navigate and reorder rules in one list: click, tap, or press Enter to open;
  drag, use the arrow keys, or use the always-available move buttons to reorder.
- Recover the in-progress ruleset and sample rows from browser-local autosave
  after a reload or deployment restart.
- Configure all canonical operands: `field`, `assigned`, `literal`, and
  `custom_function`.
- Configure operand null defaults, condition tolerances, null errors, active
  flags, assignment IDs, and stop-on-match behavior.
- Filter operators, fields, literals, functions, and prior assignments using
  value types inferred from the current sample data. Unknown and mixed columns
  remain available and are labeled instead of being silently discarded.
- Select all 58 standard functions from the engine registry and author their
  exact named argument contracts.
- Upload CSV, TSV, JSON, or Parquet test data and edit it in the browser.
- Evaluate one condition, rule, assignment, row, or the entire uploaded file
  with `SparkRowEvaluator`, the production worker-side row implementation.
- Import and export YAML through `YamlRulesetCompiler` and
  `YamlRulesetExporter`.
- Watch a collapsible, read-only YAML preview update beside the active editor,
  follow the selected rule, and remain viewport-aligned while authoring,
  including best-effort draft syntax while production validation is blocked.
- Validate through `RulesetValidator` before export.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\streamlit.exe run app.py
```

The default Streamlit theme is dark. The in-progress ruleset and sample rows
are autosaved only in the current browser. Evaluated CSV and canonical YAML
remain explicit downloads.

## Architecture

| Path | Responsibility |
|---|---|
| `studio/authoring.py` | Cached engine manifest, shared registry, compiler, and semantic validator adapter |
| `studio/schema.py` | Mutable draft models plus Studio-owned labels and widget state |
| `studio/custom_functions.py` | Manifest-backed function metadata and runtime calls |
| `studio/engine.py` | `SparkRowEvaluator` adapter |
| `studio/yaml_io.py` | Production compiler, exporter, and validator adapter |
| `studio/ui/` | Streamlit authoring and test views |
| `studio/ui/reorder.py` | Integrated mouse, touch, and keyboard rule sorter |
| `studio/ui/yaml_preview.py` | Cached live YAML snapshot and collapsible right-side preview |
| `studio/ui/browser_state.py` | Strict-JSON browser-local working-draft recovery |
| `studio/sample_data.py` | Valid starter ruleset and representative rows |
| `studio/type_compatibility.py` | Sample-value type inference and compatibility filtering |
| `tests/test_studio.py` | Contract, registry, YAML, CSV, and runtime tests |

The exact `rules_engine` source used by local and Streamlit Cloud installs is
vendored from a pinned production commit. See
[`docs/VENDORED_RULES_ENGINE.md`](docs/VENDORED_RULES_ENGINE.md) for provenance
and upgrade instructions.

CSV checks describe the uploaded sample only. Exact production Spark-schema
compatibility remains a future integration with a deployed validation endpoint.

The checked-in examples are generated from the same canonical starter project:

```powershell
.\.venv\Scripts\python.exe scripts\regenerate_examples.py
```
