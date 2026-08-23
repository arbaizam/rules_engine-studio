from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from rules_engine.examples import rule_from_template
from rules_engine.models import Rule
from rules_engine.storage import deserialize_rulebook, load_rulebook, save_rulebook, serialize_rulebook


class RulebookStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = Rule.from_dict(rule_from_template("Transaction review"))

    def test_json_round_trip_preserves_rule(self) -> None:
        content = serialize_rulebook([self.rule], "Risk rules")

        name, rules = deserialize_rulebook(content)

        self.assertEqual(name, "Risk rules")
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].to_dict(), self.rule.to_dict())

    def test_legacy_list_import_is_supported(self) -> None:
        content = json.dumps([self.rule.to_dict()])

        # A bare list is accepted for easier interoperability with early prototypes.
        _, rules = deserialize_rulebook(content)

        self.assertEqual(len(rules), 1)

    def test_save_and_load_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rulebook.json"
            save_rulebook(path, [self.rule], "Saved rules")

            loaded = load_rulebook(path)

            self.assertIsNotNone(loaded)
            name, rules = loaded
            self.assertEqual(name, "Saved rules")
            self.assertEqual(rules[0].name, self.rule.name)

    def test_invalid_shape_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "rules"):
            deserialize_rulebook('{"name": "Not enough"}')


if __name__ == "__main__":
    unittest.main()
