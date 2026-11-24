"""Account-level guardrails that cost nothing: a monthly cost budget with email alerts.

The alert address is passed at deploy time instead of committed:
    npx cdk deploy Guardrails -c budget_alert_email=you@example.com
"""

import aws_cdk as cdk
from aws_cdk import aws_budgets as budgets
from constructs import Construct

MONTHLY_LIMIT_USD = 100

# (notification type, % of the limit). Actual-spend alerts at 50/80/100%, plus an early
# warning when AWS forecasts the month will end over the limit.
ALERTS = [
    ("ACTUAL", 50),
    ("ACTUAL", 80),
    ("ACTUAL", 100),
    ("FORECASTED", 100),
]


class GuardrailsStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        budget_alert_email: str | None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        if not budget_alert_email:
            raise ValueError(
                "Guardrails needs an alert address: pass -c budget_alert_email=<email>"
            )

        subscriber = budgets.CfnBudget.SubscriberProperty(
            subscription_type="EMAIL", address=budget_alert_email
        )
        budgets.CfnBudget(
            self,
            "MonthlyCostBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_name="my-castings-monthly",
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(amount=MONTHLY_LIMIT_USD, unit="USD"),
            ),
            notifications_with_subscribers=[
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        notification_type=kind,
                        comparison_operator="GREATER_THAN",
                        threshold=percent,
                        threshold_type="PERCENTAGE",
                    ),
                    subscribers=[subscriber],
                )
                for kind, percent in ALERTS
            ],
        )
