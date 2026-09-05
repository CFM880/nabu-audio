#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read amplifier interface configuration through kernel regmap debugfs."""
import os
import platform
import re
from pathlib import Path


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo; this script only reads registers.')
    print('Kernel:', platform.release())
    root = Path('/sys/kernel/debug/regmap')
    if not root.is_dir():
        raise SystemExit('regmap debugfs is unavailable')
    failed = False
    for amp, address in [('BR', '0040'), ('TR', '0041'),
                         ('BL', '0042'), ('TL', '0043')]:
        paths = sorted(root.glob(f'2-{address}*/registers'))
        if len(paths) != 1:
            print(f'{amp}: expected one regmap, found {len(paths)}')
            failed = True
            continue
        print(f'\n{amp}: {paths[0]}')
        found = False
        try:
            with paths[0].open() as registers:
                for line in registers:
                    match = re.match(r'([0-9a-fA-F]+):\s+([0-9a-fA-F]+)\s*$', line)
                    if not match:
                        continue
                    reg, value = (int(part, 16) for part in match.groups())
                    # Stop before the large DSP memory regions. Do not write
                    # debugfs, use raw I2C, or change playback/mixer state.
                    if reg > 0x4840:
                        break
                    if 0x4800 <= reg <= 0x4840:
                        print(f'  {reg:08x}: {value:08x}')
                    if reg == 0x4808:
                        found = True
                        fmt = (value & 0x0700) >> 8
                        label = {0: 'DSP_A', 2: 'I2S'}.get(fmt, 'other')
                        print(f'  ASP format: {label} ({fmt})')
            if not found:
                print('  SP_FORMAT was not readable')
                failed = True
        except OSError as error:
            print(f'  Read failed: {error}')
            failed = True
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
