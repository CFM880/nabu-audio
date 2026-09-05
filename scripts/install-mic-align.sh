#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
# Update only the audio1 ASM driver, preserving a verified original.
set -euo pipefail
repo=$(cd -- "$(dirname -- "$0")/.." && pwd)
release=6.14.11-nabu-audio1
relative=kernel/sound/soc/qcom/qdsp6/q6asm-dai.ko
target=/lib/modules/$release/$relative
baseline=$repo/out/audio1/bundle/rootfs/lib/modules/$release/$relative
work=$repo/out/mic-align
backup=/var/lib/nabu-audio/mic-align/$release
mode=${1:---install}
case "$mode" in --install|--rollback) ;; *) echo 'Expected --install or --rollback' >&2; exit 2 ;; esac
test "$(id -u)" -eq 0 || { echo 'Run with sudo.' >&2; exit 1; }
test "$(uname -r)" = "$release" || { echo "Boot $release first." >&2; exit 1; }
test -f "$target"
test ! -L "$target"
test "$(modinfo -n q6asm_dai)" = "$target"
digest() { sha256sum "$1" | cut -d ' ' -f 1; }
if [ "$mode" = --rollback ]; then
    test -s "$backup/original.ko"
    (cd "$backup" && sha256sum --check --status original.sha256)
    if ! cmp -s "$target" "$backup/original.ko"; then
        test "$(digest "$target")" = "$(cat "$backup/installed.sha256")"
    fi
    replacement=$backup/original.ko
else
    (cd "$work" && sha256sum --check --status SHA256SUMS)
    replacement=$work/q6asm-dai.ko
    test "$(modinfo -F name "$replacement")" = q6asm_dai
    if [ ! -e "$backup/original.ko" ]; then
        # A known original must be present before accepting the first update.
        cmp -s "$baseline" "$target" || { echo 'Installed module differs from audio1 baseline.' >&2; exit 1; }
        install -d -m 0755 "$backup"
        install -m 0644 "$target" "$backup/original.ko"
        (cd "$backup" && sha256sum original.ko > original.sha256)
    fi
    (cd "$backup" && sha256sum --check --status original.sha256)
    if ! cmp -s "$target" "$backup/original.ko"; then
        test "$(digest "$target")" = "$(cat "$backup/installed.sha256")"
    fi
fi
test "$(modinfo -F vermagic "$replacement" | cut -d ' ' -f 1)" = "$release"
# The alignment fix targets the original PCM V2 protocol. Restore the
# unsuccessful V4 experiment before installing the DAI conversion.
if [ "$mode" = --install ]; then
    bash "$repo/scripts/restore-pcm-v2.sh"
fi
staging=$(mktemp "$(dirname "$target")/.mic-align.XXXXXX")
trap 'if [ -n "$staging" ]; then rm -f -- "$staging"; fi' EXIT
install -m 0644 "$replacement" "$staging"
cmp -s "$replacement" "$staging"
if [ "$mode" = --install ]; then
    digest "$replacement" > "$backup/installed.sha256"
fi
mv -T -- "$staging" "$target"
staging=
depmod -a "$release"
test "$(modinfo -n q6asm_dai)" = "$target"
cmp -s "$replacement" "$target"
echo "Completed $mode: $target"
echo "Original module: $backup/original.ko"
echo "Reboot into the same $release kernel to activate; EFI is unchanged."
