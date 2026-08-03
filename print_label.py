#!/usr/bin/env python3
"""Print one check-in label on a Brother QL-810W.

    python3 print_label.py --name Rob --ticket CNCFA23236346

Default is the CUPS backend, which is the only path proven to print on our
unit. See PRINTER_HANDOFF.md: the printer's raw ESC/P raster interpreter
rejects every well-formed raster job at the print command, over both USB and
TCP, while the AirPrint/IPP queue prints the same label correctly. The raster
backends are kept for the day the printer's command mode is switched to Raster.

Run with --dry-run to build the printer instructions without a printer.
"""

import argparse
import os
import subprocess
import sys
import tempfile

from brother_ql.backends.helpers import send
from brother_ql.conversion import convert
from brother_ql.raster import BrotherQLRaster

from label_render import DPI, render_label

MODEL = "QL-810W"
LABEL = "62x29"

#: CUPS queue for the QL-810W's AirPrint entry (Brother QL-810W-AirPrint).
QUEUE = "Brother_QL_810W"

#: PageSize to hand CUPS per label stock. The rendered bitmap is the same
#: 62 x 29 mm either way; only the media it lands on differs.
PAGE_SIZES = {
    "62x29": "29x62mm",          # DK-11209 die-cut, a real PPD page size
    "62": "Custom.62x29mm",      # DK-22205 62 mm continuous, cut to length
}


def normalise_printer(identifier):
    """brother_ql's discover prints usb://vendor:product_serial, but its pyusb
    backend parses usb://vendor:product/serial and chokes on the underscore
    form. Vendor and product alone identify the printer, so drop the serial.
    """
    if identifier and identifier.startswith("usb://") and "_" in identifier:
        return identifier.split("_", 1)[0]
    return identifier


def build_instructions(first_name, ticket_number, threshold=70.0, rotate=0, label=LABEL, cut=True):
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
        cut=cut,
    )


def print_via_cups(first_name, ticket_number, label=LABEL, queue=QUEUE, cut=True, copies=1):
    """Print through the printer's AirPrint queue.

    ppi=300 is what keeps the QR scannable: it tells CUPS the bitmap is already
    at its true physical size, so the image is placed 1:1 instead of being
    scaled to fill the page. Any rescale lands the QR module edges off the
    pixel grid and the code stops decoding reliably.
    """
    image = render_label(first_name, ticket_number)
    handle, path = tempfile.mkstemp(prefix="confbadger-", suffix=".png")
    os.close(handle)
    try:
        image.save(path, dpi=(DPI, DPI))
        argv = [
            "lp",
            "-d", queue,
            "-o", "PageSize=%s" % PAGE_SIZES[label],
            "-o", "ppi=%d" % DPI,
            "-o", "ColorModel=Gray",
            "-o", "CutMedia=%s" % ("EndOfPage" if cut else "None"),
            "-n", str(copies),
            path,
        ]
        result = subprocess.run(argv, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout).strip())
        return result.stdout.strip()
    finally:
        os.unlink(path)


def main():
    parser = argparse.ArgumentParser(description="Print one check-in label")
    parser.add_argument("--name", required=True, help="Attendee first name")
    parser.add_argument("--ticket", required=True, help="Ticket number for the QR")
    parser.add_argument(
        "--printer",
        help="tcp://<ip>:9100 for network, or usb://0x04f9:<product-id> for USB",
    )
    parser.add_argument(
        "--backend",
        default="cups",
        choices=["cups", "network", "pyusb", "linux_kernel"],
        help="cups is the only backend that prints on our unit; the raster "
             "backends need the printer's command mode set to Raster",
    )
    parser.add_argument("--queue", default=QUEUE, help="CUPS queue name")
    parser.add_argument("--copies", type=int, default=1)
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
        "--no-cut",
        action="store_true",
        help="Leave the cutter idle; use to tell a jammed blade from a print fault",
    )
    parser.add_argument(
        "--dry-run",
        metavar="PATH",
        nargs="?",
        const="label-instructions.bin",
        help="Write instructions to a file instead of printing",
    )
    args = parser.parse_args()

    if args.dry_run:
        instructions = build_instructions(
            args.name,
            args.ticket,
            threshold=args.threshold,
            rotate=args.rotate,
            label=args.label,
            cut=not args.no_cut,
        )
        with open(args.dry_run, "wb") as handle:
            handle.write(instructions)
        print(f"{args.dry_run}: {len(instructions)} bytes, not printed")
        return

    if args.backend == "cups":
        print(print_via_cups(
            args.name,
            args.ticket,
            label=args.label,
            queue=args.queue,
            cut=not args.no_cut,
            copies=args.copies,
        ))
        return

    instructions = build_instructions(
        args.name,
        args.ticket,
        threshold=args.threshold,
        rotate=args.rotate,
        label=args.label,
        cut=not args.no_cut,
    )

    if not args.printer:
        parser.error("--printer is required for the raster backends")

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
