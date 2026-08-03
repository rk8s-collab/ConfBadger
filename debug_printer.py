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


def read_frame(backend, timeout_ms):
    """brother_ql's own read gives up almost immediately and its 'select'
    strategy is broken (pyusb.py calls select.select without importing it), so
    poll the backend ourselves until the deadline.
    """
    deadline = time.time() + timeout_ms / 1000.0
    while True:
        try:
            data = backend.read()
            if data:
                return data
        except Exception:
            pass
        if time.time() >= deadline:
            return b""
        time.sleep(0.05)


def show_status(backend, label, timeout_ms):
    data = read_frame(backend, timeout_ms)
    if not data:
        print(f"  {label:<28} (silent)")
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
    parser.add_argument("--no-cut", action="store_true",
                        help="Leave the cutter idle to rule out a jammed blade")
    parser.add_argument("--read-timeout", type=float, default=2000.0,
                        help="ms to wait for each status frame; brother_ql defaults to 10")
    args = parser.parse_args()

    printer = normalise_printer(args.printer)
    backend = backend_factory(args.backend)["backend_class"](printer)
    # Leave backend.strategy alone: brother_ql's 'select' path is broken.
    print(f"opened {printer} via {args.backend}, read timeout {args.read_timeout:.0f}ms\n")

    backend.write(STATUS_REQUEST)
    time.sleep(0.3)
    show_status(backend, "idle", args.read_timeout)

    if not args.send:
        backend.dispose()
        return

    data = build_instructions("Rob", "CNCFA23236346", label=args.label, cut=not args.no_cut)
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
            show_status(backend, "after raster", args.read_timeout)
            pending_raster = b""

        backend.write(ins)
        print(f"  -> {name}: {hex_format(ins)}")
        time.sleep(0.3)
        show_status(backend, f"after {name}", args.read_timeout)

    print("\npolling for completion")
    for i in range(10):
        time.sleep(1.0)
        s = show_status(backend, f"poll {i + 1}", args.read_timeout)
        if s and s["status_type"] in ("Printing completed", "Error occurred"):
            break

    backend.dispose()


if __name__ == "__main__":
    main()
