"""Sender verification from the Authentication-Results header SES stamps on inbound mail.

Rule: DKIM-OR-SPF, DMARC-aligned. The sender is verified when either mechanism passes
for a domain aligned with the From domain (equal, or one a subdomain of the other).

Two findings from Phase 0 (32 real Gmail-forwarded digests) shape this:
- SPF passes after the Gmail hop, but only because Gmail rewrites the envelope sender to
  redacted+caf_=...@gmail.com. That is not aligned with backstage.com, so it must not
  count. In practice verification rests on DKIM (send.backstage.com aligns with
  backstage.com).
- Only the *topmost* Authentication-Results header is trusted, and only if SES
  (authserv-id amazonses.com) wrote it. Lower ones come from Google or from the sender
  and can be forged.
"""

import re
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any

from ingestion_core.parsing.mime import address_domain, from_address

TRUSTED_AUTHSERV_ID = "amazonses.com"

_RESULT_RE = re.compile(r"^(spf|dkim|dmarc)=(\w+)(.*)$", re.IGNORECASE | re.DOTALL)
_DKIM_DOMAIN_RE = re.compile(r"header\.(?:d=|i=@?)([\w.-]+)", re.IGNORECASE)
_ENVELOPE_RE = re.compile(r"(?:envelope-from|smtp\.mailfrom)=<?([^\s;>]+)", re.IGNORECASE)


@dataclass
class SenderVerdict:
    verified: bool
    details: dict[str, Any] = field(default_factory=dict)


def aligned(domain: str | None, from_domain: str) -> bool:
    if not domain or not from_domain:
        return False
    domain, from_domain = domain.lower(), from_domain.lower()
    return (
        domain == from_domain
        or domain.endswith("." + from_domain)
        or from_domain.endswith("." + domain)
    )


def verify_sender(msg: EmailMessage) -> SenderVerdict:
    from_domain = address_domain(from_address(msg))
    headers = msg.get_all("Authentication-Results") or []
    if not headers:
        return SenderVerdict(False, {"reason": "no Authentication-Results header"})

    top = " ".join(str(headers[0]).split())
    authserv_id, _, rest = top.partition(";")
    authserv_id = authserv_id.strip().lower()
    if authserv_id != TRUSTED_AUTHSERV_ID:
        return SenderVerdict(
            False,
            {"reason": f"topmost Authentication-Results is from {authserv_id!r}, not SES"},
        )

    dkim: list[dict[str, Any]] = []
    spf: dict[str, Any] | None = None
    dmarc: str | None = None
    for segment in rest.split(";"):
        m = _RESULT_RE.match(segment.strip())
        if not m:
            continue
        method, result, props = m.group(1).lower(), m.group(2).lower(), m.group(3)
        if method == "dkim":
            d = _DKIM_DOMAIN_RE.search(props)
            domain = d.group(1).lower() if d else None
            dkim.append(
                {"result": result, "domain": domain, "aligned": aligned(domain, from_domain)}
            )
        elif method == "spf":
            spf = {"result": result}
        elif method == "dmarc":
            dmarc = result

    if spf is not None:
        # SES puts envelope-from in its own ;-separated segment after the spf= result.
        env = _ENVELOPE_RE.search(rest)
        env_domain = address_domain(env.group(1)) if env else None
        spf.update(envelope_from_domain=env_domain, aligned=aligned(env_domain, from_domain))

    dkim_ok = any(d["result"] == "pass" and d["aligned"] for d in dkim)
    spf_ok = bool(spf and spf["result"] == "pass" and spf["aligned"])
    details = {
        "authserv_id": authserv_id,
        "from_domain": from_domain,
        "dkim": dkim,
        "spf": spf,
        "dmarc": dmarc,
        "verified_by": "dkim" if dkim_ok else "spf" if spf_ok else None,
    }
    return SenderVerdict(dkim_ok or spf_ok, details)
