# QL-810W print fault — RESOLVED 2026-08-01

**Labels print. Use the default backend:**

```bash
python3 print_label.py --name Rob --ticket CNCFA23236346 --label 62
```

The fault was never in our renderer, our command stream, the mechanism, the
cutter, the media or the USB stack. **The printer refuses raw ESC/P raster
jobs**, and always did. The fix was to stop using the raster protocol and print
through the printer's AirPrint/IPP queue instead, which is the same path
P-touch Editor uses and the only path that has ever produced a label here.

Everything below the horizontal rule is the original handoff, kept because the
diagnostic ordering is still sound. Its *conclusion* — mechanism or power — was
wrong. See "What actually happened" first.

## What actually happened

Verified on the MacBook with the printer attached over both USB and Wi-Fi.

- **Raw raster fails identically on every transport.** The printer accepts the
  entire job, reports `Phase change / Printing state` of its own accord, then
  returns `Error occurred` the instant it receives `1A`, with **both error
  bytes `00`** — a state Brother's own status tables do not define. Reproduced
  over pyusb *and* over TCP 9100. Transport is not implicated.
- **The page counter never moved.** `prtMarkerLifeCount` stayed at 2 across
  every raster attempt, so none of them ever put ink on tape.
- **The command stream is spec-correct.** Checked instruction by instruction
  against Brother's *Raster Command Reference QL-800/810W/820NWB*: `g` (0x67) is
  the correct opcode for monochrome (`w` is two-colour only, and sending `w`
  made the printer silently discard the job), 62 mm continuous geometry is
  12 / 696 / 12 pins at 90 bytes per row, the 35-dot feed margin is the
  documented minimum, and the `ESC i K` bit mapping is right.
- **`hrPrinterDetectedErrorState` is `00`.** No jam, no cover, no media-out, no
  supply fault. The printer is not physically unwell; it is rejecting the job.
- **AirPrint prints the identical bitmap perfectly**, and the counter increments.

Ruled out by direct experiment, each on a freshly cleared printer: the cutter
(`--no-cut` fails the same), compression mode (both `M 02` and an explicit
`M 00` fail the same), the `ESC i z` valid-flag byte (Brother's documented
`0x86` for continuous tape fails the same as brother_ql's `0xCE`), the raster
opcode, CUPS contention (no `ipp-usb` process, empty queue), and Editor Lite
mode (no mass-storage interface; `/Volumes/BROTHER` is an unrelated 2024
installer disk image).

**Leading explanation, not fully confirmed:** the printer's web UI reports
`Emulation: P-touch Template` throughout, and SNMP lists four interpreters
(`PJL`, `ESC/P`, `Raster`, `P-touch Template`). brother_ql sends `ESC i a 01`
to switch dynamically to raster mode, and the printer never honours it — the
reported emulation never changes. That would explain acceptance-then-failure
precisely. Confirming it needs Brother's **Printer Setting Tool** (not
installed; only P-touch Editor is) to read and set the persistent Command Mode.
A PJL `ENTER LANGUAGE=RASTER` wrapper was tried and did not help.

**If you want the raster path back**, install Brother's Printer Setting Tool,
set Command Mode to *Raster*, and retest `--backend pyusb`. Nothing in our code
needs to change; the raster backends are still wired up. This is optional — the
CUPS path is fine for the event.

## Operational notes for the venue

- The production command is the one at the top of this file. No `--printer` or
  `--backend` flag is needed; it defaults to CUPS via the `Brother_QL_810W`
  queue.
- `--label 62` for the DK-22205 continuous roll, `--label 62x29` once DK-11209
  die-cut arrives. Only the flag changes.
- `ppi=300` is passed deliberately so CUPS places the bitmap 1:1 rather than
  scaling it to fill the page. **Do not remove it** — any rescale moves the QR
  module edges off the pixel grid and the code stops decoding reliably.
