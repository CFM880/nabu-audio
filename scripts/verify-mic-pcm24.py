#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Verify raw S24_LE capture before removing the user S16 workaround."""
import array
import datetime
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import wave


def main():
    repo = Path(__file__).resolve().parent.parent
    module = repo / 'out/mic-align/q6asm-dai.ko'
    with tempfile.TemporaryDirectory(prefix='q6asm-build-id-') as directory:
        note = Path(directory) / 'build-id'
        subprocess.run(['objcopy', '--dump-section',
                        f'.note.gnu.build-id={note}', str(module),
                        str(Path(directory) / 'module.ko')], check=True)
        expected = note.read_bytes()
    loaded = Path('/sys/module/q6asm_dai/notes/.note.gnu.build-id').read_bytes()
    if not expected or loaded != expected:
        raise SystemExit('The new q6asm_dai is not loaded. Install it and reboot audio1 first.')
    work = repo / 'diagnostics' / datetime.datetime.now().strftime('pcm24-%Y%m%d-%H%M%S')
    work.mkdir()
    results = {}
    for fmt, code, bits in [('S16_LE', 'h', 16), ('S24_LE', 'i', 24)]:
        raw = work / f'{fmt}.raw'
        print(f'Recording {fmt} for 4 seconds; please speak.', flush=True)
        subprocess.run(['arecord', '-q', '-D', 'hw:X5,1', '-t', 'raw',
                        '-f', fmt, '-r', '48000', '-c', '2', '-d', '4', str(raw)],
                       check=True, timeout=12)
        data = array.array(code, raw.read_bytes())
        if sys.byteorder != 'little':
            data.byteswap()
        if len(data) != 48000 * 4 * 2 or not any(data):
            raise SystemExit('Incomplete or silent capture; workaround retained.')
        results[fmt] = []
        for channel in range(2):
            values = data[channel::2]
            invalid = sum(not -(1 << (bits - 1)) <= x < (1 << (bits - 1)) for x in values)
            results[fmt].append({'channel': channel + 1, 'min': min(values),
                                 'max': max(values), 'out_of_range': invalid})
        (work / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        if any(row['out_of_range'] for row in results[fmt]):
            raise SystemExit(f'{fmt} alignment still incorrect; workaround retained. See {work}')
        if bits == 24:
            pcm = array.array('h', (x >> 8 for x in data))
            if sys.byteorder != 'little':
                pcm.byteswap()
            with wave.open(str(work / 'capture24-listen.wav'), 'wb') as wav:
                wav.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
                wav.writeframes(pcm.tobytes())
    print(json.dumps(results, indent=2), flush=True)
    # Only remove our exact workaround after checking the new loaded driver
    # and raw 24-bit capture. Preserve any user-edited configuration.
    config = Path.home() / '.config/wireplumber/wireplumber.conf.d/51-nabu-mic-s16.conf'
    if config.exists():
        if config.read_bytes() != (repo / 'config/51-nabu-mic-s16.conf').read_bytes():
            raise SystemExit('Workaround file was edited; leaving it in place.')
        disabled = config.with_suffix('.conf.disabled')
        if disabled.exists():
            raise SystemExit('Disabled config already exists; leaving config in place.')
        config.rename(disabled)
        try:
            subprocess.run(['systemctl', '--user', 'restart', 'wireplumber'], check=True)
        except subprocess.CalledProcessError:
            disabled.rename(config)
            raise
        print('S16 workaround disabled. Restarted WirePlumber.', flush=True)
    print(f'Listen with: aplay {work / "capture24-listen.wav"}')
    print('Raw alignment passed; confirm voice quality by listening and test default recording next.')


if __name__ == '__main__':
    main()
