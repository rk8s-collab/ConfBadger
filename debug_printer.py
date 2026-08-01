#!/usr/bin/env python3
"""Talk to the QL-810W one command at a time and dump the status after each.

    python3 debug_printer.py --printer usb://0x04f9:0x209c --backend pyusb
    python3 debug_printer.py --printer usb://0x04f9:0x209c --backend pyusb --send

Without --send it only asks the printer how it is, which is safe at any time.
With --send it walks the job command by command, reading status between each, so
the command that trips the error light is the one named just above the status
that turns bad.
"""

import argparse
import time

from brother_ql.backends import backend_factory
from brother_ql.reader import OPCODES, chunker, hex_format, interpret_response, match_opcode

from print_label import build_instructions, normalise_printer

STATUS_REQUEST = b"\x1b\x69\x53"


def opcode_name(instruction):
    try:
        return OPCODES[match_opcode(instruction)][0]
    except Exception:
        return "unknown"


def show_status(backend, label):
    try:
        data = backend.read()
    except Exception as exc:
        print(f"  {label:<28} (no status: {type(exc).__name__})")
        return None
    if not data:
        print(f"  {label:<28} (no status)")
        return None
    try:
        s = interpret_response(data)
    except Exception:
        print(f"  {label:<28} undecodable: {hex_format(data)}")
        return None
    line = (f"  {label:<28} {s['status_type']} / {s['phase_type']} / "
            f"{s['media_type']} {s['media_width']}x{s['media_length']}mm")
    if s["errors"]:
        line += f" / ERRORS: {', '.join(s['errors'])}"
    print(line)
    # brother_ql decodes only error bytes 8 and 9. An 'Error occurred' with no
    # bits set means the cause sits in a byte it ignores, so show the raw frame.
    if s["status_type"] == "Error occurred" and not s["errors"]:
        print(f"  {'':<28} raw: {hex_format(data)}")
    return s


def main():
    parser = argparse.ArgumentParser(description="Stage-by-stage QL-810W probe")
    parser.add_argument("--printer", required=True)
    parser.add_argument("--backend", default="pyusb",
                        choices=["network", "pyusb", "linux_kernel"])
    parser.add_argument("--send", action="store_true",
                        help="Walk the real job command by command")
    parser.add_argument("--label", default="62", choices=["62x29", "62"])
    parser.add_argument("--read-timeout", type=float, default=2000.0,
                        help="ms to wait for each status frame; brother_ql defaults to 10")
    args = parser.parse_args()

    printer = normalise_printer(args.printer)
    backend = backend_factory(args.backend)["backend_class"](printer)
    backend.read_timeout = args.read_timeout
    if hasattr(backend, "strategy"):
        backend.strategy = "select"
    print(f"opened {printer} via {args.backend}, read timeout {args.read_timeout:.0f}ms\n")

    backend.write(STATUS_REQUEST)
    time.sleep(0.3)
    show_status(backend, "idle")

    if not args.send:
        backend.dispose()
        return

    data = build_instructions("Rob", "CNCFA23236346", label=args.label)
    instructions = chunker(data)
    print(f"\nwalking {len(instructions)} instructions ({len(data)} bytes)\n")

    pending_nulls = b""
    pending_raster = b""

    for ins in instructions:
        name = opcode_name(ins)
        if name == "preamble":
            pending_nulls += ins
            continue
        if pending_nulls:
            backend.write(pending_nulls)
            print(f"  -> invalidate ({len(pending_nulls)} nulls)")
            pending_nulls = b""
        if "raster" in name:
            pending_raster += ins
            continue
        if pending_raster:
            backend.write(pending_raster)
            print(f"  -> raster data ({len(pending_raster)} bytes)")
            time.sleep(0.3)
            show_status(backend, "after raster")
            pending_raster = b""

        backend.write(ins)
        print(f"  -> {name}: {hex_format(ins)}")
        time.sleep(0.3)
        show_status(backend, f"after {name}")

    print("\npolling for completion")
    for i in range(10):
        time.sleep(1.0)
        s = show_status(backend, f"poll {i + 1}")
        if s and s["status_type"] in ("Printing completed", "Error occurred"):
            break

    backend.dispose()


if __name__ == "__main__":
    main()
