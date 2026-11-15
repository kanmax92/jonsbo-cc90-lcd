# Protocol reference: Jonsbo CC90 Digital LCD panel

Reverse engineered 2026-09-20 → 2026-11-15 from the vendor Windows software
(`DeviceDriver.exe`, decompiled with Ghidra) plus supervised black-box testing
on hardware. Everything below was verified against the actual device.

## Device identity

- USB: Semico **`1a2c:4d84`** — `lsusb` label "SEMICO USB Gaming Keyboard" is
  a firmware-baked mislabel; this IS the cooler's display.
- Two HID interfaces:
  - iface 0 → fake keyboard node (ignore)
  - iface 1 → **screen channel** (vendor usage pages 0xFF00/0xFF01)
- Report `0x07`: FEATURE **and** OUTPUT, 63-byte payload. Low-Speed USB
  (1.5 Mbps), no OUT endpoints → host→device traffic is SET_REPORT control
  transfers; a hidraw `write()` of 64 bytes (`0x07` + 63) works.

## Channel 1: data frame (plaintext)

Sent by the vendor app at 1 Hz. **No DES, no `AA55`, no opcode** — the DES
channel was a red herring for data.

| byte | meaning |
|---|---|
| 0 | report ID `0x07` |
| 1 | temp hundreds digit |
| 2 | temp tens digit |
| 3 | temp units digit |
| 4 | high nibble: temp tens → drives bar gauge when a bar layout is active |
| 5–7 | second value, same 3-digit split (never renders on the CC90) |
| 8–63 | zeros (dead on this firmware build) |

The vendor caps values at 199. Byte 4 is the interesting one: the vendor app
puts the **CPU** tens digit there (bars act as a coarse CPU gauge), but the
firmware just renders whatever nibble it gets — so byte 4 can carry the **GPU**
tens instead. That is what this driver does.

How byte 4 was confirmed to drive the bars:

- 10-bar layout active, byte4 tens=2 / slot2=90 → ~3 bars; byte4 tens=9 /
  slot2=10 → ~9 bars (divergence test)
- CPU-only burn (CPU 89 °C, GPU 40 °C) → ~8–9 bars
- GPU load spike (44→53 °C) with GPU tens in byte 4 → bars rose one notch and
  settled back
- Slot 2 (bytes 5–7) tested with 0/99/0 alternation → digits area unchanged;
  nothing renders there on this panel

## Channel 2: DES control channel

Framing (32-byte region of the 63-byte payload):

```
AA 55 | DES-ECB(8 bytes: op, arg, 0, 0, 0, 0, 0, 0) | 01 | ...zeros... | BB (offset 31)
```

DES key (firmware protocol constant extracted from the vendor binary, not a
secret): `41 5F D9 FA 13 42 58 B7`.

Verified opcodes:

| opcode | effect |
|---|---|
| `0x70` | wake |
| `0x71`, `0x72`, `0x74` | sleep variants |
| `0x75` | show °C indicator |
| `0x76` | layout: temp + 5 bars + °C |
| `0x77` | layout: temp + 10 bars |
| `0x58` | reset memory / re-theme (screen visibly changes) |
| `0x38` | stop video |

**`0x76`/`0x77` are the key to the bar gauge**: the stock firmware layout has
static bars, and the vendor app never sends DES frames — so out of the box the
bars are dead chrome. Sending `0x77` (optionally after `0x70` wake) binds the
bars to byte 4's high nibble. The layout is volatile: re-send after power
cycles / replugs.

The vendor app's Windows binary contains **no DES sender at all**; it only
broadcasts the plaintext data frame. Both channels were found by decompiling
`DeviceDriver.exe` (HidD_SetFeature resolved via GetProcAddress → broadcast
writer → frame builder `FUN_00408260`; sensor enumeration `FUN_004057e0`).

## Panel capabilities (CC90 Digital, this firmware)

- One 3-digit 7-segment readout + one bar gauge — that's all.
- Bytes 8–63 of the data frame: swept in 9 groups, no visible reaction.
- Bytes 5–7 (second value): renders nothing (other models of the shared
  Semico/Jonsbo platform may render it).
- Byte 4 **low** nibble: untested in the bound layouts — might modulate a
  partial bar (finer than 10 °C/bar).

## Recovery

Screen retains the last pushed frame. If it ever looks wrong: stop the pusher,
unplug the internal USB lead for 5 s (or reboot), replug. No firmware-touching
opcodes were ever used in this work.

## Tools used

- Ghidra decompilation (REA toolchain) of `DeviceDriver.exe`
- Black-box HID probing with supervised single-write tests
- `pyDes` for DES-ECB (validated against the NIST test vector)
