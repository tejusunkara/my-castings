"""The VPC and every security group, so later stacks only attach to what's here.

Three subnet tiers in two AZs:
- public:   the load balancer and the NAT Gateway only
- app:      API tasks, the daily sweep task, the ingestion Lambda; outbound internet via
            the NAT (ECR image pulls, SSM, CloudWatch Logs), never reachable inbound
- data:     RDS; no route to the internet at all

One NAT Gateway (single AZ) is a deliberate cost choice: if its AZ goes down, the app
tier loses outbound access until it recovers. The S3 gateway endpoint is free and keeps
S3 traffic (raw emails, media) off the NAT's per-GB charge.

All security groups live here, not with the resources they guard, so the "who may talk
to whom" rules are in one place and cross-stack references only point one way.
"""

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_logs as logs
from constructs import Construct

VPC_CIDR = "10.20.0.0/16"  # avoids 10.0.0.0/16, already used by another VPC in the account
API_PORT = 8000
POSTGRES_PORT = 5432


class NetworkStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            ip_addresses=ec2.IpAddresses.cidr(VPC_CIDR),
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="app", subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS, cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="data", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, cidr_mask=24
                ),
            ],
            gateway_endpoints={
                "S3": ec2.GatewayVpcEndpointOptions(service=ec2.GatewayVpcEndpointAwsService.S3)
            },
        )

        # Rejected connections only: a record of anything probing the network, at a
        # volume that costs cents.
        self.vpc.add_flow_log(
            "RejectedTrafficLog",
            destination=ec2.FlowLogDestination.to_cloud_watch_logs(
                logs.LogGroup(
                    self,
                    "FlowLogGroup",
                    retention=logs.RetentionDays.ONE_MONTH,
                    removal_policy=cdk.RemovalPolicy.DESTROY,
                )
            ),
            traffic_type=ec2.FlowLogTrafficType.REJECT,
        )

        self.alb_sg = self._security_group("AlbSg", "Public load balancer", outbound=True)
        self.alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443), "HTTPS")
        self.alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "HTTP -> HTTPS")

        # API tasks and the daily sweep task (same image, same access).
        self.api_sg = self._security_group("ApiSg", "API and sweep tasks", outbound=True)
        self.api_sg.add_ingress_rule(self.alb_sg, ec2.Port.tcp(API_PORT), "From the ALB")

        self.ingestion_sg = self._security_group(
            "IngestionSg", "Email ingestion Lambda", outbound=True
        )

        # Nothing outbound: the database never initiates connections.
        self.db_sg = self._security_group("DbSg", "Postgres", outbound=False)
        for source, name in ((self.api_sg, "API/sweep"), (self.ingestion_sg, "ingestion")):
            self.db_sg.add_ingress_rule(source, ec2.Port.tcp(POSTGRES_PORT), f"From {name}")

        cdk.Validations.of(self.alb_sg).acknowledge(
            cdk.Acknowledgment(
                id="AwsSolutions-EC23",
                reason="Internet-facing load balancer: 80/443 from anywhere is its job.",
            )
        )

    def _security_group(self, construct_id: str, description: str, *, outbound: bool):
        return ec2.SecurityGroup(
            self,
            construct_id,
            vpc=self.vpc,
            description=description,
            allow_all_outbound=outbound,
        )
