"""Build the frontend and publish it to the site bucket:

    uv run python scripts/aws/deploy_web.py

Builds apps/web, uploads the files (hashed assets cached for a year, index.html never
cached), removes files from older builds, and clears CloudFront's cache.
"""

import mimetypes
import os
import subprocess
import time
from pathlib import Path

from _stack import client, outputs

WEB = Path("apps/web")
LONG_CACHE = "public, max-age=31536000, immutable"
NO_CACHE = "no-cache"


def main() -> None:
    subprocess.run(["npm", "run", "build"], cwd=WEB, check=True)
    dist = WEB / "dist"
    out = outputs("Web")
    bucket, distribution = out["SiteBucket"], out["DistributionId"]
    s3 = client("s3")

    uploaded = set()
    for path in sorted(p for p in dist.rglob("*") if p.is_file()):
        key = path.relative_to(dist).as_posix()
        content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
        cache = LONG_CACHE if key.startswith("assets/") else NO_CACHE
        s3.upload_file(
            str(path), bucket, key, ExtraArgs={"ContentType": content_type, "CacheControl": cache}
        )
        uploaded.add(key)
    print(f"uploaded {len(uploaded)} files")

    # Old hashed assets go only after the new index.html is in place.
    stale = [
        {"Key": o["Key"]}
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket)
        for o in page.get("Contents", [])
        if o["Key"] not in uploaded
    ]
    for start in range(0, len(stale), 1000):
        s3.delete_objects(Bucket=bucket, Delete={"Objects": stale[start : start + 1000]})
    if stale:
        print(f"removed {len(stale)} old files")

    client("cloudfront").create_invalidation(
        DistributionId=distribution,
        InvalidationBatch={
            "Paths": {"Quantity": 1, "Items": ["/*"]},
            "CallerReference": f"deploy-web-{int(time.time())}",
        },
    )
    print(f"published; live at {out['SiteUrl']} within a minute or two")


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parents[2])
    main()
