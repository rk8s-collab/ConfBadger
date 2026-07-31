#!/usr/bin/env python3
"""Print one check-in label on a Brother QL-810W loaded with DK-11202 stock.

    python3 print_label.py --name Rob --ticket CNCFA23236346 \
        --printer tcp://192.168.1.50:9100

Run with --dry-run to build the printer instructions without a printer.
"""

import argparse
import sys

from brother_ql.backends.helpers import send
from brother_ql.conversion import convert
from brother_ql.raster import BrotherQLRaster

from label_render import render_label

MODEL = "QL-810W"
LABEL = "62x29"


def normalise_printer(identifier):
    """brother_ql's discover prints usb://vendor:product_serial, but its pyusb
    backend parses usb://vendor:product/serial and chokes on the underscore
    form. Vendor and product alone identify the printer, so drop the serial.
    """
    if identifier and identifier.startswith("usb://") and "_" in identifier:
        return identifier.split("_", 1)[0]
    return identifier


def build_instructions(first_name, ticket_number, threshold=70.0, rotate=0, label=LABEL):
    qlr = BrotherQLRaster(MODEL)
    qlr.exception_on_warning = True
    return convert(
        qlr=qlr,
        images=[render_label(first_name, ticket_number)],
        label=label,
        rotate=rotate,
        threshold=threshold,
        dither=False,
        compress=False,
        red=False,
        hq=True,
        cut=True,
    )


def main():
    parser = argparse.ArgumentParser(description="Print one DK-11202 check-in label")
    parser.add_argument("--name", required=True, help="Attendee first name")
    parser.add_argument("--ticket", required=True, help="Ticket number for the QR")
    parser.add_argument(
        "--printer",
        help="tcp://<ip>:9100 for network, or usb://0x04f9:<product-id> for USB",
    )
    parser.add_argument("--backend", choices=["network", "pyusb", "linux_kernel"])
    parser.add_argument(
        "--label",
        default=LABEL,
        choices=["62x29", "62"],
        help="62x29 for DK-11209 die-cut, or 62 for DK-22205 continuous tape",
    )
    parser.add_argument(
        "--rotate",
        type=int,
        default=0,
        choices=[0, 180],
        help="Use 180 if the label prints upside down relative to the card",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=70.0,
        help="Black/white cutoff in percent; raise it if the print looks washed out",
    )
    parser.add_argument(
        "--dry-run",
        metavar="PATH",
        nargs="?",
        const="label-instructions.bin",
        help="Write instructions to a file instead of printing",
    )
    args = parser.parse_args()

    instructions = build_instructions(
        args.name,
        args.ticket,
        threshold=args.threshold,
        rotate=args.rotate,
        label=args.label,
    )

    if args.dry_run:
        with open(args.dry_run, "wb") as handle:
            handle.write(instructions)
        print(f"{args.dry_run}: {len(instructions)} bytes, not printed")
        return

    if not args.printer:
        parser.error("--printer is required unless --dry-run is used")

    printer = normalise_printer(args.printer)
    if printer != args.printer:
        print(f"using {printer} (dropped the serial discover appended)")

    status = send(
        instructions=instructions,
        printer_identifier=printer,
        backend_identifier=args.backend,
        blocking=True,
    )
    print(f"outcome={status['outcome']} did_print={status['did_print']}")
    if status.get("printer_state"):
        print(f"printer_state={status['printer_state']}")
    if not status["did_print"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
