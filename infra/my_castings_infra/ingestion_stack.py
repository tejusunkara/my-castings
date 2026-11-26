"""The email pipeline: SES -> raw-email bucket -> EventBridge -> ingestion Lambda -> Postgres.

  Gmail forward -> jobs@mail.allcastings.fyi (SES)
      -> rule "jobs-to-raw-emails": save to s3://<raw-email bucket>/inbound/<message id>
      -> S3 "Object Created" event on EventBridge
      -> Lambda (app.ingest_lambda): verify sender, parse, store, run the match sweep

The Phase 0 rule ("jobs-to-s3", writing to the scratch bucket) is left untouched and runs
first; this stack adds its own rule after it in the same rule set, so every email lands
in both buckets and the scratch bucket keeps collecting samples.

Failures: Lambda retries an error twice, then sends the event to a dead-letter queue;
EventBridge does the same if it can't invoke the function. A message in that queue sends
an email alert. The email itself is safe in S3 regardless, and can be reprocessed.
"""

from pathlib import Path

import aws_cdk as cdk
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cloudwatch_actions
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as events_targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_destinations as destinations
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_ses as ses
from aws_cdk import aws_ses_actions as ses_actions
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions
from aws_cdk import aws_sqs as sqs
from constructs import Construct

REPO_ROOT = Path(__file__).resolve().parents[2]
RULE_NAME = "jobs-to-raw-emails"
PHASE0_RULE_NAME = "jobs-to-s3"
INBOUND_PREFIX = "inbound/"


def ses_rule_arn(account: str, region: str, rule_set: str) -> str:
    """Known before the rule exists, so the Data stack's bucket policy can name it."""
    return f"arn:aws:ses:{region}:{account}:receipt-rule-set/{rule_set}:receipt-rule/{RULE_NAME}"


class IngestionStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        ingestion_security_group: ec2.ISecurityGroup,
        database_secret: secretsmanager.ISecret,
        raw_email_bucket_name: str,
        ses_rule_set: str,
        inbound_address: str,
        alert_email: str | None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        raw_email_bucket = s3.Bucket.from_bucket_name(self, "RawEmails", raw_email_bucket_name)

        dead_letters = sqs.Queue(
            self,
            "FailedEmails",
            retention_period=cdk.Duration.days(14),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            enforce_ssl=True,
        )

        function = lambda_.DockerImageFunction(
            self,
            "Ingest",
            description="Parses each forwarded casting email into the database",
            code=lambda_.DockerImageCode.from_image_asset(
                str(REPO_ROOT), target="lambda", platform=ecr_assets.Platform.LINUX_ARM64
            ),
            architecture=lambda_.Architecture.ARM_64,
            memory_size=1024,
            timeout=cdk.Duration.seconds(60),
            # Two at a time at most: a backfill of hundreds of emails must not exhaust the
            # small database's connections.
            reserved_concurrent_executions=2,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[ingestion_security_group],
            environment={"MY_CASTINGS_DB_SECRET_ARN": database_secret.secret_arn},
            retry_attempts=2,
            on_failure=destinations.SqsDestination(dead_letters),
            log_group=logs.LogGroup(
                self,
                "IngestLogs",
                retention=logs.RetentionDays.THREE_MONTHS,
                removal_policy=cdk.RemovalPolicy.DESTROY,
            ),
        )
        database_secret.grant_read(function)
        inbound_objects = f"arn:aws:s3:::{raw_email_bucket_name}/{INBOUND_PREFIX}*"
        function.add_to_role_policy(
            iam.PolicyStatement(actions=["s3:GetObject"], resources=[inbound_objects])
        )

        events.Rule(
            self,
            "EmailArrived",
            description="A new email in the raw-email bucket's inbound/ prefix",
            event_pattern=events.EventPattern(
                source=["aws.s3"],
                detail_type=["Object Created"],
                detail={
                    "bucket": {"name": [raw_email_bucket_name]},
                    "object": {"key": [{"prefix": INBOUND_PREFIX}]},
                },
            ),
            targets=[
                events_targets.LambdaFunction(
                    function,
                    dead_letter_queue=dead_letters,
                    retry_attempts=8,
                    max_event_age=cdk.Duration.hours(6),
                )
            ],
        )

        rule = ses.ReceiptRule(
            self,
            "ToRawEmails",
            receipt_rule_name=RULE_NAME,
            rule_set=ses.ReceiptRuleSet.from_receipt_rule_set_name(self, "RuleSet", ses_rule_set),
            after=ses.ReceiptRule.from_receipt_rule_name(self, "Phase0Rule", PHASE0_RULE_NAME),
            recipients=[inbound_address],
            scan_enabled=True,
            tls_policy=ses.TlsPolicy.REQUIRE,
            actions=[ses_actions.S3(bucket=raw_email_bucket, object_key_prefix=INBOUND_PREFIX)],
        )

        alerts = sns.Topic(self, "Alerts", display_name="my-castings alerts", enforce_ssl=True)
        if alert_email:
            alerts.add_subscription(subscriptions.EmailSubscription(alert_email))
        alarm = cloudwatch.Alarm(
            self,
            "EmailsFailing",
            alarm_description="An email couldn't be ingested after retries; it is in the "
            "FailedEmails queue and still in S3.",
            metric=dead_letters.metric_approximate_number_of_messages_visible(
                period=cdk.Duration.minutes(5)
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        alarm.add_alarm_action(cloudwatch_actions.SnsAction(alerts))

        cdk.CfnOutput(self, "FailedEmailsQueue", value=dead_letters.queue_url)
        _acknowledge(self, function, inbound_objects, rule, dead_letters, alerts)


def _acknowledge(stack, function, inbound_objects, rule, dead_letters, alerts) -> None:
    cdk.Validations.of(rule).acknowledge(
        cdk.Acknowledgment(
            id="Annotation::@aws-cdk/s3:AddBucketPermissions",
            reason="The Data stack's bucket policy lets exactly this rule write to inbound/.",
        )
    )
    cdk.Validations.of(function).acknowledge(
        cdk.Acknowledgment(
            id=f"AwsSolutions-IAM5[Resource::{inbound_objects}]",
            reason="Read-only (GetObject) on new emails under inbound/; S3 object ARNs need a "
            "path wildcard.",
        ),
        cdk.Acknowledgment(
            id="AwsSolutions-IAM4[Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/"
            "AWSLambdaVPCAccessExecutionRole]",
            reason="AWS's standard policy for a Lambda in a VPC (network interfaces, logs).",
        ),
        cdk.Acknowledgment(
            id="AwsSolutions-IAM4[Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/"
            "AWSLambdaBasicExecutionRole]",
            reason="AWS's standard logging policy for Lambda.",
        ),
    )
    cdk.Validations.of(dead_letters).acknowledge(
        cdk.Acknowledgment(id="AwsSolutions-SQS3", reason="This queue is itself the DLQ.")
    )
    cdk.Validations.of(alerts).acknowledge(
        cdk.Acknowledgment(
            id="AwsSolutions-SNS2",
            reason="Alarm notices only (no data). A KMS key would need a key policy for "
            "CloudWatch, for no gain here.",
        )
    )
