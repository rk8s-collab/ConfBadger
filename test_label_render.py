#!/usr/bin/env python3
"""Checks for the DK-11202 label raster. Run: python3 test_label_render.py"""

import sys

import numpy as np

from label_render import LABEL_SIZE, MARGIN, QR_TEXT_GAP, _qr_image, render_label

NAMES = ["Rob", "Kugomoorthy", "Jean-Christophe", "Mary Jane", "Li"]
TICKET = "CNCFA23236346"

failures = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


print("exact raster size (brother_ql rejects anything else)")
for n in NAMES:
    img = render_label(n, TICKET)
    check(f"{n} -> {LABEL_SIZE}", img.size == LABEL_SIZE, f"got {img.size}")

print("artwork stays inside the margins and clear of the QR")
qr_x = LABEL_SIZE[0] - MARGIN - _qr_image(TICKET, LABEL_SIZE[1] - 2 * MARGIN).width
for n in NAMES:
    a = np.array(render_label(n, TICKET))
    ink = np.argwhere(a < 128)
    (y0, x0), (y1, x1) = ink.min(axis=0), ink.max(axis=0)
    inside = x0 >= MARGIN and x1 <= LABEL_SIZE[0] - MARGIN and y0 >= MARGIN and y1 <= LABEL_SIZE[1] - MARGIN
    gutter_clear = (a[:, qr_x - QR_TEXT_GAP : qr_x] < 128).sum() == 0
    check(f"{n} within margins", inside, f"x[{x0},{x1}] y[{y0},{y1}]")
    check(f"{n} clear of QR", gutter_clear)

print("required fields")
for bad in [("", TICKET), ("Rob", ""), (None, TICKET), ("Rob", None)]:
    try:
        render_label(*bad)
        check(f"{bad} rejected", False, "no error raised")
    except ValueError:
        check(f"{bad} rejected", True)

print("QR encodes the ticket number verbatim")
try:
    import cv2

    detector = cv2.QRCodeDetector()
    for ticket in [TICKET, "CNCFE23213608", "abc-123-lower"]:
        decoded, _, _ = detector.detectAndDecode(np.array(render_label("Rob", ticket)))
        check(f"{ticket} round-trips", decoded == ticket, f"got {decoded!r}")
except ImportError:
    print("  skip (opencv not installed; pip install opencv-python-headless)")

print("brother_ql accepts the raster for a QL-810W")
try:
    from brother_ql.conversion import convert
    from brother_ql.raster import BrotherQLRaster

    data = convert(
        qlr=BrotherQLRaster("QL-810W"),
        images=[render_label("Kugomoorthy", TICKET)],
        label="62x29",
        rotate=0,
        red=False,
        cut=True,
    )
    check("instructions generated", len(data) > 0, f"{len(data)} bytes")
except ImportError:
    print("  skip (brother_ql not installed)")

print(f"\n{'FAILED: ' + ', '.join(failures) if failures else 'all checks passed'}")
sys.exit(1 if failures else 0)
