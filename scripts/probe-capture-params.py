#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Find where capture hw_params fails on Nabu, stage by stage.

Walks every ALSA call of a capture (and, for comparison, playback) setup and
reports the exact failing call with its errno, plus the negotiated parameters
before and after the failure. Never starts a stream: no DSP R/W commands are
issued, so no module, service or mixer state is touched. Playback idle.
"""
import argparse
import ctypes as C
import json

lib = C.CDLL('libasound.so.2')
p = C.c_void_p
SND_PCM_STREAM_PLAYBACK = 0
SND_PCM_STREAM_CAPTURE = 1

specs = {
    'snd_pcm_open': ([C.POINTER(p), C.c_char_p, C.c_int, C.c_int], C.c_int),
    'snd_pcm_close': ([p], C.c_int),
    'snd_pcm_hw_params_malloc': ([C.POINTER(p)], C.c_int),
    'snd_pcm_hw_params_free': ([p], None),
    'snd_pcm_hw_params_any': ([p, p], C.c_int),
    'snd_pcm_hw_params_set_access': ([p, p, C.c_int], C.c_int),
    'snd_pcm_hw_params_set_format': ([p, p, C.c_int], C.c_int),
    'snd_pcm_hw_params_set_channels': ([p, p, C.c_uint], C.c_int),
    'snd_pcm_hw_params_set_rate': ([p, p, C.c_uint, C.c_int], C.c_int),
    'snd_pcm_hw_params_set_period_size': ([p, p, C.c_ulong, C.c_int], C.c_int),
    'snd_pcm_hw_params_set_buffer_size': ([p, p, C.c_ulong], C.c_int),
    'snd_pcm_hw_params': ([p, p], C.c_int),
    'snd_pcm_hw_params_current': ([p, p], C.c_int),
    'snd_pcm_hw_params_get_format': ([p, C.POINTER(C.c_int)], C.c_int),
    'snd_pcm_hw_params_get_channels': ([p, C.POINTER(C.c_uint)], C.c_int),
    'snd_pcm_hw_params_get_rate': ([p, C.POINTER(C.c_uint), C.POINTER(C.c_int)], C.c_int),
    'snd_pcm_hw_params_get_period_size': ([p, C.POINTER(C.c_ulong), C.POINTER(C.c_int)], C.c_int),
    'snd_pcm_hw_params_get_buffer_size': ([p, C.POINTER(C.c_ulong)], C.c_int),
    'snd_strerror': ([C.c_int], C.c_char_p),
}
for name, (types, result) in specs.items():
    fn = getattr(lib, name)
    fn.argtypes, fn.restype = types, result

# snd_pcm_access_t / snd_pcm_format_t values (stable ABI numbers)
ACCESS = 3            # SND_PCM_ACCESS_RW_INTERLEAVED
FORMATS = {'S16_LE': 2, 'S24_LE': 6}

CASES = [
    # (direction, format, rate, channels, period frames, 0=exact / 1=near, buffer frames or None)
    ('capture',  'S16_LE', 48000, 2, 1024, 0, None),
    ('capture',  'S24_LE', 48000, 2, 1024, 0, None),
    ('capture',  'S24_LE', 48000, 2, 512,  0, None),
    ('capture',  'S16_LE', 48000, 2, 2048, 0, None),
    ('capture',  'S24_LE', 48000, 2, 512,  0, 4096),
    ('playback', 'S24_LE', 48000, 2, 1024, 0, None),
]


def run(case):
    direction, fmt, rate, chans, period, near, buf = case
    stream = SND_PCM_STREAM_CAPTURE if direction == 'capture' else SND_PCM_STREAM_PLAYBACK
    device = options.device if direction == 'capture' else options.device_p
    row = {'direction': direction, 'device': device, 'format': fmt,
           'rate': rate, 'channels': chans, 'requested_period_frames': period}
    pcm, params = p(), p()
    rc = lib.snd_pcm_open(C.byref(pcm), device.encode(), stream, 1)
    row['open'] = rc
    if rc < 0:
        row['error'] = lib.snd_strerror(rc).decode()
        return row
    try:
        def step(name, fn, *args):
            rc = fn(pcm, params, *args)
            row[name] = rc
            if rc < 0:
                row['error'] = lib.snd_strerror(rc).decode()
            return rc

        lib.snd_pcm_hw_params_malloc(C.byref(params))
        if step('any', lib.snd_pcm_hw_params_any) < 0:
            return row
        if step('access', lib.snd_pcm_hw_params_set_access, ACCESS) < 0:
            return row
        if step('format', lib.snd_pcm_hw_params_set_format, FORMATS[fmt]) < 0:
            return row
        if step('channels', lib.snd_pcm_hw_params_set_channels, chans) < 0:
            return row
        if step('rate', lib.snd_pcm_hw_params_set_rate, rate, 0) < 0:
            return row
        # prefer exact period, fall back to nearest so we still reach hw_params
        rc = lib.snd_pcm_hw_params_set_period_size(pcm, params, period, 0)
        row['period'] = rc
        if rc < 0:
            rc = lib.snd_pcm_hw_params_set_period_size(pcm, params, period, 1)
            row['period_near_retry'] = rc
            if rc < 0:
                row['error'] = lib.snd_strerror(rc).decode()
                return row
        if buf:
            if step('buffer', lib.snd_pcm_hw_params_set_buffer_size, buf) < 0:
                return row
        if step('hw_params', lib.snd_pcm_hw_params) < 0:
            # keep the narrowed params for the report: read them back
            lib.snd_pcm_hw_params_current(pcm, params)
            for getter, key, cast in (
                    (lib.snd_pcm_hw_params_get_format, 'negotiated_format', None),
                    (lib.snd_pcm_hw_params_get_channels, 'negotiated_channels', None),
                    (lib.snd_pcm_hw_params_get_rate, 'negotiated_rate', None),
                    (lib.snd_pcm_hw_params_get_period_size, 'negotiated_period_frames', None),
                    (lib.snd_pcm_hw_params_get_buffer_size, 'negotiated_buffer_frames', None)):
                val = C.c_ulong()
                try:
                    rc2 = getter(params, C.byref(val))
                    if rc2 == 0:
                        row[key] = val.value
                except Exception:
                    pass
            return row
        lib.snd_pcm_hw_params_current(pcm, params)
        for getter, key in (
                (lib.snd_pcm_hw_params_get_format, 'negotiated_format'),
                (lib.snd_pcm_hw_params_get_channels, 'negotiated_channels'),
                (lib.snd_pcm_hw_params_get_rate, 'negotiated_rate'),
                (lib.snd_pcm_hw_params_get_period_size, 'negotiated_period_frames'),
                (lib.snd_pcm_hw_params_get_buffer_size, 'negotiated_buffer_frames')):
            val = C.c_ulong()
            try:
                if getter(params, C.byref(val)) == 0:
                    row[key] = val.value
            except Exception:
                pass
        row['result'] = 'hw_params-ok'
        return row
    finally:
        if params:
            lib.snd_pcm_hw_params_free(params)
        lib.snd_pcm_close(pcm)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--device', default='hw:X5,0')
parser.add_argument('--device-p', default='hw:X5,0')
options = parser.parse_args()

for case in CASES:
    print(json.dumps(run(case)), flush=True)
