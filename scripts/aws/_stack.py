"""Shared helpers: AWS clients for us-east-1 and CloudFormation stack outputs."""

import boto3

REGION = "us-east-1"


def client(service: str):
    return boto3.client(service, region_name=REGION)


def outputs(stack: str) -> dict[str, str]:
    [description] = client("cloudformation").describe_stacks(StackName=stack)["Stacks"]
    return {o["OutputKey"]: o["OutputValue"] for o in description.get("Outputs", [])}
