import json
from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from my_castings_infra.network_stack import (
    API_PORT,
    CLOUDFRONT_PREFIX_LIST,
    POSTGRES_PORT,
    VPC_CIDR,
    NetworkStack,
)

ENV = cdk.Environment(account="123456789012", region="us-east-1")


@pytest.fixture(scope="module")
def stack_and_template():
    app = cdk.App()
    stack = NetworkStack(app, "Network", env=ENV)
    return stack, Template.from_stack(stack)


@pytest.fixture(scope="module")
def template(stack_and_template):
    return stack_and_template[1]


def sg_logical_id(stack, sg) -> str:
    return stack.resolve(sg.security_group_id)["Fn::GetAtt"][0]


def test_vpc_layout(template):
    template.has_resource_properties("AWS::EC2::VPC", {"CidrBlock": VPC_CIDR})
    template.resource_count_is("AWS::EC2::Subnet", 6)  # 3 tiers x 2 AZs
    template.resource_count_is("AWS::EC2::NatGateway", 1)  # single-AZ NAT, by design


def test_data_subnets_have_no_internet_route(stack_and_template):
    stack, template = stack_and_template
    isolated = {
        stack.resolve(s.route_table.route_table_id)["Ref"] for s in stack.vpc.isolated_subnets
    }
    routes = template.find_resources("AWS::EC2::Route")
    assert len(isolated) == 2
    assert not [r for r in routes.values() if r["Properties"]["RouteTableId"]["Ref"] in isolated]


def test_s3_gateway_endpoint(template):
    template.has_resource_properties(
        "AWS::EC2::VPCEndpoint",
        {"VpcEndpointType": "Gateway", "ServiceName": Match.object_like({})},
    )


def test_rejected_traffic_flow_log(template):
    template.has_resource_properties("AWS::EC2::FlowLog", {"TrafficType": "REJECT"})


def test_nothing_is_open_to_the_internet(template):
    for sg in template.find_resources("AWS::EC2::SecurityGroup").values():
        for rule in sg["Properties"].get("SecurityGroupIngress", []):
            assert rule.get("CidrIp") != "0.0.0.0/0" and rule.get("CidrIpv6") != "::/0"


def test_alb_takes_https_from_cloudfront_only(stack_and_template):
    stack, template = stack_and_template
    alb_id = sg_logical_id(stack, stack.alb_sg)
    alb = template.find_resources("AWS::EC2::SecurityGroup")[alb_id]
    assert "SecurityGroupIngress" not in alb["Properties"]  # no inline (open) rules
    rules = [
        r["Properties"]
        for r in template.find_resources("AWS::EC2::SecurityGroupIngress").values()
        if r["Properties"]["GroupId"] == {"Fn::GetAtt": [alb_id, "GroupId"]}
    ]
    assert rules == [
        {
            "Description": "HTTPS from CloudFront",
            "FromPort": 443,
            "GroupId": {"Fn::GetAtt": [alb_id, "GroupId"]},
            "IpProtocol": "tcp",
            "SourcePrefixListId": CLOUDFRONT_PREFIX_LIST,
            "ToPort": 443,
        }
    ]


@pytest.mark.parametrize(
    ("target", "port", "sources"),
    [
        ("api_sg", API_PORT, ["alb_sg"]),
        ("db_sg", POSTGRES_PORT, ["api_sg", "ingestion_sg"]),
    ],
)
def test_internal_ingress_rules(stack_and_template, target, port, sources):
    stack, template = stack_and_template
    rules = [
        r["Properties"]
        for r in template.find_resources("AWS::EC2::SecurityGroupIngress").values()
        if r["Properties"]["GroupId"]["Fn::GetAtt"][0]
        == sg_logical_id(stack, getattr(stack, target))
    ]
    assert {r["FromPort"] for r in rules} == {port}
    assert sorted(r["SourceSecurityGroupId"]["Fn::GetAtt"][0] for r in rules) == sorted(
        sg_logical_id(stack, getattr(stack, s)) for s in sources
    )


def test_database_has_no_outbound(stack_and_template):
    stack, template = stack_and_template
    db = template.find_resources("AWS::EC2::SecurityGroup")[sg_logical_id(stack, stack.db_sg)]
    # CDK's "no outbound" form: one rule to an unroutable address.
    [egress] = db["Properties"]["SecurityGroupEgress"]
    assert egress["CidrIp"] == "255.255.255.255/32"


def test_synth_needs_no_context_lookups():
    # Lookups are cached in cdk.context.json under keys naming the AWS account, which is
    # kept out of the repository. Naming the AZs in code means there is nothing to look up.
    app = cdk.App()
    stack = NetworkStack(app, "Network", env=ENV)
    assert stack.availability_zones == ["us-east-1a", "us-east-1b"]
    manifest = json.loads((Path(app.synth().directory) / "manifest.json").read_text())
    assert not manifest.get("missing")  # context values a lookup would have to fetch
