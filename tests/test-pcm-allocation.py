#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check the actual PCM allocator against Nabu's DSP end-address boundary."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parent.parent
source = (repo / 'kernel-overlay/sound/soc/qcom/qdsp6/q6asm-dai.c').read_text()
start = source.index('static int q6asm_dai_pcm_new(')
end = source.index('\nstatic const struct snd_soc_dapm_widget', start)
harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#define SZ_4K 4096
#define SNDRV_DMA_TYPE_DEV 1
struct snd_pcm { int unused; };
struct snd_soc_component { void *dev; };
struct snd_soc_pcm_runtime { struct snd_pcm *pcm; };
static const struct { size_t buffer_bytes_max; } q6asm_dai_hardware_playback = {524288};
static bool nabu;
static size_t requested;
static int alloc_result;
static bool of_machine_is_compatible(const char *name)
{
 assert(!strcmp(name, "xiaomi,nabu"));
 return nabu;
}
static int snd_pcm_set_fixed_buffer_all(struct snd_pcm *pcm, int type,
                                       void *dev, size_t bytes)
{
 assert(pcm && dev && type == SNDRV_DMA_TYPE_DEV);
 requested = bytes;
 return alloc_result;
}
''' + source[start:end] + r'''
int main(void)
{
 struct snd_pcm pcm;
 struct snd_soc_component component = {.dev = &pcm};
 struct snd_soc_pcm_runtime runtime = {.pcm = &pcm};
 uint64_t end = 1ULL << 32;
 nabu = false;
 assert(q6asm_dai_pcm_new(&component, &runtime) == 0);
 assert(requested == 524288);
 /* Original allocation at the top: its full DSP map hits the boundary. */
 assert(end - requested + 524288 == end);
 nabu = true;
 assert(q6asm_dai_pcm_new(&component, &runtime) == 0);
 assert(requested >= 524288 + SZ_4K);
 /* Every permitted request, including a non-page-sized buffer rounded by
  * q6asm, must finish before the next 32-bit address window. */
 for (size_t bytes = 256; bytes <= 524288; bytes += 32) {
  uint64_t mapped = (bytes + SZ_4K - 1) & ~(uint64_t)(SZ_4K - 1);
  assert(end - requested + mapped < end);
 }
 assert(q6asm_dai_hardware_playback.buffer_bytes_max == 524288);
 alloc_result = -12;
 assert(q6asm_dai_pcm_new(&component, &runtime) == -12);
 puts("Nabu full-size and rounded DSP maps avoid the boundary; other machines and allocation errors preserved.");
}
'''
with tempfile.TemporaryDirectory(prefix='nabu-pcm-allocation-') as directory:
    src = Path(directory) / 'test.c'
    binary = Path(directory) / 'test'
    src.write_text(harness)
    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    '-o', str(binary), str(src)], check=True)
    subprocess.run([str(binary)], check=True)
