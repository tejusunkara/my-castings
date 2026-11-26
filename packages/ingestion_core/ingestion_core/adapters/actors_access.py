"""Parser for Actors Access role notifications ("Projects match your profile - 11/25/26 3:00
PM Pacific"), sent from notifications@actorsaccess.com.

PROVISIONAL: built from one *manually* forwarded email
(tests/fixtures/actors_access_manual_forward.eml). Gmail wraps a manual forward in its own
"---------- Forwarded message ---------" block but keeps the original HTML inside it, and
the selectors below only look at Actors Access links, so the wrapper is ignored. Still to
check against an auto-forwarded email: that SES sees an actorsaccess.com DKIM pass (so
verification lets it through), and the wording of union tags, genders and ages this one
sample doesn't show.

Each card is one breakdown with its role(s). Cards are found by their title link, which
Actors Access tags with utm_content=html_title:

    <div><a href="...?view=breakdowns&breakdown=913212&...html_title...">Project title</a></div>
    <div>Episodic <span/> NON-UNION <span/> Melville, NY</div>     (type | union | location)
    <div>
      <div><a href="...breakdown=913212&...html_role...">Role name</a></div>
      <div>Any gender; 30 to 85 years old; all ethnicities. Description...<a>Read more.</a></div>
    </div>

The breakdown id is the posting's external_ref. Two breakdowns can share a title (a lead
and a background call for the same project); they stay separate postings, as Actors
Access lists them.

There is no submission deadline, posting age, billing or featured badge in these emails.
The subject's timestamp is when the notification batch ran, not when the role was posted,
so posted_at is left empty.
"""

import re
from collections.abc import Mapping
from datetime import datetime

from bs4 import BeautifulSoup, NavigableString, Tag

from ingestion_core.adapters.base import CastingSourceAdapter, domain_matches
from ingestion_core.parsing.mime import html_body, load_message
from ingestion_core.parsing.text_normalize import clean_text, normalize_genders, split_locations
from ingestion_core.types import ParsedDigest, ParsedPosting, ParsedRole

_BREAKDOWN_RE = re.compile(r"[?&]breakdown=(\d+)")
_TITLE_LINK_RE = re.compile(r"actorsaccess\.com/projects/\?.*utm_content=html_title")
_ROLE_LINK_RE = re.compile(r"actorsaccess\.com/projects/\?.*utm_content=html_role")
_VIEW_ALL_RE = re.compile(r"^view all breakdowns$", re.IGNORECASE)

# "30 to 85 years old" / "25 years old"
_AGE_RE = re.compile(r"^(\d{1,3})(?:\s+to\s+(\d{1,3}))?\s+years?\s+old$", re.IGNORECASE)
_READ_MORE_RE = re.compile(r"\s*Read more\.?\s*$", re.IGNORECASE)

# Union tags as printed on the type | union | location line. Only NON-UNION, SAG-AFTRA and
# "Not Applicable" have been seen; the rest are guesses at the obvious spellings, and
# anything else is reported as a field error so new wording gets noticed.
_UNION_TAGS = {
    "NON-UNION": "nonunion",
    "NONUNION": "nonunion",
    "SAG-AFTRA": "union",
    "UNION": "union",
    "AEA": "union",
    "SAG-AFTRA, NON-UNION": "union_and_nonunion",
    "UNION AND NON-UNION": "union_and_nonunion",
}
_NO_UNION_INFO = {"NOT APPLICABLE", ""}


