#!/usr/bin/env python3
"""cc90-lcd: live temperature display for the Jonsbo CC90 Digital cooler.

Pushes CPU temperature (digits) and GPU temperature (bars) to the cooler's
front LCD panel over hidraw. The panel protocol was reverse engineered from
the vendor's Windows software (DeviceDriver.exe) plus black-box testing; see
docs/PROTOCOL.md.

The panel has one 3-digit 7-segment readout and a decorative bar gauge:
  - bytes 1-3  : CPU temp digits (this is the only thing the vendor app shows)
  - byte 4 hi  : tens digit that drives the bar gauge *when a bar layout
                 (DES opcode 0x76/0x77) is active* -- this project uses it
                 to show GPU temp at 10 C/bar resolution
  - bytes 5-7  : second value slot; nothing renders there on the CC90

All device writes are gated behind --yes-writes.
"""

import argparse
import glob
import os
import subprocess
import sys
import time

import pydes  # vendored pyDes (MIT), see pydes.py

VENDOR_ID = "1a2c"
PRODUCT_ID = "4d84"
REPORT_LEN = 64  # report id 0x07 + 63-byte payload (FEATURE/OUTPUT, 504 bits)

# DES control channel (TF3-family protocol, see docs/PROTOCOL.md). The key is
# a firmware protocol constant extracted from the vendor binary, not a secret.
DES_KEY = bytes.fromhex("415FD9FA134258B7")
WAKE_OP = 0x70
BAR_LAYOUTS = {5: 0x76, 10: 0x77}
_des = pydes.des(DES_KEY, pydes.ECB, pad=None, padmode=pydes.PAD_NORMAL)


def des_frame(op, arg=0):
    """DES-framed control command: AA55 + DES-ECB(op,arg,0..0) + 01 + BB."""
    payload = bytearray(63)
    payload[0:2] = b"\xaa\x55"
    payload[2:10] = _des.encrypt(bytes([op, arg, 0, 0, 0, 0, 0, 0]))
    payload[10] = 0x01
    payload[31] = 0xBB
    return bytes(payload)


def find_hidraw():
    """Locate the CC90's screen hidraw node by USB VID:PID."""
    for uevent in glob.glob("/sys/class/hidraw/hidraw*/device/uevent"):
        try:
            with open(uevent) as f:
                for line in f:
                    if "HID_ID" in line and (
                        VENDOR_ID in line.lower() and PRODUCT_ID in line.lower()
                    ):
                        return "/dev/" + uevent.split("/")[4]
        except OSError:
            continue
    return None


def read_cpu_temp(path=None):
    """CPU temperature in degrees C from hwmon (k10temp/coretemp/zenpower)."""
    candidates = [path] if path else [
        t
        for p in glob.glob("/sys/class/hwmon/hwmon*")
        for t in sorted(glob.glob(p + "/temp*_input"))
        if open(p + "/name").read().strip()
        in ("k10temp", "coretemp", "zenpower", "cpu_thermal")
    ]
    for c in candidates:
        try:
            with open(c) as f:
                return int(f.read().strip()) / 1000.0
        except (OSError, ValueError):
            continue
    raise RuntimeError("no CPU temperature hwmon found (use --cpu-temp)")


def read_gpu_temp():
    """GPU temperature via nvidia-smi, or None if unavailable."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        return int(out.stdout.strip().splitlines()[0])
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
        return None


def build_frame(cpu_c, gpu_c):
    """Data frame: digits = CPU temp, bar nibble = GPU temp tens."""
    v1 = max(0, min(int(cpu_c), 199))  # vendor caps values at 199
    v2 = 0 if gpu_c is None else max(0, min(int(gpu_c), 199))
    buf = bytearray(REPORT_LEN)
    buf[0] = 0x07
    buf[1] = (v1 // 100) % 10
    buf[2] = (v1 // 10) % 10
    buf[3] = v1 % 10
    buf[4] = (min(v2 // 10, 10)) << 4  # bars: GPU tens (10 C per bar)
    buf[5] = (v2 // 100) % 10
    buf[6] = (v2 // 10) % 10
    buf[7] = v2 % 10
    return bytes(buf)


def open_device(device):
    fd = os.open(device, os.O_WRONLY)
    return fd


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--device", help="hidraw node (default: autodetect by VID:PID)")
    ap.add_argument("--cpu-temp", help="hwmon temp*_input path (default: autodetect)")
    ap.add_argument("--no-gpu", action="store_true", help="do not read GPU temp")
    ap.add_argument("--bars", type=int, choices=sorted(BAR_LAYOUTS), default=10,
                    help="bar gauge layout (5 or 10 bars); 0 = never send it")
    ap.add_argument("--interval", type=float, default=1.0, help="push interval (s)")
    ap.add_argument("--duration", type=float, default=0,
                    help="seconds to run (0 = forever)")
    ap.add_argument("--dry-run", action="store_true", help="print frames, no writes")
    ap.add_argument("--yes-writes", action="store_true",
                    help="actually write to the device (safety gate)")
    args = ap.parse_args()

    if args.dry_run:
        t = read_cpu_temp(args.cpu_temp)
        g = None if args.no_gpu else read_gpu_temp()
        print("cpu=%.1fC gpu=%s frame=%s" % (
            t, g, build_frame(t, g).hex(" ")))
        return

    if not args.yes_writes:
        ap.error("refusing to write without --yes-writes (use --dry-run to preview)")

    fd = None
    start = time.time()
    frames = 0
    while True:
        try:
            if fd is None:
                device = args.device or find_hidraw()
                if not device:
                    print("CC90 not found, retrying in 5s", flush=True)
                    time.sleep(5)
                    continue
                fd = open_device(device)
                # bind the bar gauge: wake + bar layout (volatile, firmware
                # resets to the static default layout on power cycle)
                if args.bars:
                    os.write(fd, b"\x07" + des_frame(WAKE_OP))
                    time.sleep(0.1)
                    os.write(fd, b"\x07" + des_frame(BAR_LAYOUTS[args.bars]))
                    time.sleep(0.2)
                print("pushing temps to %s (%d-bar layout)" % (device, args.bars),
                      flush=True)
            t = read_cpu_temp(args.cpu_temp)
            g = None if args.no_gpu else read_gpu_temp()
            os.write(fd, build_frame(t, g))
            frames += 1
            if frames % 30 == 1:
                print("[%d] cpu=%.1fC gpu=%s" % (frames, t, g), flush=True)
        except OSError as e:
            print("device error (%s), reopening in 5s" % e, flush=True)
            if fd is not None:
                os.close(fd)
                fd = None
            time.sleep(5)
            continue
        if args.duration and time.time() - start >= args.duration:
            break
        time.sleep(args.interval)
    if fd is not None:
        os.close(fd)


if __name__ == "__main__":
    main()
