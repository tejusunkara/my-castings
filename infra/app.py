"""CDK entry point: `npx cdk <command>` from infra/ runs this (see cdk.json).

Every stack is pinned to one account and region. SES receiving only exists in a few
regions, and the Phase 0 email setup already lives in us-east-1.

Settings kept out of the repository live in your user-level CDK settings, ~/.cdk.json:
    {"context": {"aws_account_id": "123456789012",
                 "budget_alert_email": "you@example.com",
                 "origin_verify_secret": "<random, e.g. secrets.token_urlsafe(32)>"}}
The domain and its Route 53 zone id are public, so they're in cdk.json.

Stacks, in deploy order:
    Guardrails  cost budget and alerts
    Network     VPC, subnets, NAT, security groups
    Data        Postgres, raw-email and media buckets (termination-protected)
    App         API on Fargate behind a load balancer; migration and sweep tasks
    Web         CloudFront at the domain: the frontend, with /api/* sent to the App
"""

import aws_cdk as cdk
from cdk_nag import AwsSolutionsChecks

from my_castings_infra.app_stack import AppStack
from my_castings_infra.data_stack import (
    DB_NAME,
    DataStack,
    media_bucket_name,
    raw_email_bucket_name,
)
from my_castings_infra.guardrails_stack import GuardrailsStack
from my_castings_infra.network_stack import NetworkStack
from my_castings_infra.web_stack import WebStack

app = cdk.App()


def required(name: str) -> str:
    value = app.node.try_get_context(name)
    if not value:
        raise SystemExit(
            f'Missing context "{name}". Add it to ~/.cdk.json: {{"context": {{"{name}": ...}}}}'
        )
    return str(value)


ENV = cdk.Environment(account=required("aws_account_id"), region="us-east-1")
DOMAIN = required("domain")
ORIGIN_DOMAIN = f"origin.{DOMAIN}"
SITE_ORIGIN = f"https://{DOMAIN}"

cdk.Tags.of(app).add("project", "my-castings")

GuardrailsStack(
    app,
    "Guardrails",
    env=ENV,
    budget_alert_email=app.node.try_get_context("budget_alert_email"),
    termination_protection=True,
)

network = NetworkStack(app, "Network", env=ENV)

data = DataStack(
    app,
    "Data",
    vpc=network.vpc,
    db_security_group=network.db_sg,
    site_origin=SITE_ORIGIN,
    env=ENV,
    termination_protection=True,
)

AppStack(
    app,
    "App",
    vpc=network.vpc,
    alb_security_group=network.alb_sg,
    api_security_group=network.api_sg,
    database=data.database,
    database_secret=data.database_secret,
    database_name=DB_NAME,
    media_bucket_name=media_bucket_name(ENV.account),
    raw_email_bucket_name=raw_email_bucket_name(ENV.account),
    hosted_zone_id=required("hosted_zone_id"),
    origin_domain=ORIGIN_DOMAIN,
    site_origin=SITE_ORIGIN,
    origin_verify_secret=required("origin_verify_secret"),
    env=ENV,
)

# No object references between App and Web: CloudFront finds the API by its DNS name, and
# both sides read the same secret from context. So neither stack can block the other's
# updates with a cross-stack export.
WebStack(
    app,
    "Web",
    hosted_zone_id=required("hosted_zone_id"),
    domain=DOMAIN,
    origin_domain=ORIGIN_DOMAIN,
    origin_verify_secret=required("origin_verify_secret"),
    env=ENV,
)

# Security/best-practice rules (cdk-nag) checked on every stack at synth time.
cdk.Validations.of(app).add_plugins(AwsSolutionsChecks(app, verbose=True))
app.synth()
