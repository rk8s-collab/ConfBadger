#!/usr/bin/env python3
"""Checks for card-type resolution. Run: python3 test_card_types.py"""

import os
import sys
import tempfile

from card_types import DEFAULT_CARD_TYPE, load_roles, resolve_card_type

failures = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def roles_from(text):
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    try:
        return load_roles(path)
    finally:
        os.remove(path)


def row(email="", discount="", access=""):
    return {"Email": email, "Discount": discount, "Access code": access}


ROLES = roles_from(
    "card_type,match_type,value\n"
    "ORGANISER,email,sam@example.com\n"
    "VOLUNTEER,email,Jo@Example.COM\n"
    "SPONSOR,discount_code,KCDMEL26_ACME_FREE\n"
    "SPEAKER,discount_code,KCDMEL26SPKR\n"
)

print("the five card types")
check("organiser by email", resolve_card_type(row(email="sam@example.com"), ROLES) == "ORGANISER")
check("volunteer by email", resolve_card_type(row(email="jo@example.com"), ROLES) == "VOLUNTEER")
check(
    "sponsor by discount code",
    resolve_card_type(row(discount="100.00% - KCDMEL26_ACME_FREE"), ROLES) == "SPONSOR",
)
check(
    "speaker by discount code",
    resolve_card_type(row(discount="100.00% - KCDMEL26SPKR"), ROLES) == "SPEAKER",
)
check(
    "everyone else is an attendee",
    resolve_card_type(row(email="nobody@example.com", discount="Early Bird"), ROLES) == "ATTENDEE",
)

print("code matching survives how the export writes it")
check("bare code in Discount", resolve_card_type(row(discount="KCDMEL26_ACME_FREE"), ROLES) == "SPONSOR")
check("code in Access code", resolve_card_type(row(access="KCDMEL26SPKR"), ROLES) == "SPEAKER")
check("case insensitive", resolve_card_type(row(discount="100.00% - kcdmel26spkr"), ROLES) == "SPEAKER")
check("surrounding whitespace", resolve_card_type(row(discount="  KCDMEL26SPKR  "), ROLES) == "SPEAKER")
check(
    "a longer code is not matched by its tail",
    resolve_card_type(row(discount="100.00% - OTHER_KCDMEL26SPKR"), ROLES) == "ATTENDEE",
)

print("named roles outrank redeemed codes")
check(
    "organiser holding a sponsor code",
    resolve_card_type(row(email="sam@example.com", discount="100.00% - KCDMEL26_ACME_FREE"), ROLES)
    == "ORGANISER",
)
check(
    "volunteer holding a speaker code",
    resolve_card_type(row(email="jo@example.com", discount="100.00% - KCDMEL26SPKR"), ROLES)
    == "VOLUNTEER",
)

print("a missing or messy roles.csv still lets the desk run")
check("missing file", len(load_roles("no-such-roles.csv")) == 0)
check(
    "missing file means everyone is an attendee",
    resolve_card_type(row(email="sam@example.com"), load_roles("no-such-roles.csv")) == DEFAULT_CARD_TYPE,
)

MESSY = roles_from(
    "card_type,match_type,value\n"
    "ORGANIZER,email,us@example.com\n"        # American spelling
    "VIP,email,who@example.com\n"             # not one of the five cards
    "SPONSOR,badmatch,X\n"                    # unknown match type
    "SPEAKER,discount_code,\n"                # no value
    "\n"                                      # blank line
    "VOLUNTEER,email,ok@example.com\n"
)
check("american spelling accepted", resolve_card_type(row(email="us@example.com"), MESSY) == "ORGANISER")
check("unknown card type dropped", resolve_card_type(row(email="who@example.com"), MESSY) == "ATTENDEE")
check("good rows survive bad ones", resolve_card_type(row(email="ok@example.com"), MESSY) == "VOLUNTEER")

print("blank fields in the export")
check("empty row", resolve_card_type(row(), ROLES) == "ATTENDEE")
check("missing columns entirely", resolve_card_type({}, ROLES) == "ATTENDEE")
check("None values", resolve_card_type({"Email": None, "Discount": None}, ROLES) == "ATTENDEE")

print(f"\n{'FAILED: ' + ', '.join(failures) if failures else 'all checks passed'}")
sys.exit(1 if failures else 0)
