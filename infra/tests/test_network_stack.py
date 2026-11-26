import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from my_castings_infra.network_stack import API_PORT, POSTGRES_PORT, VPC_CIDR, NetworkStack

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


def test_only_the_alb_is_open_to_the_internet(stack_and_template):
    stack, template = stack_and_template
    open_groups = [
        lid
        for lid, sg in template.find_resources("AWS::EC2::SecurityGroup").items()
        if any(
            r.get("CidrIp") == "0.0.0.0/0" for r in sg["Properties"].get("SecurityGroupIngress", [])
        )
    ]
    assert open_groups == [sg_logical_id(stack, stack.alb_sg)]


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
