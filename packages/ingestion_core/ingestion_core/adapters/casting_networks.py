"""Parser for Casting Networks saved-search digests ("48 new roles today - Your Saved Search").

Built against real post-forward captures (tests/fixtures/casting_networks_*.eml). The
email is single-part text/html. Unlike Backstage, each card is one *role*; a project with
several matching roles repeats its header on every card. Cards are grouped back into one
posting per project, keyed by the project id in the View Role URL.

Shape of one card (td.roleColumn):
    <b style="font-size: 16px">Project title</b> <span>Project Type | Union Tag</span>
    <b>Role name</b>
    <b>Submissions Due</b> September 29, 2026, 8:00pm
    <b>Billing</b> / 18 - 90 / Any Gender
    <div>pay line</div>
    <div style="font-style: italic">role description (truncated with "...")</div>
    <a href=".../talent/project/<project id>/role/<role id>?...">View Role</a>

There is no posting age, seeking location or featured badge in these emails.
"""

import re
from collections.abc import Mapping
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag

from ingestion_core.adapters.base import CastingSourceAdapter, domain_matches
from ingestion_core.parsing.mime import html_body, load_message
from ingestion_core.parsing.text_normalize import (
    clean_text,
    normalize_genders,
    parse_age_range,
)
from ingestion_core.types import ParsedDigest, ParsedPosting, ParsedRole

# The emails print deadlines without a timezone, in the timezone set on the recipient's
# Casting Networks account, which for this account is Hawaii-Aleutian (observes DST).
# Evidence (2026-11-24): the email's "November 30, 2026, 4:00am" shows as 9:00am EST in
# the app; across 38 emails a midnight-Eastern deadline prints as 7:00pm both before and
# after the Nov 1 DST change, which fits America/Adak and not Pacific/Honolulu.
# If the account's timezone setting changes, this must change with it.
DEADLINE_TZ = ZoneInfo("America/Adak")
DEADLINE_LABEL = "submissions due"
_DEADLINE_FORMAT = "%B %d, %Y, %I:%M%p"

_ROLE_URL_RE = re.compile(r"/project/(\d+)/role/(\d+)")

# Project-level union tags. "Other" (and anything unrecognized) leaves it to role text.
_NONUNION_TAGS = {"non union", "no union affiliation"}
_UNION_TAGS = {"sag-aftra", "sag", "aftra", "aea", "actra", "agma", "agva", "equity"}
_UNKNOWN_TAGS = {"other", ""}

# Role names on union projects often say the role itself books differently:
# "NU to portray Pedestrians", "Joggers (NONSAG COVERED)", "UNION/NON WITH ...".
_NONUNION_ROLE_RE = re.compile(r"\b(nu|non[\s-]*union|non[\s-]*sag)\b", re.IGNORECASE)
_UNION_ROLE_RE = re.compile(r"\b(union|sag[\s-]*aftra|sagaftra)\b", re.IGNORECASE)
_BOTH_ROLE_RE = re.compile(r"\bunion\s*/\s*non\b", re.IGNORECASE)


