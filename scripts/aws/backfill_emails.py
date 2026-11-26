"""Import emails already in the Phase 0 scratch bucket into the live pipeline:

    uv run python scripts/aws/backfill_emails.py            # casting emails only
    uv run python scripts/aws/backfill_emails.py --all      # everything, setup mail too
    uv run python scripts/aws/backfill_emails.py --dry-run  # list what would be copied

Copies each object into the raw-email bucket under inbound/backfill/, which fires the
same S3 event SES's own deliveries do, so the ingestion Lambda parses them exactly like
new mail. Safe to re-run: an object already ingested is skipped by the Lambda, and copies
already present are not made again.

Run it after the Ingestion stack is deployed and migrations have run.
"""

import argparse
import os
from email import message_from_bytes, policy
from email.utils import parseaddr
from pathlib import Path

from _stack import client

SCRATCH_BUCKET = "allcastings-fyi-scratch-raw-emails"
CASTING_DOMAINS = ("backstage.com", "castingnetworks.com", "actorsaccess.com")
PREFIX = "inbound/backfill/"


def sender_domain(s3, bucket: str, key: str) -> str:
    # The headers are in the first few KB; no need to fetch whole digests.
    head = s3.get_object(Bucket=bucket, Key=key, Range="bytes=0-65535")["Body"].read()
    msg = message_from_bytes(head, policy=policy.default)
    return parseaddr(str(msg.get("From", "")))[1].rpartition("@")[2].lower()


def is_casting(domain: str) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in CASTING_DOMAINS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--all", action="store_true", help="include non-casting emails")
    parser.add_argument("--dry-run", action="store_true", help="list, don't copy")
    args = parser.parse_args()

    s3 = client("s3")
    account = client("sts").get_caller_identity()["Account"]
    target = f"my-castings-raw-emails-{account}"
    existing = {
        o["Key"]
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=target, Prefix=PREFIX)
        for o in page.get("Contents", [])
    }

    copied = skipped = present = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=SCRATCH_BUCKET):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            domain = sender_domain(s3, SCRATCH_BUCKET, key)
            if not args.all and not is_casting(domain):
                skipped += 1
                continue
            if PREFIX + key in existing:
                present += 1
                continue
            print(f"{'would copy' if args.dry_run else 'copy'} {key} ({domain})")
            if not args.dry_run:
                s3.copy_object(
                    Bucket=target,
                    Key=PREFIX + key,
                    CopySource={"Bucket": SCRATCH_BUCKET, "Key": key},
                )
            copied += 1
    verb = "would copy" if args.dry_run else "copied"
    print(f"{verb} {copied}; {present} already there; {skipped} non-casting skipped")


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parents[2])
    main()
