#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
repo=$(cd -- "$(dirname -- "$0")/.." && pwd)
source=$repo/kernel-overlay
build=${KERNEL_BUILD:-$repo/out/audio1/build}
work=$repo/out/mic-align
release=6.14.11-nabu-audio1
test "$(cat "$build/include/config/kernel.release")" = "$release"
test -s "$build/Module.symvers"
mkdir -p "$work"
cp "$source/sound/soc/qcom/qdsp6/q6asm-dai.c" "$source/sound/soc/qcom/qdsp6/"*.h "$work/"
printf 'obj-m := q6asm-dai.o\n' > "$work/Kbuild"
make -C "$build" M="$work" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    LOCALVERSION= -j4 modules
test "$(modinfo -F name "$work/q6asm-dai.ko")" = q6asm_dai
test "$(modinfo -F vermagic "$work/q6asm-dai.ko" | cut -d ' ' -f 1)" = "$release"
aarch64-linux-gnu-strip --strip-debug "$work/q6asm-dai.ko"
(cd "$work" && sha256sum q6asm-dai.ko > SHA256SUMS)
echo "Built $work/q6asm-dai.ko for $release"