class CastingNetworksAdapter(CastingSourceAdapter):
    source_key = "casting_networks"

    def matches_sender(self, from_address: str, headers: Mapping[str, str]) -> bool:
        return domain_matches(from_address, "castingnetworks.com")

    def parse(self, raw_mime: bytes, received_at: datetime) -> ParsedDigest:
        try:
            html = html_body(load_message(raw_mime))
        except Exception as exc:  # undecodable MIME is a whole-email failure, not a crash
            return ParsedDigest(error=f"could not decode email: {exc}")
        if not html:
            return ParsedDigest(error="email has no text/html part")

        soup = BeautifulSoup(html, "lxml")
        digest = ParsedDigest()
        projects: dict[str, _Project] = {}
        for index, card in enumerate(soup.select("td.roleColumn")):
            self._parse_card(card, index, projects, digest)
        for project in projects.values():
            digest.postings.append(project.finish(digest.field_errors))
        if not digest.postings:
            digest.error = "no role cards found in Casting Networks digest"
        return digest

    def _parse_card(
        self, card: Tag, index: int, projects: dict[str, "_Project"], digest: ParsedDigest
    ) -> None:
        errors = digest.field_errors
        bolds = card.find_all("b")
        if len(bolds) < 2:
            errors.append(f"card[{index}]: no project title or role name, skipped")
            return
        title = clean_text(bolds[0].get_text())
        role_name = clean_text(bolds[1].get_text())
        where = f"card[{index}] {title!r} role {role_name!r}"

        link = card.find("a", href=_ROLE_URL_RE)
        apply_url = link.get("href") if link else None
        if apply_url is None:
            errors.append(f"{where}: apply_url: missing View Role link")
        # Without the project id, the card still becomes its own posting.
        project_id = _ROLE_URL_RE.search(apply_url).group(1) if apply_url else f"card-{index}"

        project = projects.get(project_id)
        if project is None:
            tags = bolds[0].find_next_sibling("span")
            project = _Project(
                title=title,
                external_ref=None if project_id.startswith("card-") else project_id,
                tag_text=clean_text(tags.get_text()) if tags else None,
                where=f"posting {title!r}",
            )
            projects[project_id] = project

        role = ParsedRole(role_name=role_name, apply_url=apply_url)
        deadline_label = None
        for bold in bolds[2:]:
            label = clean_text(bold.get_text())
            if deadline_label is None and label.lower() == DEADLINE_LABEL:
                deadline_label = bold
            elif deadline_label is not None:
                self._apply_details(bold, role, where, errors)
                break
        else:
            errors.append(f"{where}: no billing/age/gender line")

        if deadline_label is None:
            errors.append(f"{where}: submission_deadline: missing")
        else:
            text = clean_text(deadline_label.parent.get_text())[len(DEADLINE_LABEL) :].strip()
            deadline = parse_deadline(text)
            if deadline is None:
                errors.append(f"{where}: submission_deadline: unparseable {text!r}")
            else:
                project.deadlines.append(deadline)

        description = card.find("div", style=re.compile(r"font-style:\s*italic"))
        if description is not None and project.description is None:
            project.description = clean_text(description.get_text()) or None
        project.roles.append(role)

    @staticmethod
    def _apply_details(billing: Tag, role: ParsedRole, where: str, errors: list[str]) -> None:
        """'<b>Principal</b> / 18 - 90 / Any Gender' (age or gender may be absent)."""
        role.billing_type = clean_text(billing.get_text()) or None
        rest = clean_text(billing.parent.get_text())[len(role.billing_type or "") :]
        tokens = [t for t in (clean_text(x) for x in rest.split("/")) if t]
        genders: list[str] = []
        for token in tokens:
            if any(ch.isdigit() for ch in token) and role.age_min is None:
                try:
                    role.age_min, role.age_max = parse_age_range(token)
                except ValueError:
                    errors.append(f"{where}: age: unparseable {token!r}")
            else:
                genders.extend(g for g in (clean_text(x) for x in token.split(",")) if g)
        role.genders = normalize_genders(genders)


class _Project:
    """Cards seen so far for one project, folded into a ParsedPosting at the end."""

    def __init__(self, title: str, external_ref: str | None, tag_text: str | None, where: str):
        self.title = title
        self.external_ref = external_ref
        self.tag_text = tag_text
        self.where = where
        self.description: str | None = None
        self.deadlines: list[datetime] = []
        self.roles: list[ParsedRole] = []

    def finish(self, errors: list[str]) -> ParsedPosting:
        project_type, _, union_tag = (self.tag_text or "").partition("|")
        return ParsedPosting(
            title=self.title,
            external_ref=self.external_ref,
            category_tag=self.tag_text or None,
            project_type=clean_text(project_type) or None,
            union_status=union_status(
                clean_text(union_tag), [r.role_name for r in self.roles], self.where, errors
            ),
            description=self.description,
            # Roles in one project can close at different times; the posting shows the
            # earliest so nothing is missed.
            submission_deadline=min(self.deadlines) if self.deadlines else None,
            roles=self.roles,
        )


def parse_deadline(text: str) -> datetime | None:
    """'September 29, 2026, 8:00pm' -> aware datetime in DEADLINE_TZ."""
    try:
        naive = datetime.strptime(clean_text(text), _DEADLINE_FORMAT)
    except ValueError:
        return None
    return naive.replace(tzinfo=DEADLINE_TZ)


def union_status(tag: str, role_names: list[str], where: str, errors: list[str]) -> str | None:
    """Combine the project's union tag with what its role names say.

    A SAG-AFTRA project booking "NU to portray Pedestrians" is open to non-union talent
    too, so it becomes union_and_nonunion rather than union.
    """
    key = clean_text(tag).lower()
    union = nonunion = False
    if key in _NONUNION_TAGS:
        nonunion = True
    elif key in _UNION_TAGS:
        union = True
    elif key not in _UNKNOWN_TAGS:
        errors.append(f"{where}: union_status: unrecognized tag {tag!r}")

    for name in role_names:
        if _BOTH_ROLE_RE.search(name):
            union = nonunion = True
            continue
        if _NONUNION_ROLE_RE.search(name):
            nonunion = True
        elif _UNION_ROLE_RE.search(name):
            union = True

    if union and nonunion:
        return "union_and_nonunion"
    if union:
        return "union"
    if nonunion:
        return "nonunion"
    return None