class ActorsAccessAdapter(CastingSourceAdapter):
    source_key = "actors_access"

    def matches_sender(self, from_address: str, headers: Mapping[str, str]) -> bool:
        return domain_matches(from_address, "actorsaccess.com")

    def parse(self, raw_mime: bytes, received_at: datetime) -> ParsedDigest:
        try:
            html = html_body(load_message(raw_mime))
        except Exception as exc:  # undecodable MIME is a whole-email failure, not a crash
            return ParsedDigest(error=f"could not decode email: {exc}")
        if not html:
            return ParsedDigest(error="email has no text/html part")

        soup = BeautifulSoup(html, "lxml")
        view_all = soup.find("a", string=_VIEW_ALL_RE)
        view_all_url = view_all.get("href") if view_all else None

        digest = ParsedDigest()
        for index, title_link in enumerate(soup.find_all("a", href=_TITLE_LINK_RE)):
            posting = self._parse_card(title_link, index, digest.field_errors)
            posting.view_all_jobs_url = view_all_url
            digest.postings.append(posting)
        if not digest.postings:
            digest.error = "no breakdown cards found in Actors Access email"
        return digest

    def _parse_card(self, title_link: Tag, index: int, errors: list[str]) -> ParsedPosting:
        title = clean_text(title_link.get_text())
        where = f"posting[{index}] {title!r}"
        ref = _BREAKDOWN_RE.search(title_link.get("href", ""))
        posting = ParsedPosting(title=title, external_ref=ref.group(1) if ref else None)
        if ref is None:
            errors.append(f"{where}: external_ref: no breakdown id in title link")

        header = title_link.find_parent("div")
        tag_line = header.find_next_sibling("div") if header else None
        if tag_line is None:
            errors.append(f"{where}: no type/union/location line")
        else:
            self._apply_tags(_segments(tag_line), posting, where, errors)

        # Role blocks run from the tag line up to the next card's title.
        block = tag_line.find_next_sibling("div") if tag_line else None
        while block is not None and not block.find("a", href=_TITLE_LINK_RE):
            for role_link in block.find_all("a", href=_ROLE_LINK_RE):
                posting.roles.append(self._parse_role(role_link, posting, where, errors))
            block = block.find_next_sibling("div")
        if not posting.roles:
            errors.append(f"{where}: no roles")
        return posting

    @staticmethod
    def _apply_tags(
        segments: list[str], posting: ParsedPosting, where: str, errors: list[str]
    ) -> None:
        """['Episodic', 'NON-UNION', 'Melville, NY'] -> type, union status, locations."""
        posting.category_tag = " | ".join(segments) or None
        if len(segments) != 3:
            errors.append(f"{where}: expected type | union | location, got {segments!r}")
            return
        project_type, union_tag, location = segments
        posting.project_type = project_type or None
        posting.seeking_locations = split_locations(location)
        key = union_tag.upper()
        if key in _UNION_TAGS:
            posting.union_status = _UNION_TAGS[key]
        elif key not in _NO_UNION_INFO:
            errors.append(f"{where}: union_status: unrecognized tag {union_tag!r}")

    @staticmethod
    def _parse_role(
        role_link: Tag, posting: ParsedPosting, where: str, errors: list[str]
    ) -> ParsedRole:
        role = ParsedRole(
            role_name=clean_text(role_link.get_text()), apply_url=role_link.get("href")
        )
        where = f"{where} role {role.role_name!r}"
        name_div = role_link.find_parent("div")
        details = name_div.find_next_sibling("div") if name_div else None
        if details is None:
            errors.append(f"{where}: no gender/age line")
            return role

        text = _READ_MORE_RE.sub("", clean_text(details.get_text()))
        # The posting has no description of its own; the first role's line (gender, age,
        # ethnicity, then the truncated description) stands in for it, kept whole so the
        # ethnicity, which has no field, isn't lost.
        if posting.description is None:
            posting.description = text or None

        # "Any gender; 30 to 85 years old; all ethnicities. ..." Gender comes first; age
        # is whichever of the first two parts reads "... years old".
        parts = [clean_text(p) for p in text.split(";", 2)]
        if len(parts) < 3:
            errors.append(f"{where}: unexpected gender/age line {text[:60]!r}")
        for position, part in enumerate(parts[:2]):
            if m := _AGE_RE.match(part):
                low = int(m.group(1))
                high = int(m.group(2)) if m.group(2) else low
                if low > high:
                    errors.append(f"{where}: age: inverted range {part!r}")
                else:
                    role.age_min, role.age_max = low, high
            elif position == 0:
                role.genders = normalize_genders([clean_text(g) for g in part.split(",")])
        if role.age_min is None and len(parts) >= 2:
            errors.append(f"{where}: age: unparseable {parts[1]!r}")
        return role


def _segments(line: Tag) -> list[str]:
    """Text of a line split at its <span> dividers: 'Episodic|NON-UNION|Melville, NY'."""
    segments, current = [], []
    for child in line.children:
        if isinstance(child, NavigableString):
            current.append(str(child))
        elif isinstance(child, Tag) and child.name == "span":
            segments.append(clean_text("".join(current)))
            current = []
        elif isinstance(child, Tag):
            current.append(child.get_text())
    segments.append(clean_text("".join(current)))
    return [s for s in segments if s]
