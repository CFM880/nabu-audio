#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Play a quiet tone through each amplifier, restoring its original volume."""
import math
import re
import signal
import struct
import subprocess
import tempfile
import time
import wave
from pathlib import Path

AMPS = ('BR', 'TR', 'BL', 'TL')

def mixer(amp, value=None):
    cmd = ['amixer', '-c', 'X5', 'cget' if value is None else 'cset',
           f'name={amp} Digital PCM Volume']
    if value is not None:
        cmd.append(str(value))
    return subprocess.check_output(cmd, text=True)

def interrupted(signum, frame):
    raise KeyboardInterrupt

def main():
    saved = {amp: int(re.search(r': values=(\d+)', mixer(amp))[1]) for amp in AMPS}
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGHUP, interrupted)
    with tempfile.TemporaryDirectory(prefix='nabu-speaker-test-') as tmp:
        path = Path(tmp) / 'tone.wav'
        with wave.open(str(path), 'wb') as wav:
            wav.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
            data = bytearray()
            for n in range(96000):
                ramp = min(1, n / 2400, (95999 - n) / 2400)
                value = int(32767 * 0.0158 * ramp * math.sin(2 * math.pi * 440 * n / 48000))
                data.extend(struct.pack('<hh', value, value))
            wav.writeframes(data)
        try:
            for number, selected in enumerate(AMPS, 1):
                for amp in AMPS:
                    mixer(amp, 0)
                mixer(selected, min(saved[selected], 817))
                print(f'{number}: {selected}', flush=True)
                subprocess.run(['aplay', '-q', '-D', 'hw:X5,0', str(path)],
                               check=True, timeout=8)
                time.sleep(2)
        finally:
            for amp, value in saved.items():
                try:
                    mixer(amp, value)
                except subprocess.CalledProcessError as error:
                    print(f'Volume restore failed for {amp}: {error}', flush=True)

if __name__ == '__main__':
    main()
