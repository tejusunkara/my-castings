"""The website: CloudFront at allcastings.fyi serving the built frontend, with /api/*
forwarded to the API's load balancer.

One address for both keeps the session cookie same-origin (no CORS, no third-party
cookie rules): the browser only ever talks to https://allcastings.fyi.

- /*      the React build from a private bucket (Origin Access Control). Paths without a
          file extension get index.html, so /casting-calls/12 loads the app, which routes
          it. This is done per request by a function, not with CloudFront error pages,
          because error pages would also replace the API's own 404s.
- /api/*  never cached; cookies, query strings and headers pass through. The /api prefix
          is removed on the way, so the API keeps its own paths (/matches, /auth/login).
          CloudFront adds the secret X-Origin-Verify header the load balancer requires.
- www.allcastings.fyi redirects to allcastings.fyi.
"""

import aws_cdk as cdk
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as route53_targets
from aws_cdk import aws_s3 as s3
from constructs import Construct

from my_castings_infra.app_stack import ORIGIN_VERIFY_HEADER

SITE_FUNCTION = """
function handler(event) {
  var request = event.request;
  if (request.headers.host && request.headers.host.value === 'www.%(domain)s') {
    return {
      statusCode: 301,
      statusDescription: 'Moved Permanently',
      headers: { location: { value: 'https://%(domain)s' + request.uri } },
    };
  }
  // App routes (no file extension) all load the single-page app.
  if (request.uri.indexOf('.') === -1) {
    request.uri = '/index.html';
  }
  return request;
}
"""

API_FUNCTION = """
function handler(event) {
  var request = event.request;
  request.uri = request.uri.replace(/^\\/api(?=\\/|$)/, '') || '/';
  return request;
}
"""


class WebStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        hosted_zone_id: str,
        domain: str,
        origin_domain: str,
        origin_verify_secret: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        www = f"www.{domain}"
        hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
            self, "Zone", hosted_zone_id=hosted_zone_id, zone_name=domain
        )

        bucket = s3.Bucket(
            self,
            "Site",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            # Only build output lives here. Deleted with the stack if empty; no auto-empty
            # helper (it would add a Lambda).
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        certificate = acm.Certificate(
            self,
            "Certificate",
            domain_name=domain,
            subject_alternative_names=[www],
            validation=acm.CertificateValidation.from_dns(hosted_zone),
        )

        site_function = cloudfront.Function(
            self,
            "SiteRouting",
            code=cloudfront.FunctionCode.from_inline(SITE_FUNCTION % {"domain": domain}),
            runtime=cloudfront.FunctionRuntime.JS_2_0,
        )
        api_function = cloudfront.Function(
            self,
            "ApiPrefix",
            code=cloudfront.FunctionCode.from_inline(API_FUNCTION),
            runtime=cloudfront.FunctionRuntime.JS_2_0,
        )

        api_origin = origins.HttpOrigin(
            origin_domain,
            protocol_policy=cloudfront.OriginProtocolPolicy.HTTPS_ONLY,
            origin_ssl_protocols=[cloudfront.OriginSslPolicy.TLS_V1_2],
            custom_headers={ORIGIN_VERIFY_HEADER: origin_verify_secret},
            read_timeout=cdk.Duration.seconds(30),
        )
        # What reaches the API: all cookies and query strings, and only the headers it uses,
        # plus CloudFront-Viewer-Address (the client IP, which clients can't forge). Not
        # the Host header: CloudFront must keep sending the origin's own name, which the
        # load balancer's certificate covers.
        api_request_policy = cloudfront.OriginRequestPolicy(
            self,
            "ApiRequests",
            cookie_behavior=cloudfront.OriginRequestCookieBehavior.all(),
            query_string_behavior=cloudfront.OriginRequestQueryStringBehavior.all(),
            header_behavior=cloudfront.OriginRequestHeaderBehavior.allow_list(
                "Accept", "Content-Type", "User-Agent", "CloudFront-Viewer-Address"
            ),
        )
        self.distribution = cloudfront.Distribution(
            self,
            "Distribution",
            domain_names=[domain, www],
            certificate=certificate,
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            http_version=cloudfront.HttpVersion.HTTP2_AND_3,
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                response_headers_policy=cloudfront.ResponseHeadersPolicy.SECURITY_HEADERS,
                function_associations=[
                    cloudfront.FunctionAssociation(
                        function=site_function,
                        event_type=cloudfront.FunctionEventType.VIEWER_REQUEST,
                    )
                ],
            ),
            additional_behaviors={
                "/api/*": cloudfront.BehaviorOptions(
                    origin=api_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=api_request_policy,
                    response_headers_policy=cloudfront.ResponseHeadersPolicy.SECURITY_HEADERS,
                    function_associations=[
                        cloudfront.FunctionAssociation(
                            function=api_function,
                            event_type=cloudfront.FunctionEventType.VIEWER_REQUEST,
                        )
                    ],
                )
            },
        )

        target = route53.RecordTarget.from_alias(
            route53_targets.CloudFrontTarget(self.distribution)
        )
        for name, record_name in (("Apex", domain), ("Www", www)):
            route53.ARecord(
                self, f"{name}A", zone=hosted_zone, record_name=record_name, target=target
            )
            route53.AaaaRecord(
                self, f"{name}Aaaa", zone=hosted_zone, record_name=record_name, target=target
            )

        # The build is uploaded by scripts/aws/deploy-web.sh (s3 sync + cache invalidation)
        # rather than a CDK BucketDeployment, which would add a Lambda with broad S3 rights.
        cdk.CfnOutput(self, "SiteUrl", value=f"https://{domain}")
        cdk.CfnOutput(self, "SiteBucket", value=bucket.bucket_name)
        cdk.CfnOutput(self, "DistributionId", value=self.distribution.distribution_id)
        _acknowledge(self, bucket)


def _acknowledge(stack: cdk.Stack, bucket: s3.Bucket) -> None:
    cdk.Validations.of(bucket).acknowledge(
        cdk.Acknowledgment(
            id="AwsSolutions-S1", reason="Holds only the public build output; no access logs."
        )
    )
    cdk.Validations.of(stack).acknowledge(
        cdk.Acknowledgment(
            id="AwsSolutions-CFR1",
            reason="No geo restriction: the artist may travel and use the site anywhere.",
        ),
        cdk.Acknowledgment(
            id="AwsSolutions-CFR2",
            reason="No WAF (~$6+/month): one user, password login is rate-limited by the API, "
            "and the origin only accepts CloudFront with a secret header.",
        ),
        cdk.Acknowledgment(
            id="AwsSolutions-CFR3",
            reason="No CloudFront access logs for a single-user site.",
        ),
    )
