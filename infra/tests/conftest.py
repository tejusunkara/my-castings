import aws_cdk as cdk
import pytest

from my_castings_infra.app_stack import AppStack
from my_castings_infra.data_stack import (
    DB_NAME,
    DataStack,
    media_bucket_name,
    raw_email_bucket_name,
)
from my_castings_infra.ingestion_stack import IngestionStack, ses_rule_arn
from my_castings_infra.network_stack import NetworkStack
from my_castings_infra.web_stack import WebStack

ACCOUNT = "123456789012"
ENV = cdk.Environment(account=ACCOUNT, region="us-east-1")
DOMAIN = "allcastings.fyi"
SECRET = "test-origin-secret"


@pytest.fixture(scope="session")
def account():
    return ACCOUNT


@pytest.fixture(scope="session")
def origin_secret():
    return SECRET


@pytest.fixture(scope="session")
def stacks():
    """The whole app as app.py wires it, with test values."""
    app = cdk.App()
    network = NetworkStack(app, "Network", env=ENV)
    data = DataStack(
        app,
        "Data",
        vpc=network.vpc,
        db_security_group=network.db_sg,
        site_origin=f"https://{DOMAIN}",
        ses_rule_arn=ses_rule_arn(ACCOUNT, "us-east-1", "allcastings-inbound"),
        env=ENV,
        termination_protection=True,
    )
    app_stack = AppStack(
        app,
        "App",
        vpc=network.vpc,
        alb_security_group=network.alb_sg,
        api_security_group=network.api_sg,
        database=data.database,
        database_secret=data.database_secret,
        database_name=DB_NAME,
        media_bucket_name=media_bucket_name(ACCOUNT),
        raw_email_bucket_name=raw_email_bucket_name(ACCOUNT),
        hosted_zone_id="Z123",
        origin_domain=f"origin.{DOMAIN}",
        site_origin=f"https://{DOMAIN}",
        origin_verify_secret=SECRET,
        env=ENV,
    )
    web = WebStack(
        app,
        "Web",
        hosted_zone_id="Z123",
        domain=DOMAIN,
        origin_domain=f"origin.{DOMAIN}",
        origin_verify_secret=SECRET,
        env=ENV,
    )
    ingestion = IngestionStack(
        app,
        "Ingestion",
        vpc=network.vpc,
        ingestion_security_group=network.ingestion_sg,
        database_secret=data.database_secret,
        raw_email_bucket_name=raw_email_bucket_name(ACCOUNT),
        ses_rule_set="allcastings-inbound",
        inbound_address="jobs@mail.allcastings.fyi",
        alert_email="alerts@example.com",
        env=ENV,
    )
    return {
        "app": app,
        "network": network,
        "data": data,
        "app_stack": app_stack,
        "web": web,
        "ingestion": ingestion,
    }
