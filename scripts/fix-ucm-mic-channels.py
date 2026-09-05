#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Fix Nabu's Mic channel direction, preserving the rest of the installed UCM."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--install', action='store_true', help='Back up and update the system file')
args = parser.parse_args()
path = Path('/usr/share/alsa/ucm2/Xiaomi/nabu/HiFi.conf')
original = path.read_bytes()
text = original.decode()
# Restrict the replacement to the Mic device; never alter Speaker playback.
parts = re.split(r'(?m)(?=^SectionDevice\.)', text)
mic = [i for i, part in enumerate(parts) if part.startswith('SectionDevice."Mic" {')]
if len(mic) != 1:
    raise SystemExit('Expected exactly one Mic device; no changes made.')
i = mic[0]
if re.search(r'(?m)^\s*CaptureChannels\s+2\s*$', parts[i]):
    if re.search(r'(?m)^\s*PlaybackChannels\b', parts[i]):
        raise SystemExit('Conflicting channel declarations; no changes made.')
    print('Mic already declares CaptureChannels 2.')
    raise SystemExit(0)
parts[i], count = re.subn(r'(?m)^(\s*)PlaybackChannels(\s+2\s*)$', r'\1CaptureChannels\2', parts[i])
if count != 1:
    raise SystemExit('Expected exactly one Mic PlaybackChannels 2; no changes made.')
updated = ''.join(parts).encode()
print('Mic: PlaybackChannels 2 -> CaptureChannels 2', flush=True)
if not args.install:
    print('Dry run; use --install to apply.')
    raise SystemExit(0)
if os.geteuid():
    raise SystemExit('Installation requires root.')
backup = Path('/var/lib/nabu-audio/ucm-mic') / (hashlib.sha256(original).hexdigest() + '.conf')
backup.parent.mkdir(parents=True, exist_ok=True)
if backup.exists():
    if backup.read_bytes() != original:
        raise SystemExit('Backup mismatch; no changes made.')
else:
    shutil.copy2(path, backup)
stat = path.stat()
fd, name = tempfile.mkstemp(prefix='.HiFi.conf.', dir=path.parent)
try:
    with os.fdopen(fd, 'wb') as f:
        f.write(updated)
        f.flush()
        os.fsync(f.fileno())
    os.chown(name, stat.st_uid, stat.st_gid)
    os.chmod(name, stat.st_mode & 0o7777)
    if path.read_bytes() != original:
        raise RuntimeError('UCM changed during install; refusing to overwrite it.')
    os.replace(name, path)
finally:
    if os.path.exists(name):
        os.unlink(name)
print(f'Updated {path}; backup: {backup}')
