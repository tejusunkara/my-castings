"""The role GitHub Actions assumes to release: no long-lived AWS keys anywhere.

GitHub's OIDC provider issues each workflow run a short-lived token; AWS trades it for
this role's credentials only when the token says it comes from this repository's
"production" environment. That environment (repository settings) only runs from main and
waits for the owner's approval, so a pull request, a fork or another branch can't deploy.

What the role can do, all of it needed for a release (.github/workflows/deploy.yml):
- assume the CDK bootstrap roles, to deploy stacks (`cdk deploy App Ingestion Web`)
- read stack outputs (the release scripts find their targets that way)
- run the migration task and wait for it
- upload the frontend to the site bucket and invalidate CloudFront's cache

Deployment goes through CloudFormation, whose execution role is the bootstrap default.
The stateful Data stack is protected regardless: termination protection on the stack,
deletion protection on the database, and Retain on both buckets.
"""

import aws_cdk as cdk
from aws_cdk import aws_iam as iam
from constructs import Construct

GITHUB_OIDC_URL = "https://token.actions.githubusercontent.com"
CDK_QUALIFIER = "hnb659fds"  # the default bootstrap qualifier


class GitHubDeployStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        repository: str,
        environment: str = "production",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        account, region = self.account, self.region

        provider = iam.OidcProviderNative(
            self,
            "GitHubOidc",
            url=GITHUB_OIDC_URL,
            client_ids=["sts.amazonaws.com"],
        )
        self.role = iam.Role(
            self,
            "DeployRole",
            description=f"GitHub Actions releases from {repository} ({environment})",
            max_session_duration=cdk.Duration.hours(1),
            assumed_by=iam.WebIdentityPrincipal(
                provider.oidc_provider_arn,
                conditions={
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                        # Only jobs running in the protected environment of this repository.
                        "token.actions.githubusercontent.com:sub": (
                            f"repo:{repository}:environment:{environment}"
                        ),
                    }
                },
            ),
        )

        bootstrap_roles = [
            f"arn:aws:iam::{account}:role/cdk-{CDK_QUALIFIER}-{kind}-role-{account}-{region}"
            for kind in ("deploy", "file-publishing", "image-publishing", "lookup")
        ]
        statements = [
            iam.PolicyStatement(
                sid="UseCdkBootstrapRoles",
                actions=["sts:AssumeRole", "sts:TagSession"],
                resources=bootstrap_roles,
            ),
            iam.PolicyStatement(
                sid="ReadStackOutputs",
                actions=["cloudformation:DescribeStacks"],
                resources=[
                    f"arn:aws:cloudformation:{region}:{account}:stack/{name}/*"
                    for name in ("App", "Web", "Ingestion")
                ],
            ),
            iam.PolicyStatement(
                sid="RunMigrations",
                actions=["ecs:RunTask"],
                resources=[f"arn:aws:ecs:{region}:{account}:task-definition/AppMigrateTask*"],
            ),
            iam.PolicyStatement(
                sid="WatchMigrations",
                actions=["ecs:DescribeTasks"],
                resources=[f"arn:aws:ecs:{region}:{account}:task/*"],
            ),
            iam.PolicyStatement(
                sid="PassMigrationRoles",
                actions=["iam:PassRole"],
                resources=[f"arn:aws:iam::{account}:role/App-MigrateTask*"],
                conditions={"StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}},
            ),
            iam.PolicyStatement(
                sid="PublishFrontend",
                actions=["s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
                resources=["arn:aws:s3:::web-site*", "arn:aws:s3:::web-site*/*"],
            ),
            iam.PolicyStatement(
                sid="RefreshCloudFront",
                actions=["cloudfront:CreateInvalidation"],
                resources=[f"arn:aws:cloudfront::{account}:distribution/*"],
            ),
        ]
        for statement in statements:
            self.role.add_to_policy(statement)

        cdk.CfnOutput(self, "DeployRoleArn", value=self.role.role_arn)

        cdk.Validations.of(self.role).acknowledge(
            cdk.Acknowledgment(
                id="AwsSolutions-IAM5",
                reason="Wildcards are name prefixes of resources CDK names with generated "
                "suffixes (App-MigrateTask*, web-site*, AppMigrateTask*), task ARNs (unknown "
                "until a task starts) and distribution ids; actions are listed exactly.",
            ),
            *[
                cdk.Acknowledgment(id=f"AwsSolutions-IAM5[Resource::{r}]", reason="See above.")
                for r in (
                    f"arn:aws:ecs:{region}:{account}:task-definition/AppMigrateTask*",
                    f"arn:aws:ecs:{region}:{account}:task/*",
                    f"arn:aws:iam::{account}:role/App-MigrateTask*",
                    "arn:aws:s3:::web-site*",
                    "arn:aws:s3:::web-site*/*",
                    f"arn:aws:cloudfront::{account}:distribution/*",
                    *[
                        f"arn:aws:cloudformation:{region}:{account}:stack/{name}/*"
                        for name in ("App", "Web", "Ingestion")
                    ],
                )
            ],
        )
