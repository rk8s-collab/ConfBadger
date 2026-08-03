#!/usr/bin/env python3
"""Checks for check-in search: name and email matching, and that the response
never carries a usable address. Run: python3 test_checkin_search.py"""

import csv
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)

KEY = "test-key-not-a-secret"
os.environ["CHECKIN_KEY"] = KEY

from fastapi.testclient import TestClient  # noqa: E402  (after CHECKIN_KEY)

from app import _mask_email, app  # noqa: E402

# app.py resolves data.csv, roles.csv and the check-in log relative to the
# working directory, so serve requests from a scratch one. This has to happen
# after the import: confbadger.py loads fonts/ relative to the cwd at import
# time and raises if it can't find them.
os.chdir(tempfile.mkdtemp(prefix="checkin-search-"))

COLUMNS = ["Ticket number", "First Name", "Last Name", "Email", "Company", "Title", "Ticket title", "Discount", "Access code"]
ATTENDEES = [
    # Two John Smiths — the case the operator can only resolve with an email.
    ("T-001", "John", "Smith", "j.smith@worlduni.com", "World Uni"),
    ("T-002", "John", "Smith", "john.smith@globex.example", "Globex"),
    ("T-003", "Eve", "Moneypenny", "e.moneypenny@syard.co.uk", "Scotland Yard"),
    ("T-004", "Ada", "Lovelace", "ada@analytical.example", "Analytical"),
]

with open("data.csv", "w", newline="", encoding="utf-8") as fh:
    writer = csv.writer(fh)
    writer.writerow(COLUMNS)
    for ticket, first, last, email, company in ATTENDEES:
        writer.writerow([ticket, first, last, email, company, "", "Standard", "Standard", ""])

client = TestClient(app)
failures = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def search(q, key=KEY):
    headers = {"X-Checkin-Key": key} if key is not None else {}
    return client.get("/checkin/search", params={"q": q}, headers=headers)


print("the endpoint is still behind the shared key")
check("no key rejected", search("john", key=None).status_code == 401)
check("wrong key rejected", search("john", key="nope").status_code == 401)
check("right key accepted", search("john").status_code == 200)

print("name search still works")
rows = search("moneypenny").json()
check("surname match", [r["last_name"] for r in rows] == ["Moneypenny"], f"got {rows}")
check("card type still resolved", rows and rows[0]["card_type"] == "ATTENDEE")

print("email search separates two people with the same name")
both = search("john smith").json()
check("name alone is ambiguous", len(search("smith").json()) == 2, f"got {len(both)}")
one = search("j.smith@worlduni.com").json()
check("full address finds exactly one", len(one) == 1, f"got {len(one)}")
check("and it is the right one", one and one[0]["ticket_number"] == "T-001", f"got {one}")
check("partial address works", len(search("globex").json()) == 1)
check("domain-only works", len(search("syard").json()) == 1)
check("case insensitive", len(search("J.SMITH@WORLDUNI.COM").json()) == 1)

print("short queries do not fan out across addresses")
# "ex" appears in globex.example and analytical.example but in nobody's name.
check("two characters match no addresses", search("ex").json() == [], f"got {search('ex').json()}")
check("three characters do match", len(search("exa").json()) == 2)

print("no usable address ever leaves the endpoint")
for q in ["john", "smith", "j.smith@worlduni.com", "exa", "ada"]:
    body = search(q).text
    leaked = [email for _, _, _, email, _ in ATTENDEES if email in body]
    check(f"{q!r} leaks nothing", not leaked, f"leaked {leaked}")
check("masked field is present", all("email_masked" in r for r in search("smith").json()))
check(
    "masked field is what we expect",
    sorted(r["email_masked"] for r in search("smith").json())
    == ["j...@globex.example", "j...@worlduni.com"],
    f"got {[r['email_masked'] for r in search('smith').json()]}",
)

print("masking")
check("keeps first character and domain", _mask_email("j.smith@worlduni.com") == "j...@worlduni.com")
check("hides the local part length", _mask_email("a@x.io") == _mask_email("averylonglocal@x.io"))
check("single character local part", _mask_email("a@x.io") == "a...@x.io")
check("no address", _mask_email("") == "")
check("not an address", _mask_email("not-an-email") == "")
check("missing local part", _mask_email("@x.io") == "")
check("missing domain", _mask_email("a@") == "")
check("surrounding whitespace", _mask_email("  j.smith@worlduni.com  ") == "j...@worlduni.com")

print(f"\n{'FAILED: ' + ', '.join(failures) if failures else 'all checks passed'}")
sys.exit(1 if failures else 0)
