"""Opinionated starter scenarios that make the first run useful."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4


TEMPLATES: dict[str, dict[str, Any]] = {
    "Transaction review": {
        "icon": "💳",
        "description": "Flag unusually large, high-risk transactions for a person to review.",
        "fields": [
            {"key": "amount", "label": "Transaction amount", "data_type": "number", "example": 1250},
            {"key": "risk_score", "label": "Risk score", "data_type": "number", "example": 78},
            {
                "key": "country",
                "label": "Transaction country",
                "data_type": "text",
                "choices": ["United States", "Canada", "United Kingdom", "Other"],
                "example": "United States",
            },
            {
                "key": "new_customer",
                "label": "New customer",
                "data_type": "boolean",
                "example": True,
            },
        ],
        "rule": {
            "name": "Review high-risk, large transactions",
            "description": "Protect the business without delaying ordinary purchases.",
            "match": "all",
            "conditions": [
                {"field": "amount", "operator": "greater_or_equal", "value": 1000},
                {"field": "risk_score", "operator": "greater_or_equal", "value": 70},
            ],
            "outcome": {
                "kind": "Decision",
                "value": "Manual review",
                "message": "Hold the transaction and add it to the risk review queue.",
            },
            "priority": 20,
            "tags": ["risk", "payments"],
        },
        "matching_sample": {"amount": 1850, "risk_score": 82, "country": "Canada", "new_customer": True},
        "non_matching_sample": {"amount": 84, "risk_score": 22, "country": "United States", "new_customer": False},
    },
    "Support priority": {
        "icon": "🎧",
        "description": "Fast-track urgent cases from your most important customers.",
        "fields": [
            {
                "key": "customer_tier",
                "label": "Customer tier",
                "data_type": "text",
                "choices": ["Standard", "Business", "Enterprise"],
                "example": "Enterprise",
            },
            {
                "key": "sentiment",
                "label": "Customer sentiment",
                "data_type": "text",
                "choices": ["Positive", "Neutral", "Negative"],
                "example": "Negative",
            },
            {
                "key": "hours_open",
                "label": "Hours since opened",
                "data_type": "number",
                "example": 6,
            },
            {"key": "subject", "label": "Ticket subject", "data_type": "text", "example": "Unable to sign in"},
        ],
        "rule": {
            "name": "Escalate unhappy enterprise customers",
            "description": "Make sure high-value, unhappy customers get a rapid response.",
            "match": "all",
            "conditions": [
                {"field": "customer_tier", "operator": "equals", "value": "Enterprise"},
                {"field": "sentiment", "operator": "equals", "value": "Negative"},
            ],
            "outcome": {
                "kind": "Route to queue",
                "value": "Priority support",
                "message": "Assign a senior agent and respond within 30 minutes.",
            },
            "priority": 10,
            "tags": ["support", "customer experience"],
        },
        "matching_sample": {
            "customer_tier": "Enterprise",
            "sentiment": "Negative",
            "hours_open": 2,
            "subject": "Production is down",
        },
        "non_matching_sample": {
            "customer_tier": "Standard",
            "sentiment": "Neutral",
            "hours_open": 1,
            "subject": "How do I change my password?",
        },
    },
    "Order discount": {
        "icon": "🛍️",
        "description": "Reward loyal customers when their order reaches a target amount.",
        "fields": [
            {"key": "order_total", "label": "Order total", "data_type": "number", "example": 250},
            {
                "key": "loyalty_level",
                "label": "Loyalty level",
                "data_type": "text",
                "choices": ["None", "Silver", "Gold"],
                "example": "Gold",
            },
            {"key": "item_count", "label": "Number of items", "data_type": "number", "example": 4},
            {"key": "promo_code", "label": "Promo code", "data_type": "text", "example": "SUMMER"},
        ],
        "rule": {
            "name": "Give Gold members 15% off large orders",
            "description": "Reward loyal shoppers while protecting margin on small baskets.",
            "match": "all",
            "conditions": [
                {"field": "loyalty_level", "operator": "equals", "value": "Gold"},
                {"field": "order_total", "operator": "greater_or_equal", "value": 200},
            ],
            "outcome": {
                "kind": "Apply discount",
                "value": "15% off",
                "message": "Apply the loyalty discount before tax and shipping.",
            },
            "priority": 50,
            "tags": ["commerce", "loyalty"],
        },
        "matching_sample": {"order_total": 275, "loyalty_level": "Gold", "item_count": 4, "promo_code": ""},
        "non_matching_sample": {"order_total": 85, "loyalty_level": "Silver", "item_count": 1, "promo_code": ""},
    },
}


def rule_from_template(name: str, *, fresh_id: bool = True) -> dict[str, Any]:
    template = deepcopy(TEMPLATES[name])
    rule = template["rule"]
    rule["fields"] = template["fields"]
    if fresh_id or "id" not in rule:
        rule["id"] = uuid4().hex
    for condition in rule["conditions"]:
        condition["id"] = uuid4().hex[:10]
    rule["enabled"] = True
    return rule


def starter_rulebook() -> list[dict[str, Any]]:
    return [rule_from_template(name) for name in TEMPLATES]
