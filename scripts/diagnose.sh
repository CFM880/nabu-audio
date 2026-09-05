#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
set -uo pipefail
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

printf '\n=== Kernel and ALSA ===\n'
uname -a
cat /proc/asound/cards /proc/asound/pcm
printf '\n=== DSP state ===\n'
for dsp in /sys/class/remoteproc/remoteproc*; do
    printf '%s: ' "$dsp"
    paste -s -d ' ' "$dsp/name" "$dsp/state"
done
printf '\n=== QRTR services ===\n'
python3 "$script_dir/qrtr-services.py" --require-slim
printf '\n=== ADSP QRTR binding ===\n'
cat /sys/bus/rpmsg/devices/17300000.remoteproc:glink-edge.IPCRTR.-1.-1/uevent
printf '\n=== SLIMbus devices ===\n'
ls -l /sys/bus/slimbus/devices
printf '\n=== Audio boot messages ===\n'
journalctl -b -k --no-pager | rg -i 'slim|wcd|cs35|snd|sound|apr|adsp|qrtr|ipcrouter'
if [ "$(id -u)" -eq 0 ]; then
    printf '\n=== Deferred devices ===\n'
    cat /sys/kernel/debug/devices_deferred
    printf '\n=== ASoC components ===\n'
    cat /sys/kernel/debug/asoc/components
    printf '\n=== QRTR debug files ===\n'
    if [ -d /sys/kernel/debug/qrtr ]; then
        find /sys/kernel/debug/qrtr -maxdepth 2 -type f -print
    fi
fi
exit 0