- The printer is at **192.168.1.166** (`BRWF44EB4FEE25D.local`, MAC
  `f4:4e:b4:fe:e2:5d`). Give it a DHCP reservation before the venue.
- **Port 9100 is write-only on this unit.** It accepts data and never answers,
  so TCP gives no diagnostics at all. Use SNMP for status instead — it works
  well and needs no cable:
  ```bash
  snmpget -v1 -c public 192.168.1.166 1.3.6.1.2.1.43.16.5.1.2.1.1
  ```
- **A latched error does not clear over the wire.** Invalidate + `ESC @` will
  not do it, even repeated. It needs a button press or a power cycle. Worth
  knowing at 8 am.
- Verified end to end: the printed QR scans in the deployed PWA and resolves to
  the correct ticket number.

## Tooling added

| Command | Purpose |
| --- | --- |
| `python3 net_probe.py --host 192.168.1.166` | Decodes a full 32-byte status frame, including the mode byte and error bytes brother_ql discards. Confirms 9100 is write-only on this unit. |

`test_label_render.py` needs `numpy` and `opencv-python-headless`, which are in
`requirements.txt` but not installed in `venv/`. Install them before relying on
it.

---

# Original handoff (conclusion superseded — see above)

You are picking this up on the MacBook that has the Brother QL-810W physically
attached. All the work so far was done on a Linux box with **no printer**, so
everything below was verified in software only. You can touch the hardware; that
is the whole point of the handoff.

Read this file top to bottom before running anything.

## The job this serves

Check-in desk for **KCD Melbourne 2026, held 5 August 2026**. On arrival an
attendee is looked up, and one peel-and-stick label is printed and applied to a
pre-printed badge card. The label carries the attendee's **first name** and a QR
of the **bare ticket number**. Nothing else — last name, company and the
attendee-type banner are already printed on the card.

The QR is the join key. Scanning it at a sponsor booth records a lead against
the ticket number, which is later hydrated from the ticketing export. If the QR
content changes in any way, that link silently breaks.

There are only a few days until the event. Prefer a working label over an
elegant one.

## Current state: one specific, reproducible failure

The printer accepts an entire job and then errors at the moment it should
physically print. No label emerges. The status LED flashes red.

Reproduce it with:

```bash
python3 debug_printer.py --printer usb://0x04f9:0x209c --backend pyusb --send
```

Last known output, abbreviated to the parts that matter:

```
  idle                  Reply to status request / Waiting to receive / Continuous length tape 62x0mm
  -> media/quality: 1B 69 7A CE 0A 3E 00 0F 01 00 00 00 00
  -> raster data (25203 bytes)
  after raster          Phase change / Printing state / Continuous length tape 62x0mm
  -> print: 1A
  after print           Error occurred / Printing state / Continuous length tape 62x0mm
     raw: 80 20 42 34 39 30 04 00 00 00 3E 0A 00 00 23 00 00 00 02 01 00 00 00 00 00 81 00 00 00 00 00 24
```

Read that carefully, because it is the core evidence:

- The printer is **healthy at idle** and senses the media correctly.
- Every setup command is accepted. Silence between commands is normal — a QL
  only volunteers status on a status request or a phase change.
- The raster is accepted in full and the printer replies **Phase change /
  Printing state**. It took all 25,203 bytes of image data and moved itself into
  printing phase of its own accord.
- The error appears **only on `1A`**, the print-and-feed command — the instant
  the motor and cutter engage.
- In the raw frame, **byte 8 and byte 9 are both `00`**. Those are Error
  Information 1 and 2. The printer is declaring an error while naming no cause.

Data path fine, fault at mechanical execution, no error code. That points at the
mechanism or its power supply, not at the byte stream.

## What is already conclusively ruled out — do not re-litigate

Each of these was verified, not assumed. Do not spend time re-deriving them.

- **The rendered image.** 696x271px, which is exactly `62x29`'s `dots_printable`.
  The die-cut branch of `brother_ql`'s `conversion.py` raises rather than
  rescaling, so any other size would fail loudly and immediately.
