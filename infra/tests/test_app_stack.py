import pytest
from aws_cdk.assertions import Match, Template


@pytest.fixture(scope="module")
def template(stacks):
    return Template.from_stack(stacks["app_stack"])


def containers(template):
    return {
        d["Properties"]["ContainerDefinitions"][0].get("Command")
        and tuple(d["Properties"]["ContainerDefinitions"][0]["Command"]): d["Properties"]
        for d in template.find_resources("AWS::ECS::TaskDefinition").values()
    }


def test_three_task_definitions_on_arm(template):
    tasks = containers(template)
    assert set(tasks) == {
        None,
        ("alembic", "upgrade", "head"),
        ("python", "-m", "app.sweeps", "run_once"),
    }
    for task in tasks.values():
        assert task["RuntimePlatform"]["CpuArchitecture"] == "ARM64"
        assert (task["Cpu"], task["Memory"]) == ("256", "512")


def test_credentials_are_secrets_not_environment(template, account):
    for task in containers(template).values():
        container = task["ContainerDefinitions"][0]
        env_names = {e["Name"] for e in container["Environment"]}
        secret_names = {s["Name"] for s in container["Secrets"]}
        assert secret_names == {
            "MY_CASTINGS_DB_USER",
            "MY_CASTINGS_DB_PASSWORD",
            "MY_CASTINGS_JWT_SECRET",
            "MY_CASTINGS_AUTH_PASSWORD_HASH",
        }
        assert not env_names & secret_names
        assert not any("PASSWORD" in n or "SECRET" in n for n in env_names)
        env = {e["Name"]: e["Value"] for e in container["Environment"]}
        assert env["MY_CASTINGS_MEDIA_BUCKET"] == f"my-castings-media-{account}"
        assert env["MY_CASTINGS_CLIENT_IP_HEADER"] == "cloudfront-viewer-address"


def test_service_runs_privately_with_rollback(template):
    template.has_resource_properties(
        "AWS::ECS::Service",
        {
            "DesiredCount": 1,
            "LaunchType": "FARGATE",
            "NetworkConfiguration": {
                "AwsvpcConfiguration": Match.object_like({"AssignPublicIp": "DISABLED"})
            },
            "DeploymentConfiguration": Match.object_like(
                {"DeploymentCircuitBreaker": {"Enable": True, "Rollback": True}}
            ),
        },
    )


def test_listener_rejects_requests_without_the_secret_header(template, origin_secret):
    template.has_resource_properties(
        "AWS::ElasticLoadBalancingV2::Listener",
        {
            "Port": 443,
            "Protocol": "HTTPS",
            "DefaultActions": [Match.object_like({"Type": "fixed-response"})],
        },
    )
    template.has_resource_properties(
        "AWS::ElasticLoadBalancingV2::ListenerRule",
        {
            "Conditions": [
                {
                    "Field": "http-header",
                    "HttpHeaderConfig": {
                        "HttpHeaderName": "X-Origin-Verify",
                        "Values": [origin_secret],
                    },
                }
            ],
            "Actions": [Match.object_like({"Type": "forward"})],
        },
    )
    # The listener must not open the load balancer to the internet itself.
    template.resource_count_is("AWS::EC2::SecurityGroupIngress", 0)


def test_task_roles_get_exactly_the_s3_actions_they_use(template, account):
    statements = {
        lid: r["Properties"]["PolicyDocument"]["Statement"]
        for lid, r in template.find_resources("AWS::IAM::Policy").items()
        if "TaskRole" in lid
    }
    api = next(s for lid, s in statements.items() if lid.startswith("ApiTask"))
    sweep = next(s for lid, s in statements.items() if lid.startswith("SweepTask"))
    assert [(s["Action"], s["Resource"]) for s in api] == [
        (
            ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
            f"arn:aws:s3:::my-castings-media-{account}/media/*",
        ),
        ("s3:GetObject", f"arn:aws:s3:::my-castings-raw-emails-{account}/*"),
    ]
    assert [(s["Action"], s["Resource"]) for s in sweep] == [
        ("s3:GetObject", f"arn:aws:s3:::my-castings-media-{account}/media/*")
    ]
    assert not any(lid.startswith("MigrateTaskTaskRole") for lid in statements)


def test_daily_sweep_at_9am_new_york(template):
    template.has_resource_properties(
        "AWS::Scheduler::Schedule",
        {
            "ScheduleExpression": "cron(0 9 * * ? *)",
            "ScheduleExpressionTimezone": "America/New_York",
            "State": "ENABLED",
        },
    )


def test_outputs_for_one_off_tasks(template):
    outputs = template.find_outputs("*")
    assert {"ClusterName", "MigrateTaskDefinition", "TaskSubnets", "TaskSecurityGroup"} <= set(
        outputs
    )
