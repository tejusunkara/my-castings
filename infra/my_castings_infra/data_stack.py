"""Everything stateful: Postgres, the raw-email bucket and the media bucket.

Kept apart from the app so redeploying or even deleting the app can't touch data. The
stack has termination protection, the database has deletion protection and takes a final
snapshot if it's ever removed, and both buckets are retained if the stack goes away.

Single-AZ database with 7 days of point-in-time backups: a zone outage means downtime
until it recovers or a restore, which is the accepted trade for half the cost of Multi-AZ.
"""

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_rds as rds
from aws_cdk import aws_s3 as s3
from constructs import Construct

DB_NAME = "my_castings"
DB_ADMIN_USER = "my_castings_admin"
DB_INSTANCE_ID = "my-castings"


# Fixed names (bucket names are global, hence the account id), so other stacks can refer to
# the buckets by name and write exact IAM resources without cross-stack references.
def media_bucket_name(account: str) -> str:
    return f"my-castings-media-{account}"


def raw_email_bucket_name(account: str) -> str:
    return f"my-castings-raw-emails-{account}"


class DataStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        db_security_group: ec2.ISecurityGroup,
        site_origin: str,
        ses_rule_arn: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Created here, with its retention, before RDS starts writing to it. (Letting RDS
        # set retention instead adds a helper Lambda to the stack.)
        db_log_group = logs.LogGroup(
            self,
            "DatabaseLogs",
            log_group_name=f"/aws/rds/instance/{DB_INSTANCE_ID}/postgresql",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        self.database = rds.DatabaseInstance(
            self,
            "Database",
            instance_identifier=DB_INSTANCE_ID,
            engine=rds.DatabaseInstanceEngine.postgres(version=rds.PostgresEngineVersion.VER_16_9),
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.T4G, ec2.InstanceSize.MICRO),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[db_security_group],
            # RDS generates the password into Secrets Manager; it never appears in code.
            credentials=rds.Credentials.from_generated_secret(DB_ADMIN_USER),
            database_name=DB_NAME,
            allocated_storage=20,
            max_allocated_storage=50,
            storage_type=rds.StorageType.GP3,
            storage_encrypted=True,
            multi_az=False,
            publicly_accessible=False,
            backup_retention=cdk.Duration.days(7),
            deletion_protection=True,
            removal_policy=cdk.RemovalPolicy.SNAPSHOT,
            auto_minor_version_upgrade=True,
            parameters={"rds.force_ssl": "1"},
            cloudwatch_logs_exports=["postgresql"],
        )
        self.database.node.add_dependency(db_log_group)
        self.database_secret = self.database.secret

        # Every email SES receives, kept permanently: the source of truth for reprocessing.
        self.raw_email_bucket = s3.Bucket(
            self,
            "RawEmails",
            bucket_name=raw_email_bucket_name(self.account),
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # SES writes incoming mail under inbound/, and only the one receipt rule may. S3 then
        # tells EventBridge, which starts the ingestion Lambda (Ingestion stack). The
        # EventBridge switch is set on the bucket directly: CDK's notification helper would
        # add a Lambda to this stack.
        self.raw_email_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="SesWritesInbound",
                principals=[iam.ServicePrincipal("ses.amazonaws.com")],
                actions=["s3:PutObject"],
                resources=[self.raw_email_bucket.arn_for_objects("inbound/*")],
                conditions={
                    "StringEquals": {"aws:SourceAccount": self.account},
                    "ArnLike": {"aws:SourceArn": ses_rule_arn},
                },
            )
        )
        raw_cfn = self.raw_email_bucket.node.default_child
        raw_cfn.add_property_override(
            "NotificationConfiguration.EventBridgeConfiguration.EventBridgeEnabled", True
        )

        # Headshots, reels, resume. Browsers upload with signed forms and view with signed
        # links, so only the site's own origin needs CORS.
        self.media_bucket = s3.Bucket(
            self,
            "Media",
            bucket_name=media_bucket_name(self.account),
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            removal_policy=cdk.RemovalPolicy.RETAIN,
            cors=[
                s3.CorsRule(
                    allowed_origins=[site_origin],
                    allowed_methods=[s3.HttpMethods.GET, s3.HttpMethods.HEAD, s3.HttpMethods.POST],
                    allowed_headers=["*"],
                    max_age=3600,
                )
            ],
            lifecycle_rules=[
                s3.LifecycleRule(abort_incomplete_multipart_upload_after=cdk.Duration.days(1))
            ],
        )

        for bucket in (self.raw_email_bucket, self.media_bucket):
            cdk.Validations.of(bucket).acknowledge(
                cdk.Acknowledgment(
                    id="AwsSolutions-S1",
                    reason="Single-user app; S3 access logs would cost more attention than they "
                    "give. API access is logged by the app and CloudTrail.",
                )
            )
        cdk.Validations.of(self.database).acknowledge(
            cdk.Acknowledgment(
                id="AwsSolutions-RDS3",
                reason="Single-AZ by decision (cost); 7-day point-in-time backups cover data loss.",
            ),
            cdk.Acknowledgment(
                id="AwsSolutions-RDS11",
                reason="Default port: the database has no public route and only two security "
                "groups may connect, so a non-default port adds nothing.",
            ),
            cdk.Acknowledgment(
                id="AwsSolutions-SMG4",
                reason="Rotation needs a rotation Lambda in the VPC; for one admin user the "
                "password is rotated by hand if needed.",
            ),
        )
