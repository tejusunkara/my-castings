import json
import shutil
import subprocess

import pytest
from aws_cdk.assertions import Match, Template

from my_castings_infra.web_stack import API_FUNCTION, SITE_FUNCTION


@pytest.fixture(scope="module")
def template(stacks):
    return Template.from_stack(stacks["web"])


def distribution(template):
    [dist] = template.find_resources("AWS::CloudFront::Distribution").values()
    return dist["Properties"]["DistributionConfig"]


def test_serves_the_domain_and_www_over_modern_tls(template):
    config = distribution(template)
    assert config["Aliases"] == ["allcastings.fyi", "www.allcastings.fyi"]
    assert config["ViewerCertificate"]["MinimumProtocolVersion"] == "TLSv1.2_2021"
    assert config["DefaultCacheBehavior"]["ViewerProtocolPolicy"] == "redirect-to-https"


def test_api_behavior_is_uncached_and_sends_the_secret(template, origin_secret):
    config = distribution(template)
    [api] = config["CacheBehaviors"]
    assert api["PathPattern"] == "/api/*"
    assert api["CachePolicyId"] == "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"  # CachingDisabled
    assert set(api["AllowedMethods"]) >= {"POST", "PATCH", "DELETE"}
    api_origin = next(o for o in config["Origins"] if o["DomainName"] == "origin.allcastings.fyi")
    assert api_origin["OriginCustomHeaders"] == [
        {"HeaderName": "X-Origin-Verify", "HeaderValue": origin_secret}
    ]
    assert api_origin["CustomOriginConfig"]["OriginProtocolPolicy"] == "https-only"


def test_api_gets_client_address_but_not_host(template):
    [policy] = template.find_resources("AWS::CloudFront::OriginRequestPolicy").values()
    config = policy["Properties"]["OriginRequestPolicyConfig"]
    assert config["CookiesConfig"] == {"CookieBehavior": "all"}
    headers = config["HeadersConfig"]
    assert headers["HeaderBehavior"] == "whitelist"
    assert set(headers["Headers"]) == {
        "Accept",
        "Content-Type",
        "User-Agent",
        "CloudFront-Viewer-Address",
    }


def test_site_bucket_is_private_behind_oac(template):
    template.resource_count_is("AWS::CloudFront::OriginAccessControl", 1)
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {"PublicAccessBlockConfiguration": Match.object_like({"BlockPublicPolicy": True})},
    )
    template.resource_count_is("AWS::Lambda::Function", 0)  # no deployment helper


def test_dns_for_apex_and_www(template):
    names = {
        (r["Properties"]["Name"], r["Properties"]["Type"])
        for r in template.find_resources("AWS::Route53::RecordSet").values()
    }
    assert names == {
        ("allcastings.fyi.", "A"),
        ("allcastings.fyi.", "AAAA"),
        ("www.allcastings.fyi.", "A"),
        ("www.allcastings.fyi.", "AAAA"),
    }


# --- the CloudFront functions, run in Node --------------------------------------------

NODE = shutil.which("node")


def run(function_code: str, uri: str, host: str = "allcastings.fyi") -> dict:
    script = function_code + (
        f"\nconsole.log(JSON.stringify(handler({{request: {{uri: {json.dumps(uri)}, "
        f"headers: {{host: {{value: {json.dumps(host)}}}}}}}}})));"
    )
    return json.loads(
        subprocess.run([NODE, "-e", script], capture_output=True, check=True, text=True).stdout
    )


site = SITE_FUNCTION % {"domain": "allcastings.fyi"}


@pytest.mark.skipif(NODE is None, reason="node not installed")
@pytest.mark.parametrize(
    "uri, expected",
    [
        ("/", "/index.html"),
        ("/casting-calls/12", "/index.html"),
        ("/media", "/index.html"),
        ("/assets/index-abc.js", "/assets/index-abc.js"),
        ("/favicon.svg", "/favicon.svg"),
    ],
)
def test_site_function_routes_app_paths_to_index(uri, expected):
    assert run(site, uri)["uri"] == expected


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_site_function_redirects_www():
    response = run(site, "/media", host="www.allcastings.fyi")
    assert response["statusCode"] == 301
    assert response["headers"]["location"]["value"] == "https://allcastings.fyi/media"


@pytest.mark.skipif(NODE is None, reason="node not installed")
@pytest.mark.parametrize(
    "uri, expected",
    [
        ("/api/matches", "/matches"),
        ("/api/auth/login", "/auth/login"),
        ("/api", "/"),
        ("/api/", "/"),
        ("/apiary/x", "/apiary/x"),
    ],
)
def test_api_function_strips_only_the_prefix(uri, expected):
    assert run(API_FUNCTION, uri)["uri"] == expected
