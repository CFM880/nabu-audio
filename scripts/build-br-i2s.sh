#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
repo=$(cd -- "$(dirname -- "$0")/.." && pwd)
source=$repo
build=${KERNEL_BUILD:-$repo/out/audio1/build}
work=$repo/out/br-i2s
release=6.14.11-nabu-audio1
test "$(cat "$build/include/config/kernel.release")" = "$release"
test -s "$build/Module.symvers"
mkdir -p "$work/qdsp6"
cp "$source/sound/soc/qcom/sm8150.c" "$source/sound/soc/qcom/common.h" "$work/"
cp "$source/sound/soc/qcom/qdsp6/q6afe.h" "$work/qdsp6/"
printf 'obj-m := snd-soc-sm8150.o\nsnd-soc-sm8150-y := sm8150.o\n' > "$work/Kbuild"
make -C "$build" M="$work" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    LOCALVERSION= -j4 modules
test "$(modinfo -F name "$work/snd-soc-sm8150.ko")" = snd_soc_sm8150
test "$(modinfo -F vermagic "$work/snd-soc-sm8150.ko" | cut -d ' ' -f 1)" = "$release"
aarch64-linux-gnu-strip --strip-debug "$work/snd-soc-sm8150.ko"
(cd "$work" && sha256sum snd-soc-sm8150.ko > SHA256SUMS)
echo "Built $work/snd-soc-sm8150.ko for $release"
