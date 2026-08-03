#!/usr/bin/env python3
"""Status-frame decoder, and a probe of raw TCP 9100.

brother_ql throws away most of the status frame -- it decodes only the two
error bytes -- so decode() here unpacks the whole 32 bytes, including the mode
byte and the reserved fields. That is what showed the printer returning
"Error occurred" with both error bytes clear, which Brother's status tables do
not define. It is imported by the USB probes for the same reason.

The TCP side established a useful negative: **port 9100 on our QL-810W is
write-only**. It accepts a full job and never answers, not even a status
request or a PJL INFO query, so the network path gives no diagnostics at all.
Use SNMP for status over the network, or pyusb for a real back-channel.

    python3 net_probe.py --host 192.168.1.166            # expect (silent)
"""

import argparse
import socket
import time

INVALIDATE = b"\x00" * 200
INIT = b"\x1b\x40"
STATUS_REQUEST = b"\x1b\x69\x53"

# ESC i a {n}: dynamic command mode. 0=ESC/P, 1=raster, 3=P-touch Template.
MODE_ESCP = b"\x1b\x69\x61\x00"
MODE_RASTER = b"\x1b\x69\x61\x01"
MODE_TEMPLATE = b"\x1b\x69\x61\x03"

STATUS_TYPE = {
    0x00: "Reply to status request",
    0x01: "Printing completed",
    0x02: "Error occurred",
    0x04: "Turned off",
    0x05: "Notification",
    0x06: "Phase change",
}
PHASE_TYPE = {0x00: "Waiting to receive", 0x01: "Printing state"}
MEDIA_TYPE = {0x00: "No media", 0x0A: "Continuous", 0x0B: "Die-cut", 0xFF: "Incompatible"}

ERROR_1 = ["No media", "End of media", "Cutter jam", "Weak batteries",
           "(bit4)", "(bit5)", "Printer in use", "Printer turned off"]
ERROR_2 = ["Replace media", "Expansion buffer full", "Communication error",
           "Communication buffer full", "Cover open", "Overheating",
           "Black marking not detected", "System error"]


def decode(frame):
    if len(frame) < 32:
        return f"short frame ({len(frame)} bytes): {frame.hex(' ')}"
    b = frame[:32]
    errs = [n for i, n in enumerate(ERROR_1) if b[8] & (1 << i)]
    errs += [n for i, n in enumerate(ERROR_2) if b[9] & (1 << i)]
    out = [
        f"status      {STATUS_TYPE.get(b[18], hex(b[18]))}",
        f"phase       {PHASE_TYPE.get(b[19], hex(b[19]))} #{b[20] << 8 | b[21]}",
        f"media       {MEDIA_TYPE.get(b[11], hex(b[11]))} {b[10]}mm x {b[17]}mm",
        f"errors      {', '.join(errs) if errs else 'none (err1=%02X err2=%02X)' % (b[8], b[9])}",
        # Byte 15 is the printer's mode byte. brother_ql never looks at it, and
        # it is the one field that says which command language is actually live.
        f"mode byte   0x{b[15]:02X}",
        f"notif/model 0x{b[22]:02X} / series 0x{b[3]:02X} model 0x{b[4]:02X}",
        f"raw         {b.hex(' ')}",
    ]
    return "\n    ".join(out)


def talk(host, port, payloads, read_timeout=3.0):
    s = socket.create_connection((host, port), timeout=5)
    s.settimeout(read_timeout)
    try:
        for label, data in payloads:
            s.sendall(data)
            print(f"  -> {label} ({len(data)} bytes)")
            time.sleep(0.4)
            deadline = time.time() + read_timeout
            got = b""
            while time.time() < deadline:
                try:
                    chunk = s.recv(4096)
                except socket.timeout:
                    break
                if not chunk:
                    break
                got += chunk
                if len(got) >= 32:
                    break
            if got:
                for i in range(0, len(got), 32):
                    print(f"     {decode(got[i:i + 32])}")
            else:
                print("     (silent)")
    finally:
        s.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, default=9100)
    p.add_argument("--reset", action="store_true", help="clear error state first")
    p.add_argument("--set-mode", choices=["escp", "raster", "template"],
                   help="send ESC i a to switch dynamic command mode")
    args = p.parse_args()

    payloads = []
    if args.reset:
        payloads.append(("invalidate + init", INVALIDATE + INIT))
    if args.set_mode:
        payloads.append((f"ESC i a -> {args.set_mode}",
                         {"escp": MODE_ESCP, "raster": MODE_RASTER,
                          "template": MODE_TEMPLATE}[args.set_mode]))
    payloads.append(("status request", STATUS_REQUEST))

    talk(args.host, args.port, payloads)


if __name__ == "__main__":
    main()
