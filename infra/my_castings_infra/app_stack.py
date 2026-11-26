"""The API on Fargate behind a load balancer, plus the jobs that use the same image.

Requests reach the API only through CloudFront (see web_stack.py):
  browser -> CloudFront (allcastings.fyi/api/*) -> load balancer (origin.allcastings.fyi)
  -> API task (port 8000, private subnet)
The load balancer accepts only CloudFront's addresses (security group) and only requests
carrying the secret X-Origin-Verify header CloudFront adds; everything else gets a 403.

One image, three task definitions:
- api      the long-running service
- migrate  `alembic upgrade head`, run by hand before a release (scripts/aws/run-task.sh)
- sweep    `python -m app.sweeps run_once`, daily at 9am New York time

Secrets never appear in the template: the database credentials come from the secret RDS
generated, and the login password hash and session-signing key from SSM SecureString
parameters created by scripts/aws/create-app-secrets.sh before the first deploy.
"""

from pathlib import Path

import aws_cdk as cdk
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_rds as rds
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as route53_targets
from aws_cdk import aws_scheduler as scheduler
from aws_cdk import aws_scheduler_targets as scheduler_targets
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_ssm as ssm
from constructs import Construct

from my_castings_infra.network_stack import API_PORT

REPO_ROOT = Path(__file__).resolve().parents[2]
ORIGIN_VERIFY_HEADER = "X-Origin-Verify"
JWT_SECRET_PARAMETER = "/my-castings/jwt-secret"
PASSWORD_HASH_PARAMETER = "/my-castings/auth-password-hash"


class AppStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        alb_security_group: ec2.ISecurityGroup,
        api_security_group: ec2.ISecurityGroup,
        database: rds.DatabaseInstance,
        database_secret: secretsmanager.ISecret,
        database_name: str,
        media_bucket_name: str,
        raw_email_bucket_name: str,
        hosted_zone_id: str,
        origin_domain: str,
        site_origin: str,
        origin_verify_secret: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        zone_name = origin_domain.split(".", 1)[1]
        hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
            self, "Zone", hosted_zone_id=hosted_zone_id, zone_name=zone_name
        )

        image = ecs.ContainerImage.from_asset(
            str(REPO_ROOT), file="Dockerfile", platform=ecr_assets.Platform.LINUX_ARM64
        )
        self.cluster = ecs.Cluster(self, "Cluster", vpc=vpc)

        environment = {
            "MY_CASTINGS_DB_HOST": database.db_instance_endpoint_address,
            "MY_CASTINGS_DB_PORT": database.db_instance_endpoint_port,
            "MY_CASTINGS_DB_NAME": database_name,
            "MY_CASTINGS_MEDIA_BUCKET": media_bucket_name,
            "MY_CASTINGS_MEDIA_CORS_ORIGINS": f'["{site_origin}"]',
            "MY_CASTINGS_S3_REGION": self.region,
            "MY_CASTINGS_CLIENT_IP_HEADER": "cloudfront-viewer-address",
        }
        secrets = {
            "MY_CASTINGS_DB_USER": ecs.Secret.from_secrets_manager(database_secret, "username"),
            "MY_CASTINGS_DB_PASSWORD": ecs.Secret.from_secrets_manager(database_secret, "password"),
            "MY_CASTINGS_JWT_SECRET": _secure_parameter(self, "JwtSecret", JWT_SECRET_PARAMETER),
            "MY_CASTINGS_AUTH_PASSWORD_HASH": _secure_parameter(
                self, "PasswordHash", PASSWORD_HASH_PARAMETER
            ),
        }

        def task(name: str, command: list[str] | None) -> ecs.FargateTaskDefinition:
            definition = ecs.FargateTaskDefinition(
                self,
                f"{name}Task",
                cpu=256,
                memory_limit_mib=512,
                runtime_platform=ecs.RuntimePlatform(
                    cpu_architecture=ecs.CpuArchitecture.ARM64,
                    operating_system_family=ecs.OperatingSystemFamily.LINUX,
                ),
            )
            definition.add_container(
                "app",
                image=image,
                command=command,
                environment=environment,
                secrets=secrets,
                logging=ecs.LogDrivers.aws_logs(
                    stream_prefix=name.lower(),
                    log_group=logs.LogGroup(
                        self,
                        f"{name}Logs",
                        retention=logs.RetentionDays.ONE_MONTH,
                        removal_policy=cdk.RemovalPolicy.DESTROY,
                    ),
                ),
                port_mappings=[ecs.PortMapping(container_port=API_PORT)]
                if command is None
                else None,
            )
            return definition

        api_task = task("Api", None)
        migrate_task = task("Migrate", ["alembic", "upgrade", "head"])
        sweep_task = task("Sweep", ["python", "-m", "app.sweeps", "run_once"])

        # Exactly what the code does, nothing broader:
        # - API: signs upload forms (PutObject) and view links (GetObject), checks uploads
        #   (HeadObject needs GetObject), deletes media; reads raw emails to reprocess them.
        # - sweep: checks abandoned uploads (HeadObject). It deletes rows, not objects.
        # - migrate: database only.
        media_objects = f"arn:aws:s3:::{media_bucket_name}/media/*"
        raw_email_objects = f"arn:aws:s3:::{raw_email_bucket_name}/*"
        api_task.add_to_task_role_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
                resources=[media_objects],
            )
        )
        api_task.add_to_task_role_policy(
            iam.PolicyStatement(actions=["s3:GetObject"], resources=[raw_email_objects])
        )
        sweep_task.add_to_task_role_policy(
            iam.PolicyStatement(actions=["s3:GetObject"], resources=[media_objects])
        )

        self.service = ecs.FargateService(
            self,
            "Api",
            cluster=self.cluster,
            task_definition=api_task,
            desired_count=1,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[api_security_group],
            assign_public_ip=False,
            circuit_breaker=ecs.DeploymentCircuitBreaker(enable=True, rollback=True),
            min_healthy_percent=100,
            max_healthy_percent=200,
            health_check_grace_period=cdk.Duration.seconds(60),
        )

        load_balancer = elbv2.ApplicationLoadBalancer(
            self,
            "LoadBalancer",
            vpc=vpc,
            internet_facing=True,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=alb_security_group,
            drop_invalid_header_fields=True,
        )
        certificate = acm.Certificate(
            self,
            "OriginCertificate",
            domain_name=origin_domain,
            validation=acm.CertificateValidation.from_dns(hosted_zone),
        )
        listener = load_balancer.add_listener(
            "Https",
            port=443,
            certificates=[certificate],
            ssl_policy=elbv2.SslPolicy.RECOMMENDED_TLS,
            # open=False: the security group (CloudFront only) decides who connects, not
            # an automatic 0.0.0.0/0 rule.
            open=False,
            default_action=elbv2.ListenerAction.fixed_response(
                403, content_type="text/plain", message_body="Forbidden"
            ),
        )
        targets = elbv2.ApplicationTargetGroup(
            self,
            "ApiTargets",
            vpc=vpc,
            port=API_PORT,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[self.service],
            deregistration_delay=cdk.Duration.seconds(30),
            health_check=elbv2.HealthCheck(path="/health", healthy_threshold_count=2),
        )
        listener.add_action(
            "FromCloudFront",
            priority=1,
            conditions=[
                elbv2.ListenerCondition.http_header(ORIGIN_VERIFY_HEADER, [origin_verify_secret])
            ],
            action=elbv2.ListenerAction.forward([targets]),
        )
        route53.ARecord(
            self,
            "OriginRecord",
            zone=hosted_zone,
            record_name=origin_domain,
            target=route53.RecordTarget.from_alias(
                route53_targets.LoadBalancerTarget(load_balancer)
            ),
        )

        scheduler.Schedule(
            self,
            "DailySweep",
            description="Match and media sweeps, daily at 9am New York time",
            schedule=scheduler.ScheduleExpression.cron(
                minute="0", hour="9", time_zone=cdk.TimeZone.AMERICA_NEW_YORK
            ),
            target=scheduler_targets.EcsRunFargateTask(
                self.cluster,
                task_definition=sweep_task,
                vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
                security_groups=[api_security_group],
            ),
        )

        # Everything scripts/aws/run-task.sh needs to start a one-off migration.
        cdk.CfnOutput(self, "ClusterName", value=self.cluster.cluster_name)
        cdk.CfnOutput(self, "MigrateTaskDefinition", value=migrate_task.task_definition_arn)
        cdk.CfnOutput(
            self,
            "TaskSubnets",
            value=",".join(
                vpc.select_subnets(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS).subnet_ids
            ),
        )
        cdk.CfnOutput(self, "TaskSecurityGroup", value=api_security_group.security_group_id)

        allowed_wildcards = {
            "*": "Execution roles: ecr:GetAuthorizationToken is defined on '*' only.",
            media_objects: "Objects under media/ in the media bucket; actions are exactly "
            "Put/Get/DeleteObject (API) or GetObject (sweep).",
            raw_email_objects: "Raw-email objects, read-only (GetObject), for reprocessing.",
        }
        _acknowledge(self, allowed_wildcards, load_balancer, api_task, migrate_task, sweep_task)


def _secure_parameter(scope: Construct, construct_id: str, name: str) -> ecs.Secret:
    parameter = ssm.StringParameter.from_secure_string_parameter_attributes(
        scope, construct_id, parameter_name=name
    )
    return ecs.Secret.from_ssm_parameter(parameter)


def _acknowledge(
    stack: cdk.Stack, allowed_wildcards: dict[str, str], load_balancer, *task_definitions
) -> None:
    cdk.Validations.of(load_balancer).acknowledge(
        cdk.Acknowledgment(
            id="AwsSolutions-ELB2",
            reason="No ALB access logs: the app logs requests, and CloudFront sits in front.",
        )
    )
    for definition in task_definitions:
        cdk.Validations.of(definition).acknowledge(
            cdk.Acknowledgment(
                id="AwsSolutions-ECS2",
                reason="The environment holds only non-secret settings (hostnames, bucket "
                "name); every credential is an ECS secret.",
            ),
            # The only wildcard resources: object paths, which S3 requires, and ECR login.
            *[
                cdk.Acknowledgment(id=f"AwsSolutions-IAM5[Resource::{r}]", reason=why)
                for r, why in allowed_wildcards.items()
            ],
        )
    cdk.Validations.of(stack).acknowledge(
        cdk.Acknowledgment(
            id="AwsSolutions-ECS4",
            reason="Container Insights costs more than it tells about one small task; the "
            "service's default CPU/memory metrics are enough.",
        )
    )
