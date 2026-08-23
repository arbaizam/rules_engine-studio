# Runtime parity

Rules Engine Studio does not contain a preview evaluator.

| Studio operation | Authoritative implementation |
|---|---|
| Draft compilation | `rules_engine.compiler_yaml.YamlRulesetCompiler` |
| Semantic validation | `rules_engine.validator.RulesetValidator` |
| YAML export | `rules_engine.exporter_yaml.YamlRulesetExporter` |
| Function metadata and implementations | `FunctionRegistry` populated by `register_standard_functions` |
| Row evaluation | `rules_engine.runtime.SparkRowEvaluator` |

`SparkRowEvaluator` is the production row implementation used inside Spark
workers. The studio invokes it directly against uploaded Python row mappings,
which avoids starting a Spark session while retaining engine comparison, null,
assignment, stop-on-match, assigned-value, and custom-function behavior.

The studio adds two presentation behaviors only:

- Exceptions are captured per test row and displayed in an `error` field.
- Missing fields in the uploaded test data are authoring warnings. They are not
  engine validation issues.

The dependency is pinned to a specific `rules_engine` commit. Updating that pin
must be accompanied by the contract tests in `tests/test_studio.py`.
