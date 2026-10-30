"""Parser for Backstage "New Roles Available" digest emails.

Built against real post-forward captures (tests/fixtures/backstage_*.eml). The HTML part
is the source of truth; the plain-text part lacks gender, age, tags and posting age.

Shape of one job card (div.section_job-card):
    span.job-tag ...          project type (class exactly "job-tag"), "$ Paid" (.paid),
                              union status (.union), "Staff Pick" (.staff), and the
                              posting-level badge "Stand out! Be the first to apply!"
    <em>Posted 1 day, 20 hours ago</em>
    <h2><a href=...>Title</a></h2>
    <p>description (may end with a "More" link)</p>
    <p><strong>Seeking talent from:</strong> City, ST; City, ST</p>
    per role, a grey box:
        <h4>Role name</h4>
        <ul><li>Billing, Gender, Gender, 18-24</li><li>Estimated pay amount: ...</li></ul>
        <p><strong>Stand out! Be the first to apply!</strong></p>   (role-level badge)
        <a class="primary-cta">Apply</a>
"""

from collections.abc import Mapping
from datetime import datetime

from bs4 import BeautifulSoup, Tag

from ingestion_core.adapters.base import CastingSourceAdapter, domain_matches
from ingestion_core.parsing.mime import html_body, load_message
from ingestion_core.parsing.relative_time import parse_relative_age
from ingestion_core.parsing.text_normalize import (
    clean_text,
    normalize_genders,
    normalize_union_status,
    parse_age_range,
    split_locations,
)
from ingestion_core.types import ParsedDigest, ParsedPosting, ParsedRole

BADGE_TEXT = "stand out!"
LOCATIONS_LABEL = "seeking talent from"


class BackstageAdapter(CastingSourceAdapter):
    source_key = "backstage"

    def matches_sender(self, from_address: str, headers: Mapping[str, str]) -> bool:
        return domain_matches(from_address, "backstage.com")

    def parse(self, raw_mime: bytes, received_at: datetime) -> ParsedDigest:
        try:
            html = html_body(load_message(raw_mime))
        except Exception as exc:  # undecodable MIME is a whole-email failure, not a crash
            return ParsedDigest(error=f"could not decode email: {exc}")
        if not html:
            return ParsedDigest(error="email has no text/html part")

        soup = BeautifulSoup(html, "lxml")
        digest = ParsedDigest()
        for index, card in enumerate(soup.select("div.section_job-card")):
            posting = self._parse_card(card, index, received_at, digest.field_errors)
            if posting is not None:
                digest.postings.append(posting)
        if not digest.postings:
            digest.error = "no job cards found in Backstage digest"
        return digest

    def _parse_card(
        self, card: Tag, index: int, received_at: datetime, errors: list[str]
    ) -> ParsedPosting | None:
        heading = card.find("h2")
        if heading is None:
            errors.append(f"posting[{index}]: no title, skipped")
            return None
        title = clean_text(heading.get_text())
        where = f"posting[{index}] {title!r}"
        link = heading.find("a")

        posting = ParsedPosting(
            title=title,
            view_all_jobs_url=link.get("href") if link else None,
        )
        self._apply_tags(card, posting)

        posted = card.find("em")
        if posted is not None:
            age = parse_relative_age(posted.get_text())
            if age is None:
                errors.append(f"{where}: posted_at: unparseable {clean_text(posted.get_text())!r}")
            else:
                posting.posted_at = received_at - age

        for para in heading.find_all_next("p"):
            if para.find_parent("div", class_="section_job-card") is not card:
                break
            label = para.find("strong")
            if label and clean_text(label.get_text()).lower().startswith(LOCATIONS_LABEL):
                label.extract()
                posting.seeking_locations = split_locations(para.get_text())
                break
            if posting.description is None:
                for more in para.find_all("a", string=lambda s: s and s.strip() == "More"):
                    more.extract()
                posting.description = clean_text(para.get_text()) or None

        for role_index, role_heading in enumerate(card.find_all("h4")):
            role = self._parse_role(role_heading, f"{where} role[{role_index}]", errors)
            posting.roles.append(role)
        return posting

    @staticmethod
    def _apply_tags(card: Tag, posting: ParsedPosting) -> None:
        tags = card.select("span.job-tag")
        posting.category_tag = " · ".join(clean_text(t.get_text()) for t in tags) or None
        for tag in tags:
            classes = set(tag.get("class") or [])
            text = clean_text(tag.get_text())
            if text.lower().startswith(BADGE_TEXT):
                posting.is_featured = True
            elif "union" in classes:
                posting.union_status = normalize_union_status(text)
            elif classes == {"job-tag"} and posting.project_type is None:
                posting.project_type = text

    @staticmethod
    def _parse_role(heading: Tag, where: str, errors: list[str]) -> ParsedRole:
        role = ParsedRole(role_name=clean_text(heading.get_text()))
        where = f"{where} {role.role_name!r}"
        # Everything for this role lives in the same <tbody> as its <h4>.
        box = heading.find_parent("tbody")

        details = box.find("li") if box else None
        if details is None:
            errors.append(f"{where}: no role details line")
        else:
            tokens = [t for t in (clean_text(x) for x in details.get_text().split(",")) if t]
            if tokens:
                role.billing_type = tokens.pop(0)
            if tokens and any(ch.isdigit() for ch in tokens[-1]):
                age_token = tokens.pop()
                try:
                    role.age_min, role.age_max = parse_age_range(age_token)
                except ValueError:
                    errors.append(f"{where}: age: unparseable {age_token!r}")
            role.genders = normalize_genders(tokens)

        if box is not None:
            role.is_featured = any(
                clean_text(s.get_text()).lower().startswith(BADGE_TEXT)
                for s in box.find_all("strong")
            )
            apply = box.find("a", class_="primary-cta")
            role.apply_url = apply.get("href") if apply else None
        if role.apply_url is None:
            errors.append(f"{where}: apply_url: missing Apply link")
        return role
