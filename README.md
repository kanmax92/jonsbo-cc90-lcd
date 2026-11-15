# jonsbo-cc90-lcd

Linux driver for the **Jonsbo CC90 Digital** cooler's front LCD panel:
live **CPU temperature** on the 7-segment digits and **GPU temperature** on
the bar gauge. No vendor software, no Docker, no VM — one small Python daemon
plus a systemd user service.

```
┌─────────────────────────────┐
│  4 9 °C   ▂▂▂▂▂▃▃▂▂▂        │
│  CPU temp   GPU temp bars   │
└─────────────────────────────┘   (not the real panel, but close enough)
```

The vendor's Windows app only shows CPU temp — the bar gauge is dead chrome
there. This driver binds the bars to GPU temperature via a layout command the
vendor app never sends. More in [docs/PROTOCOL.md](docs/PROTOCOL.md).

## Hardware & access

The panel is a Semico `1a2c:4d84` USB HID device (`lsusb` mislabels it
"SEMICO USB Gaming Keyboard" — it is the cooler). The screen lives on its
second HID interface. Read-only USB access needs write permission on the
hidraw node; the shipped udev rule grants it to the `input` group.

```bash
sudo cp udev/60-jonsbo-cc90.rules /usr/lib/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger
sudo usermod -aG input "$USER"   # re-login afterwards
```

## Manual install

```bash
pip install pydes            # or use the vendored pydes.py
sudo install -Dm755 cc90_lcd.py /usr/local/bin/cc90-lcd
cc90-lcd --dry-run           # preview a frame
sudo cc90-lcd --yes-writes   # or run unprivileged once udev rule is in place
```

Flags: `--bars {10,5,0}` (gauge layout; 0 = leave stock), `--no-gpu`,
`--interval`, `--duration`, `--device`, `--cpu-temp` (hwmon path override),
`--dry-run`. All device writes are gated behind `--yes-writes`.

## systemd user service

```bash
install -Dm644 systemd/cc90-lcd.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now cc90-lcd
loginctl enable-linger "$USER"   # start at boot, before login
journalctl --user -u cc90-lcd -f
```

The service sends the wake + bar-layout commands and re-applies them whenever
the device re-enumerates (replug, reboot), so the gauge survives power cycles.

## AUR

Arch package `jonsbo-cc90-lcd` (installs the script, udev rule, and user
service unit): see the `aur/` branch or the AUR page. After installing:

```bash
sudo udevadm control --reload && sudo udevadm trigger
systemctl --user enable --now cc90-lcd
```

## What works / what doesn't

| Feature | Status |
|---|---|
| CPU temp digits (3-digit 7-seg) | ✅ live, 1 Hz |
| GPU temp on bars (10 °C/bar) | ✅ live |
| Partial bars / finer resolution | ❓ untested (byte 4 low nibble) |
| Second value slot (bytes 5–7) | ❌ renders nothing on this panel |
| Any other panel content | ❌ bytes 8–63 are dead on this firmware |

Recovery if the screen ever looks odd: stop the service, unplug the cooler's
internal USB lead for 5 s, replug. That has always been enough.

## Protocol summary

Two channels on HID report `0x07` (63-byte payload):

1. **Data frame** (plaintext, no crypto): digits in bytes 1–3, bar-drive
   nibble in byte 4's high half, second value in bytes 5–7 (unused on CC90).
2. **DES control channel** (`AA55` + DES-ECB block + `01` + `BB`): layout and
   power opcodes — `0x70` wake, `0x71/72/74` sleep, `0x75` °C indicator,
   `0x76` temp+5-bars, `0x77` temp+10-bars, `0x58` re-theme, `0x38`
   stop-video. The DES key is a firmware protocol constant extracted from the
   vendor binary.

Full details, frame layouts, and the reverse-engineering story:
[docs/PROTOCOL.md](docs/PROTOCOL.md).

## Disclaimer

Unofficial, reverse-engineered. No Jonsbo/Semico affiliation. Writes are
limited to HID feature/output reports on the vendor-defined interface — no
firmware-touching opcodes are used. Use at your own risk.

## License

MIT. Vendored `pydes.py` is [pyDes](https://github.com/toddw/pyDes) (MIT).
