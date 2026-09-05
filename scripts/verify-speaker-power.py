#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Verify four Nabu amplifiers power off at idle and on during silent playback.

Requires root for DAPM debugfs and an idle playback device. Does not unload
modules, change mixers, or stop desktop services. Run after rebooting the new
machine driver; an idle-only check can be selected with --idle-only.
"""
import argparse
import os
from pathlib import Path
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--idle-only', action='store_true')
options = parser.parse_args()
if os.geteuid():
    raise SystemExit('Run with sudo to read DAPM debugfs.')
root = Path('/sys/kernel/debug/asoc/Xiaomi Pad 5')

def check(label, expected):
    bad = []
    for amp, address in [('BR','0040'),('TR','0041'),('BL','0042'),('TL','0043')]:
        paths = list(root.glob(f'cs35l41.2-{address}/dapm/{amp} Main AMP'))
        if len(paths) != 1:
            raise RuntimeError(f'{amp}: expected one DAPM widget, found {len(paths)}')
        line = paths[0].read_text().splitlines()[0]
        state = line.split(':', 1)[1].split()[0]
        print(f'{label}: {line}', flush=True)
        if state != expected:
            bad.append(amp)
    if bad:
        raise RuntimeError(f'{label}: expected {expected} for {", ".join(bad)}')

check('idle', 'Off')
if not options.idle_only:
    command = ['aplay','-q','-D','hw:X5,0','-t','raw','-f','S16_LE',
               '-r','48000','-c','2','-d','3','/dev/zero']
    proc = subprocess.Popen(command)
    try:
        time.sleep(1)
        if proc.poll() is not None:
            raise RuntimeError('Playback ended before the power-state check; check whether hw:X5,0 is busy.')
        check('playing silence', 'On')
        if proc.wait(timeout=8):
            raise RuntimeError('Silent playback failed.')
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    time.sleep(.5)
    check('closed', 'Off')
print('Speaker power-state checks passed.')
