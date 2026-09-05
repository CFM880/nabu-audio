#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Locate capture warnings across prepare/read/drop/hw_free/close on Nabu.

Records eight seconds per format, discarding audio. Does not change mixer,
services or modules. Run with the capture device idle. JSON includes kernel
messages and monotonic phase timestamps; a clean log alone is not proof of
error-free hardware, since the codec rate-limits and masks FIFO interrupts.
"""
import argparse
import ctypes as C
import errno
import json
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', default='hw:X5,1')
    parser.add_argument('--cycles', type=int, choices=range(1, 7), default=1)
    parser.add_argument('--latency-us', type=int, choices=[100000, 500000], default=500000)
    args = parser.parse_args()
    lib = C.CDLL('libasound.so.2')
    ptr = C.c_void_p
    specs = {
        'snd_pcm_open': ([C.POINTER(ptr), C.c_char_p, C.c_int, C.c_int], C.c_int),
        'snd_pcm_set_params': ([ptr, C.c_int, C.c_int, C.c_uint, C.c_uint,
                                C.c_int, C.c_uint], C.c_int),
        'snd_pcm_readi': ([ptr, ptr, C.c_ulong], C.c_long),
        'snd_pcm_wait': ([ptr, C.c_int], C.c_int),
        'snd_strerror': ([C.c_int], C.c_char_p),
    }
    for name in ('prepare', 'start', 'drop', 'hw_free', 'close'):
        specs['snd_pcm_' + name] = ([ptr], C.c_int)
    for name, (types, result) in specs.items():
        fn = getattr(lib, name)
        fn.argtypes, fn.restype = types, result

    report = {'phases': [], 'captures': []}
    since = time.time()

    def check(rc):
        if rc < 0:
            raise RuntimeError(lib.snd_strerror(rc).decode())
        return rc

    def mark(fmt, phase):
        report['phases'].append(dict(format=fmt, phase=phase,
                                     monotonic_us=time.monotonic_ns() // 1000))

    try:
        for fmt, code, sample in [('S16_LE', 2, C.c_int16),
                                  ('S24_LE', 6, C.c_int32)] * args.cycles:
            pcm = ptr()
            check(lib.snd_pcm_open(C.byref(pcm), args.device.encode(), 1, 1))
            try:
                mark(fmt, 'configure_prepare')
                check(lib.snd_pcm_set_params(pcm, code, 3, 2, 48000, 0, args.latency_us))
                check(lib.snd_pcm_prepare(pcm))
                time.sleep(1)
                mark(fmt, 'read')
                check(lib.snd_pcm_start(pcm))
                data = (sample * 2048)()
                frames, nonzero = 0, 0
                minimum, maximum = None, None
                deadline = time.monotonic() + 12
                while frames < 48000 * 8:
                    if time.monotonic() > deadline:
                        raise TimeoutError('capture exceeded 12 seconds')
                    count = lib.snd_pcm_readi(pcm, data, min(1024, 48000 * 8 - frames))
                    if count == -errno.EAGAIN:
                        check(lib.snd_pcm_wait(pcm, 1000))
                        continue
                    check(count)
                    if count == 0:
                        raise RuntimeError('capture returned zero frames')
                    values = data[:count * 2]
                    lo, hi = min(values), max(values)
                    minimum = lo if minimum is None else min(minimum, lo)
                    maximum = hi if maximum is None else max(maximum, hi)
                    nonzero += sum(v != 0 for v in values)
                    frames += count
                report['captures'].append(dict(format=fmt, frames=frames,
                    nonzero_samples=nonzero, minimum=minimum, maximum=maximum))
                mark(fmt, 'drop')
                check(lib.snd_pcm_drop(pcm))
                time.sleep(1)
                mark(fmt, 'hw_free')
                check(lib.snd_pcm_hw_free(pcm))
                time.sleep(1)
            finally:
                mark(fmt, 'close')
                check(lib.snd_pcm_close(pcm))
            time.sleep(1)
        mark('', 'done')
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        result = subprocess.run(['journalctl', '-b', '-k', '--since',
                                 f'@{since:.6f}', '-o', 'json', '--no-pager'],
                                capture_output=True, text=True)
        report['journal_returncode'] = result.returncode
        report['journal_stderr'] = result.stderr
        report['kernel_messages'] = [json.loads(line) for line in result.stdout.splitlines()]
        print(json.dumps(report, indent=2))
    return 1 if 'error' in report or result.returncode else 0


if __name__ == '__main__':
    raise SystemExit(main())
