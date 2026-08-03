#!/usr/bin/env python3
"""Render a single DK-11202 (62 x 29 mm) check-in label for the Brother QL-810W.

The label carries a first name and a QR of the bare ticket number. Everything
else — last name, company, title, attendee-type banner — is already on the
pre-printed card.
"""

import argparse
import io
import os

import pyqrcode
from PIL import Image, ImageDraw, ImageFont

# brother_ql raises on a die-cut raster of any other size rather than rescaling
# it, so this must match its '62x29' dots_printable exactly.
LABEL_SIZE = (696, 271)
DPI = 300

MARGIN = 12
QR_TEXT_GAP = 16
NAME_MAX_SIZE = 150
NAME_MIN_SIZE = 24

FONT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fonts", "OpenSans-Bold.ttf"
)


def _qr_image(ticket_number, box_px):
    qr = pyqrcode.create(ticket_number, error="M")
    modules = len(qr.code) + 8
    scale = max(1, box_px // modules)
    buf = io.BytesIO()
    qr.png(buf, scale=scale, quiet_zone=4)
    buf.seek(0)
    return Image.open(buf).convert("L")


def _fit_font(text, max_w, max_h):
    for size in range(NAME_MAX_SIZE, NAME_MIN_SIZE - 1, -1):
        font = ImageFont.truetype(FONT_PATH, size)
        box = font.getbbox(text)
        if box[2] - box[0] <= max_w and box[3] - box[1] <= max_h:
            return font, box
    font = ImageFont.truetype(FONT_PATH, NAME_MIN_SIZE)
    return font, font.getbbox(text)


def render_label(first_name, ticket_number):
    first_name = (first_name or "").strip()
    ticket_number = (ticket_number or "").strip()
    if not first_name:
        raise ValueError("first_name is required")
    if not ticket_number:
        raise ValueError("ticket_number is required")

    display_name = (
        first_name[0].upper() + first_name[1:] if len(first_name) > 1 else first_name.upper()
    )

    canvas = Image.new("L", LABEL_SIZE, 255)

    # Encoded verbatim: this is the join key against the ticketing export, so
    # any case or whitespace change here silently breaks hydration.
    qr = _qr_image(ticket_number, LABEL_SIZE[1] - 2 * MARGIN)
    qr_x = LABEL_SIZE[0] - MARGIN - qr.width
    canvas.paste(qr, (qr_x, (LABEL_SIZE[1] - qr.height) // 2))

    font, box = _fit_font(
        display_name, qr_x - QR_TEXT_GAP - MARGIN, LABEL_SIZE[1] - 2 * MARGIN
    )
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (MARGIN - box[0], (LABEL_SIZE[1] - (box[3] - box[1])) // 2 - box[1]),
        display_name,
        font=font,
        fill=0,
    )
    return canvas


def main():
    parser = argparse.ArgumentParser(
        description="Render one DK-11202 check-in label to a true-size PNG"
    )
    parser.add_argument("--name", required=True, help="Attendee first name")
    parser.add_argument("--ticket", required=True, help="Ticket number for the QR")
    parser.add_argument("--out", default="label-preview.png", help="Output PNG path")
    args = parser.parse_args()

    image = render_label(args.name, args.ticket)
    image.save(args.out, dpi=(DPI, DPI))
    print(
        f"{args.out}: {image.width}x{image.height}px @ {DPI}dpi "
        f"({image.width / DPI * 25.4:.1f} x {image.height / DPI * 25.4:.1f} mm)"
    )


if __name__ == "__main__":
    main()
