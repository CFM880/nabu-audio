#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
# Restore only a recognized PCM V4 experiment; a PCM V2 baseline is a no-op.
set -euo pipefail
repo=$(cd -- "$(dirname -- "$0")/.." && pwd)
release=6.14.11-nabu-audio1
relative=kernel/sound/soc/qcom/qdsp6/q6asm.ko
target=/lib/modules/$release/$relative
baseline=$repo/out/audio1/bundle/rootfs/lib/modules/$release/$relative
backup=/var/lib/nabu-audio/mic-pcm24/$release
test "$#" -eq 0
test "$(id -u)" -eq 0
test "$(uname -r)" = "$release"
test -f "$target" && test ! -L "$target"
test "$(modinfo -n q6asm)" = "$target"
if cmp -s "$target" "$baseline"; then
    echo 'Original PCM V2 module already installed.'
    exit 0
fi
(cd "$backup" && sha256sum --check --status original.sha256)
cmp -s "$backup/original.ko" "$baseline"
test "$(sha256sum "$target" | cut -d ' ' -f 1)" = "$(cat "$backup/installed.sha256")"
test "$(modinfo -F name "$baseline")" = q6asm
test "$(modinfo -F vermagic "$baseline" | cut -d ' ' -f 1)" = "$release"
staging=$(mktemp "$(dirname "$target")/.pcm-v2.XXXXXX")
trap 'if [ -n "$staging" ]; then rm -f -- "$staging"; fi' EXIT
install -m 0644 "$baseline" "$staging"
cmp -s "$baseline" "$staging"
mv -T -- "$staging" "$target"
staging=
depmod -a "$release"
echo 'Restored PCM V2 module. Reboot audio1 to activate.'
