import pytest
from aws_cdk.assertions import Match, Template


@pytest.fixture(scope="module")
def template(stacks):
    return Template.from_stack(stacks["ingestion"])


def test_ses_rule_runs_after_phase0_rule_and_saves_under_inbound(template, account):
    template.has_resource_properties(
        "AWS::SES::ReceiptRule",
        {
            "RuleSetName": "allcastings-inbound",
            "After": "jobs-to-s3",
            "Rule": Match.object_like(
                {
                    "Name": "jobs-to-raw-emails",
                    "Enabled": True,
                    "Recipients": ["jobs@mail.allcastings.fyi"],
                    "ScanEnabled": True,
                    "TlsPolicy": "Require",
                    "Actions": [
                        {
                            "S3Action": {
                                "BucketName": f"my-castings-raw-emails-{account}",
                                "ObjectKeyPrefix": "inbound/",
                            }
                        }
                    ],
                }
            ),
        },
    )
    # The rule set itself (and the Phase 0 rule) belong to Phase 0, not this stack.
    template.resource_count_is("AWS::SES::ReceiptRuleSet", 0)


def test_lambda_is_an_arm_image_in_the_vpc_with_capped_concurrency(template):
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "PackageType": "Image",
            "Architectures": ["arm64"],
            "ReservedConcurrentExecutions": 2,
            "Timeout": 60,
            "VpcConfig": Match.object_like({"SecurityGroupIds": Match.any_value()}),
            "Environment": {
                "Variables": {"MY_CASTINGS_DB_SECRET_ARN": Match.any_value()},
            },
        },
    )


def test_lambda_reads_only_new_emails(template, account):
    statements = [
        s
        for p in template.find_resources("AWS::IAM::Policy").values()
        for s in p["Properties"]["PolicyDocument"]["Statement"]
        if "s3:GetObject" in (s["Action"] if isinstance(s["Action"], list) else [s["Action"]])
    ]
    assert [s["Resource"] for s in statements] == [
        f"arn:aws:s3:::my-castings-raw-emails-{account}/inbound/*"
    ]


def test_eventbridge_rule_matches_inbound_objects(template, account):
    template.has_resource_properties(
        "AWS::Events::Rule",
        {
            "EventPattern": {
                "source": ["aws.s3"],
                "detail-type": ["Object Created"],
                "detail": {
                    "bucket": {"name": [f"my-castings-raw-emails-{account}"]},
                    "object": {"key": [{"prefix": "inbound/"}]},
                },
            },
            "Targets": [
                Match.object_like(
                    {
                        "DeadLetterConfig": Match.any_value(),
                        "RetryPolicy": {
                            "MaximumRetryAttempts": 8,
                            "MaximumEventAgeInSeconds": 21600,
                        },
                    }
                )
            ],
        },
    )


def test_failures_go_to_a_queue_that_alerts_by_email(template):
    template.has_resource_properties(
        "AWS::Lambda::EventInvokeConfig",
        {
            "MaximumRetryAttempts": 2,
            "DestinationConfig": {"OnFailure": {"Destination": Match.any_value()}},
        },
    )
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {"MetricName": "ApproximateNumberOfMessagesVisible", "Threshold": 1},
    )
    template.has_resource_properties(
        "AWS::SNS::Subscription", {"Protocol": "email", "Endpoint": "alerts@example.com"}
    )
