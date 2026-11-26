"""Parser output types. Adapters produce these; the API/Lambda map them onto DB rows."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

ParseStatus = Literal["success", "partial", "failed"]


@dataclass
class ParsedRole:
    role_name: str
    billing_type: str | None = None
    # Lower-cased, e.g. ["female", "trans female"]. Empty means open to any gender
    # (either omitted by the source or listed as "All Genders").
    genders: list[str] = field(default_factory=list)
    age_min: int | None = None
    age_max: int | None = None
    is_featured: bool = False  # role-level badge, independent of the posting's
    # Free text as the source prints it ("$850 for 9 hours of work", "SAG AFTRA scale").
    pay: str | None = None
    apply_url: str | None = None  # personalized/tokenized; stored exactly as received


@dataclass
class ParsedPosting:
    title: str
    category_tag: str | None = None  # raw tags as shown, e.g. "Feature Film · $ Paid · Union"
    project_type: str | None = None  # e.g. "Feature Film"
    union_status: str | None = None  # "union" | "nonunion" | "union_and_nonunion"
    description: str | None = None
    posted_at: datetime | None = None
    submission_deadline: datetime | None = None
    seeking_locations: list[str] = field(default_factory=list)
    is_featured: bool = False  # posting-level badge
    view_all_jobs_url: str | None = None
    external_ref: str | None = None
    roles: list[ParsedRole] = field(default_factory=list)


@dataclass
class ParsedDigest:
    postings: list[ParsedPosting] = field(default_factory=list)
    # Whole-email failure reason (no postings found, no HTML body, ...).
    error: str | None = None
    # Per-field problems that didn't stop the row from being stored, e.g.
    # "posting[2] 'Title' role[0] 'Name': age: unparseable '18 to 24'".
    field_errors: list[str] = field(default_factory=list)

    @property
    def status(self) -> ParseStatus:
        if self.error or not self.postings:
            return "failed"
        if self.field_errors:
            return "partial"
        return "success"

    @property
    def error_summary(self) -> str | None:
        if self.status == "failed":
            return self.error or "no postings found"
        if self.field_errors:
            return "; ".join(self.field_errors)
        return None
