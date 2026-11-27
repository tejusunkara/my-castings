import pytest
from aws_cdk.assertions import Template


@pytest.fixture(scope="module")
def template(stacks):
    return Template.from_stack(stacks["github"])


def role(template):
    [role] = template.find_resources("AWS::IAM::Role").values()
    return role["Properties"]


def test_oidc_provider_without_a_helper_lambda(template):
    template.has_resource_properties(
        "AWS::IAM::OIDCProvider",
        {
            "Url": "https://token.actions.githubusercontent.com",
            "ClientIdList": ["sts.amazonaws.com"],
        },
    )
    template.resource_count_is("AWS::Lambda::Function", 0)


def test_only_the_production_environment_of_this_repo_can_assume_it(template):
    [statement] = role(template)["AssumeRolePolicyDocument"]["Statement"]
    assert statement["Action"] == "sts:AssumeRoleWithWebIdentity"
    assert statement["Condition"] == {
        "StringEquals": {
            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
            "token.actions.githubusercontent.com:sub": (
                "repo:owner/my-castings:environment:production"
            ),
        }
    }
    assert role(template)["MaxSessionDuration"] == 3600


def test_permissions_are_exactly_what_a_release_uses(template, account):
    [policy] = template.find_resources("AWS::IAM::Policy").values()
    actions = {s["Sid"]: s["Action"] for s in policy["Properties"]["PolicyDocument"]["Statement"]}
    assert actions == {
        "UseCdkBootstrapRoles": ["sts:AssumeRole", "sts:TagSession"],
        "ReadStackOutputs": "cloudformation:DescribeStacks",
        "RunMigrations": "ecs:RunTask",
        "WatchMigrations": "ecs:DescribeTasks",
        "PassMigrationRoles": "iam:PassRole",
        "PublishFrontend": ["s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
        "RefreshCloudFront": "cloudfront:CreateInvalidation",
    }
    statements = {s["Sid"]: s for s in policy["Properties"]["PolicyDocument"]["Statement"]}
    assert statements["UseCdkBootstrapRoles"]["Resource"] == [
        f"arn:aws:iam::{account}:role/cdk-hnb659fds-{kind}-role-{account}-us-east-1"
        for kind in ("deploy", "file-publishing", "image-publishing", "lookup")
    ]
    assert statements["PassMigrationRoles"]["Condition"] == {
        "StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}
    }
