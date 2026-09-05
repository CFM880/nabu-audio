#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
repo=$(cd -- "$(dirname -- "$0")/.." && pwd)
source=$repo/kernel-overlay
build=${KERNEL_BUILD:-$repo/out/audio1/build}
work=$repo/out/codec-port-log
release=6.14.11-nabu-audio1
test "$(cat "$build/include/config/kernel.release")" = "$release"
test -s "$build/Module.symvers"
mkdir -p "$work"
cp "$source/sound/soc/codecs/"* "$work/"
printf 'obj-m := snd-soc-wcd934x.o\nsnd-soc-wcd934x-y := wcd934x.o\n' > "$work/Kbuild"
make -C "$build" M="$work" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    LOCALVERSION= -j4 modules
test "$(modinfo -F name "$work/snd-soc-wcd934x.ko")" = snd_soc_wcd934x
test "$(modinfo -F vermagic "$work/snd-soc-wcd934x.ko" | cut -d ' ' -f 1)" = "$release"
aarch64-linux-gnu-strip --strip-debug "$work/snd-soc-wcd934x.ko"
(cd "$work" && sha256sum snd-soc-wcd934x.ko > SHA256SUMS)
echo "Built $work/snd-soc-wcd934x.ko for $release"