- **The QR contents.** Round-tripped through OpenCV's decoder and byte-compared
  against the input, including a lowercase case. `python3 test_label_render.py`
  re-checks this.
- **The command stream.** Decoded instruction by instruction. `ESC i z CE 0A 3E
  00 0F 01…` declares media type `0x0A` (continuous), width `0x3E` (62mm),
  length 0, and 271 raster lines. All correct for DK-22205.
- **Raster geometry.** 271 lines at opcode `0x67`, **90 bytes per row**, which is
  what the QL-810W's 720-dot head requires. The 696px image is padded correctly
  by the library.
- **USB writes.** All 25,447 bytes reach the OUT endpoint with no error.
- **Printer communication.** It answers status requests correctly and reports
  media accurately.
- **CUPS contention.** The `ippusb://` queue was removed. Did not help.
- **Power cycling.** Done several times. Did not help.

The software is not the problem. Resist the pull to go back and "fix" the
renderer — it is verified and it is not implicated.

## Diagnostic plan, in order

Work down this list. Stop when something prints.

**1. Press the Feed button on the printer. No computer involved.**

The single most informative test. If tape does not advance cleanly on a plain
Feed press, the fault is mechanical or power and no protocol work will help. If
Feed works perfectly but `1A` errors, that is genuinely surprising and worth
reporting back in detail.

**2. Confirm mains power, firmly seated.**

The QL-810W takes data on modest power but the head and feed motor draw hard the
instant `1A` fires. A loose barrel connector, a third-party adapter, or a fitted
and depleted PA-BT-4000LI battery base all produce exactly this signature: full
data acceptance, clean phase change, then failure at motor engagement with no
error bit — because from firmware's point of view nothing is *wrong*, it simply
could not execute.

**3. Reseat the roll.** Cover fully latched, tape end cut square, running under
both guides and gripped by the platen.

**4. Rule out the cutter.**

```bash
python3 debug_printer.py --printer usb://0x04f9:0x209c --backend pyusb --send --no-cut
```

`--no-cut` drops the auto-cut command and clears the cut-at-end bit; the stream
goes from `ESC i M 40 / ESC i A 01 / ESC i K 08` down to `ESC i K 00`. If it
prints without cutting, it is a jammed blade.

**5. Prove the hardware independently of our code — the key discriminator.**

`label-test.png` is committed at the repo root. It is the exact bitmap that
`brother_ql` is failing to print: 696x271px, 300dpi, 58.9 x 22.9mm, name "Rob"
and a QR that decodes to `CNCFA23236346`. Import it into **P-touch Editor** and
print it through Brother's own driver.

Set the media to match what is loaded (62mm continuous for DK-22205) and print
at **100% / actual size with no scaling**, or the QR module edges will land off
the pixel grid and may not scan.

This single test splits the diagnosis cleanly:

- **P-touch prints it** → mechanism, cutter, power and media are all fine. The
  fault is in the raw-raster path or the USB transport, and the diagnosis above
  is wrong. Go back to the protocol with that knowledge, and try the network
  backend (step 6) next, since it bypasses the USB stack entirely.
- **P-touch also fails** → it is the printer, full stop. The answer is service or
  a spare unit. Decide fast given the event date; do not keep debugging.

If it prints, also scan the QR with the deployed PWA to confirm it resolves to
the right ticket number. That closes the end-to-end check at the same time.

**6. Try the network backend.**

```bash
python3 print_label.py --name Rob --ticket CNCFA23236346 \
    --printer tcp://<printer-ip>:9100 --backend network --label 62
```

Different transport entirely, and it is the intended production path anyway
(single wireless printer, MacBook as host). Get the IP from the router's DHCP
table and give it a reservation so it survives a reboot at the venue.

**Note:** the network backend has **no read-back capability at all**
(`brother_ql/backends/helpers.py:67`). `did_print` is always `False` over TCP,
even on a perfect print. Judge purely by whether a label physically appears.

