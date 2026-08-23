from __future__ import annotations

import unittest

from rules_engine.engine import evaluate_rule, evaluate_rulebook, validate_rule
from rules_engine.models import Condition, FieldDefinition, Outcome, Rule


def make_rule(*conditions: Condition, match: str = "all", priority: int = 100) -> Rule:
    return Rule(
        name="Review large orders",
        description="A test rule",
        fields=[
            FieldDefinition("amount", "Order amount", "number"),
            FieldDefinition("tier", "Customer tier", "text"),
            FieldDefinition("note", "Order note", "text"),
        ],
        conditions=list(conditions),
        outcome=Outcome("Decision", "Review", "Ask a person to review it."),
        match=match,
        priority=priority,
    )


class RuleEvaluationTests(unittest.TestCase):
    def test_all_conditions_must_match(self) -> None:
        rule = make_rule(
            Condition("amount", "greater_or_equal", 1000),
            Condition("tier", "equals", "Gold"),
        )

        result = evaluate_rule(rule, {"amount": 1200, "tier": "Silver"})

        self.assertFalse(result.matched)
        self.assertEqual([item.matched for item in result.condition_results], [True, False])
        self.assertIsNone(result.outcome)

    def test_any_condition_can_match(self) -> None:
        rule = make_rule(
            Condition("amount", "greater_than", 1000),
            Condition("tier", "equals", "Gold"),
            match="any",
        )

        result = evaluate_rule(rule, {"amount": 25, "tier": "gold"})

        self.assertTrue(result.matched)
        self.assertEqual(result.outcome["value"], "Review")

    def test_numbers_are_compared_as_numbers(self) -> None:
        rule = make_rule(Condition("amount", "less_than", "10"))

        self.assertTrue(evaluate_rule(rule, {"amount": "2"}).matched)
        self.assertFalse(evaluate_rule(rule, {"amount": "12"}).matched)

    def test_text_comparisons_ignore_case(self) -> None:
        rule = make_rule(Condition("note", "contains", "URGENT"))

        self.assertTrue(evaluate_rule(rule, {"note": "Please handle this urgently"}).matched)

    def test_missing_field_is_empty_but_does_not_equal_a_value(self) -> None:
        empty_rule = make_rule(Condition("note", "is_empty"))
        equals_rule = make_rule(Condition("note", "equals", "missing"))

        self.assertTrue(evaluate_rule(empty_rule, {}).matched)
        self.assertFalse(evaluate_rule(equals_rule, {}).matched)

    def test_explanation_includes_the_received_value(self) -> None:
        rule = make_rule(Condition("tier", "equals", "Gold"))

        result = evaluate_rule(rule, {"tier": "Silver"})

        self.assertIn("Customer tier is Gold", result.condition_results[0].explanation)
        self.assertIn("received Silver", result.condition_results[0].explanation)

    def test_rulebook_skips_disabled_rules_and_sorts_by_priority(self) -> None:
        later = make_rule(Condition("amount", "greater_than", 0), priority=200)
        earlier = make_rule(Condition("amount", "greater_than", 0), priority=10)
        disabled = make_rule(Condition("amount", "greater_than", 0), priority=1)
        disabled.enabled = False

        results = evaluate_rulebook([later, disabled, earlier], {"amount": 5})

        self.assertEqual([item.rule_id for item in results], [earlier.id, later.id])

    def test_validation_points_to_incomplete_parts(self) -> None:
        rule = make_rule(Condition("unknown", "equals", ""))
        rule.name = ""
        rule.outcome.value = ""

        errors = validate_rule(rule)

        self.assertIn("Give the rule a name.", errors)
        self.assertIn("Condition 1 needs a valid field.", errors)
        self.assertIn("Condition 1 needs a value to compare.", errors)
        self.assertIn("Describe what should happen when the rule matches.", errors)


if __name__ == "__main__":
    unittest.main()
