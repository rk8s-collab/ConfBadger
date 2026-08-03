#!/usr/bin/env python3
"""Decide which pre-printed card an attendee gets at the check-in desk.

Five cards are stocked. Volunteers and organisers are named individually in
roles.csv because their ticket looks like anyone else's; sponsors and speakers
are identified by the discount code they redeemed. Everyone else is an attendee.

roles.csv is a flat three-column file so an organiser can maintain it in a
spreadsheet up to the morning of the event:

    card_type,match_type,value
    VOLUNTEER,email,jo@example.com
    ORGANISER,email,sam@example.com
    SPONSOR,discount_code,KCDMEL26_ACME_FREE
    SPEAKER,discount_code,KCDMEL26SPKR
"""

import csv
import logging
import os

logger = logging.getLogger("uvicorn")

ROLES_CSV = "roles.csv"

#: Highest priority first. Someone can legitimately match twice — an organiser
#: who also redeemed a sponsor code — and the desk needs one answer, so the more
#: specific role wins.
CARD_TYPES = ("ORGANISER", "VOLUNTEER", "SPEAKER", "SPONSOR", "ATTENDEE")
DEFAULT_CARD_TYPE = "ATTENDEE"

#: The event's own spelling is ORGANISER, but exports and volunteers' muscle
#: memory both produce the American form.
_CARD_TYPE_ALIASES = {"ORGANIZER": "ORGANISER"}

_MATCH_TYPES = ("email", "discount_code")

#: Columns the ticketing export can carry a redeemed code in. Bevy writes the
#: human-readable discount to one and the raw code to the other, inconsistently.
_CODE_FIELDS = ("Discount", "Access code")


class RoleTable:
    """Email -> card type, and discount code -> card type. Both keyed lowercase."""

    def __init__(self, emails=None, codes=None):
        self.emails = emails or {}
        self.codes = codes or {}

    def __len__(self):
        return len(self.emails) + len(self.codes)


def _canonical_card_type(raw):
    value = (raw or "").strip().upper()
    value = _CARD_TYPE_ALIASES.get(value, value)
    return value if value in CARD_TYPES else None


def load_roles(path=ROLES_CSV):
    """Read roles.csv. A missing file is not an error — it means nobody has been
    singled out yet, so everyone is an attendee and the desk still runs."""
    if not os.path.exists(path):
        logger.info("%s not found — every attendee gets the %s card", path, DEFAULT_CARD_TYPE)
        return RoleTable()

    table = RoleTable()
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for lineno, row in enumerate(csv.DictReader(fh), start=2):
            card_type = _canonical_card_type(row.get("card_type"))
            match_type = (row.get("match_type") or "").strip().lower()
            value = (row.get("value") or "").strip()
            if not any([card_type, match_type, value]):
                continue
            # A typo'd row must not take the whole desk down mid-morning, so log
            # it loudly and carry on with the rows that parsed.
            if card_type is None:
                logger.warning("%s line %d: unknown card_type %r — row ignored", path, lineno, row.get("card_type"))
                continue
            if match_type not in _MATCH_TYPES:
                logger.warning("%s line %d: unknown match_type %r — row ignored", path, lineno, row.get("match_type"))
                continue
            if not value:
                logger.warning("%s line %d: empty value — row ignored", path, lineno)
                continue
            target = table.emails if match_type == "email" else table.codes
            target[value.lower()] = card_type

    logger.info(
        "loaded %d role rows from %s (%d emails, %d discount codes)",
        len(table), path, len(table.emails), len(table.codes),
    )
    return table


def _code_candidates(row):
    """Pull the redeemed codes out of an export row.

    Bevy writes the discount as "100.00% - KCDMEL26_ACME_FREE", so the bare code
    after the separator is offered alongside the whole field. Matching the
    separated token rather than a substring keeps a short code like SPKR from
    matching an unrelated discount that happens to contain those letters.
    """
    for field in _CODE_FIELDS:
        text = str(row.get(field, "") or "").strip()
        if not text:
            continue
        yield text.lower()
        if " - " in text:
            yield text.rsplit(" - ", 1)[1].strip().lower()


def resolve_card_type(row, roles):
    """Return the card type for one row of the ticketing export."""
    matched = set()

    email = str(row.get("Email", "") or "").strip().lower()
    if email in roles.emails:
        matched.add(roles.emails[email])

    for candidate in _code_candidates(row):
        if candidate in roles.codes:
            matched.add(roles.codes[candidate])

    for card_type in CARD_TYPES:
        if card_type in matched:
            return card_type
    return DEFAULT_CARD_TYPE
