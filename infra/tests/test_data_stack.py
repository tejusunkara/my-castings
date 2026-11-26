import pytest
from aws_cdk.assertions import Match, Template


@pytest.fixture(scope="module")
def template(stacks):
    return Template.from_stack(stacks["data"])


def test_stack_is_termination_protected(stacks):
    assert stacks["data"].termination_protection


def test_database_is_private_encrypted_backed_up_and_protected(template):
    template.has_resource(
        "AWS::RDS::DBInstance",
        {
            "Properties": Match.object_like(
                {
                    "DBInstanceClass": "db.t4g.micro",
                    "Engine": "postgres",
                    "EngineVersion": Match.string_like_regexp(r"^16\."),
                    "MultiAZ": False,
                    "PubliclyAccessible": False,
                    "StorageEncrypted": True,
                    "BackupRetentionPeriod": 7,
                    "DeletionProtection": True,
                    "DBName": "my_castings",
                }
            ),
            "DeletionPolicy": "Snapshot",
            "UpdateReplacePolicy": "Snapshot",
        },
    )
    template.has_resource_properties(
        "AWS::RDS::DBParameterGroup", {"Parameters": {"rds.force_ssl": "1"}}
    )


def test_password_is_generated_not_written(template):
    template.resource_count_is("AWS::SecretsManager::Secret", 1)
    template.has_resource_properties(
        "AWS::SecretsManager::Secret",
        {"GenerateSecretString": Match.object_like({"GenerateStringKey": "password"})},
    )


def test_buckets_are_private_retained_and_named(template, account):
    buckets = template.find_resources("AWS::S3::Bucket")
    assert len(buckets) == 2
    for bucket in buckets.values():
        assert bucket["DeletionPolicy"] == "Retain"
        block = bucket["Properties"]["PublicAccessBlockConfiguration"]
        assert all(block[k] for k in block)
    names = {b["Properties"]["BucketName"] for b in buckets.values()}
    assert names == {f"my-castings-media-{account}", f"my-castings-raw-emails-{account}"}


def test_media_cors_allows_only_the_site(template, account):
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "BucketName": f"my-castings-media-{account}",
            "CorsConfiguration": {
                "CorsRules": [
                    Match.object_like(
                        {
                            "AllowedOrigins": ["https://allcastings.fyi"],
                            "AllowedMethods": ["GET", "HEAD", "POST"],
                        }
                    )
                ]
            },
        },
    )


def test_no_helper_lambdas(template):
    template.resource_count_is("AWS::Lambda::Function", 0)


def test_raw_emails_notify_eventbridge_without_a_helper(template, account):
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "BucketName": f"my-castings-raw-emails-{account}",
            "NotificationConfiguration": {"EventBridgeConfiguration": {"EventBridgeEnabled": True}},
        },
    )


def test_only_the_ses_rule_may_write_inbound(template, account):
    policies = template.find_resources("AWS::S3::BucketPolicy")
    statements = [
        s
        for p in policies.values()
        for s in p["Properties"]["PolicyDocument"]["Statement"]
        if s.get("Sid") == "SesWritesInbound"
    ]
    assert len(statements) == 1
    [statement] = statements
    assert statement["Principal"] == {"Service": "ses.amazonaws.com"}
    assert statement["Action"] == "s3:PutObject"
    assert statement["Condition"] == {
        "StringEquals": {"aws:SourceAccount": account},
        "ArnLike": {
            "aws:SourceArn": f"arn:aws:ses:us-east-1:{account}:receipt-rule-set/"
            "allcastings-inbound:receipt-rule/jobs-to-raw-emails"
        },
    }