## Tools in this repo

| Command | Purpose |
| --- | --- |
| `python3 label_render.py --name Rob --ticket CNCFA23236346 --out preview.png` | Render only, no printer. PNG carries 300dpi — print at 100% scale to check physically. |
| `python3 test_label_render.py` | Full render/QR/geometry checks. Should print `all checks passed`. |
| `python3 print_label.py --dry-run` | Build the instruction bytes without a printer. |
| `python3 print_label.py --name … --ticket … --printer … --backend …` | Real print. |
| `python3 debug_printer.py --printer … --backend pyusb` | Status only, safe any time. |
| `python3 debug_printer.py … --send` | Walk the job command by command, status after each. |

Useful flags on `print_label.py`: `--label 62x29` (die-cut) or `--label 62`
(continuous), `--rotate 180` if inverted relative to the card, `--threshold`
(default 70) if washed out or too heavy, `--no-cut`.

## Label stock — this has already bitten us once

- **DK-11209** is the correct stock: die-cut **29 x 62mm**. Use `--label 62x29`.
- **DK-11202** is **62 x 100mm shipping labels** — the wrong product. The planning
  docs originally specified it by mistake. Loading it gives `Replace media
  error`. If you see that, the wrong roll is in the printer.
- **DK-22205** is 62mm continuous and works via `--label 62`. This is what is
  currently loaded, used as a stand-in.

DK-11209 was due to be bought on 2026-08-02. Once it arrives, retest with
`--label 62x29` and check registration inside the card's 63 x 34.5mm white box.
No code change is needed to switch — only the flag.

## brother_ql bugs found along the way

Version 0.9.4. These are real library defects, already worked around here:

1. **`select` strategy is dead code.** `backends/pyusb.py` calls `select.select()`
   at line 135 but never imports `select`, so setting `strategy = 'select'`
   raises `NameError` on every read. Leave the default `try_twice` alone.
2. **Read timeout is 10 milliseconds** (`backends/pyusb.py:69`), far too short to
   catch a completion frame from a printer that is physically feeding. This is
   why `print_label.py` reports `did_print=False` even when a print may have
   succeeded. `debug_printer.py` polls to its own deadline instead.
3. **`discover` emits an unusable identifier.** It prints
   `usb://vendor:product_serial` with an underscore, but the pyusb backend parses
   `usb://vendor:product/serial` and crashes on it. `normalise_printer()` in
   `print_label.py` strips the serial; vendor and product alone identify the
   printer.
4. **`brother_ql discover` does not work on the network backend** — it raises
   `NotImplementedError`. Get the IP from the router instead.

The `deprecation warning: brother_ql.devicedependent is deprecated` line on every
run is benign. Ignore it.

## Constraints

- **Do not change the QR contents.** The bare ticket number, verbatim, no
  prefix, no case change, no whitespace. It is the hydration join key.
- **Do not change `LABEL_SIZE`.** 696x271 is dictated by the library.
- **Do not put PII on the label.** First name and ticket QR only. No email, no
  company, no last name.
- **`data.csv` is gitignored** and will hold a real attendee export. Only
  `*.sample.csv` is tracked. Do not re-include real data.
- Commits are authored `rk8s-collab <rk8s.contact@gmail.com>`. `origin` is
  `rk8s-collab/ConfBadger`, `upstream` is `rkenefeck/ConfBadger`. Work on a
  branch, PR to upstream, never push to `rkenefeck`.

## Definition of done

A real label physically emerges from the QL-810W, carrying the first name and a
QR that scans in the deployed PWA and resolves to the correct ticket number.
Report back what fixed it — the cause matters for the venue runbook, since the
same failure at 8am on event day needs a known answer.

If you get through step 5 with no print and Brother's own driver also fails, stop
and escalate rather than continuing to debug. At that point it is a hardware
replacement decision and it is time-critical.
