import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from my_castings_infra.guardrails_stack import ALERTS, MONTHLY_LIMIT_USD, GuardrailsStack

ENV = cdk.Environment(account="123456789012", region="us-east-1")


def synth(email: str | None) -> Template:
    app = cdk.App()
    stack = GuardrailsStack(app, "Guardrails", env=ENV, budget_alert_email=email)
    return Template.from_stack(stack)


def test_monthly_budget_with_email_alerts():
    template = synth("alerts@example.com")
    template.resource_count_is("AWS::Budgets::Budget", 1)
    template.has_resource_properties(
        "AWS::Budgets::Budget",
        {
            "Budget": {
                "BudgetType": "COST",
                "TimeUnit": "MONTHLY",
                "BudgetLimit": {"Amount": MONTHLY_LIMIT_USD, "Unit": "USD"},
            },
            "NotificationsWithSubscribers": Match.array_with(
                [
                    {
                        "Notification": Match.object_like(
                            {"NotificationType": "FORECASTED", "Threshold": 100}
                        ),
                        "Subscribers": [
                            {"SubscriptionType": "EMAIL", "Address": "alerts@example.com"}
                        ],
                    }
                ]
            ),
        },
    )
    budget = next(iter(template.find_resources("AWS::Budgets::Budget").values()))
    assert len(budget["Properties"]["NotificationsWithSubscribers"]) == len(ALERTS)


def test_alert_email_is_required():
    with pytest.raises(ValueError, match="budget_alert_email"):
        synth(None)
