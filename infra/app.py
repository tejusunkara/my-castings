"""CDK entry point: `npx cdk <command>` from infra/ runs this (see cdk.json).

Every stack is pinned to one account and region. SES receiving only exists in a few
regions, and the Phase 0 email setup already lives in us-east-1.
"""

import aws_cdk as cdk
from cdk_nag import AwsSolutionsChecks

from my_castings_infra.guardrails_stack import GuardrailsStack
from my_castings_infra.network_stack import NetworkStack

ENV = cdk.Environment(account="123456789012", region="us-east-1")

app = cdk.App()
cdk.Tags.of(app).add("project", "my-castings")

GuardrailsStack(
    app,
    "Guardrails",
    env=ENV,
    budget_alert_email=app.node.try_get_context("budget_alert_email"),
    termination_protection=True,
)

network = NetworkStack(app, "Network", env=ENV)

# Security/best-practice rules (cdk-nag) checked on every stack at synth time.
cdk.Validations.of(app).add_plugins(AwsSolutionsChecks(app, verbose=True))
app.synth()
