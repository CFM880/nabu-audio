#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise driver period conversion with stopped/freed runtime and bad tokens."""
import subprocess
from pathlib import Path

repo = Path(__file__).resolve().parent.parent
work = repo / 'out/mic-align'
work.mkdir(parents=True, exist_ok=True)
source = (repo / 'sound/soc/qcom/qdsp6/q6asm-dai.c').read_text()
start = source.index('static void q6asm_capture_s24(')
end = source.index('\nstatic void event_handler(', start)
helpers = source[start:end]
harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <endian.h>
#include <string.h>
typedef uint32_t __le32;
typedef uint32_t u32;
typedef int32_t s32;
#define cpu_to_le32(x) htole32(x)
#define le32_to_cpu(x) le32toh(x)
struct snd_dma_buffer { unsigned char *area; size_t bytes; };
struct snd_pcm_runtime { unsigned char *dma_area; };
struct snd_pcm_substream {
    struct snd_dma_buffer dma_buffer;
    struct snd_pcm_runtime *runtime;
    bool running;
};
struct q6asm_dai_rtd {
    struct snd_pcm_substream *substream;
    unsigned int pcm_count, pcm_size, periods;
};
static int locked;
#define snd_pcm_stream_lock_irqsave(s, f) do { \
    (void)(s); (f) = 0; assert(!locked); locked = 1; \
} while (0)
#define snd_pcm_stream_unlock_irqrestore(s, f) do { \
    (void)(s); (void)(f); assert(locked); locked = 0; \
} while (0)
static bool snd_pcm_running(struct snd_pcm_substream *s)
{
    assert(locked);
    return s->running;
}
''' + helpers + r'''
int main(void)
{
    __le32 words[6], saved[6];
    struct snd_pcm_runtime runtime = { .dma_area = NULL };
    struct snd_pcm_substream stream = {
        .dma_buffer = { .area = (unsigned char *)words, .bytes = sizeof(words) },
        .runtime = &runtime,
    };
    struct q6asm_dai_rtd prtd = {
        .substream = &stream, .pcm_count = 8, .pcm_size = sizeof(words), .periods = 3,
    };
    for (int i = 0; i < 6; i++)
        words[i] = htole32((uint32_t)(i - 3) << 8);
    memcpy(saved, words, sizeof(words));
    /* The crash case: completion after STOP/hw_free cleared runtime DMA. */
    assert(!q6asm_capture_s24_period(&prtd, 0));
    assert(!locked && !memcmp(saved, words, sizeof(words)));
    stream.running = true;
    /* Convert only the token's period using persistent fixed storage. */
    assert(q6asm_capture_s24_period(&prtd, 1));
    assert((int32_t)le32toh(words[2]) == -1 && words[3] == 0);
    assert(words[0] == saved[0] && words[1] == saved[1]);
    assert(words[4] == saved[4] && words[5] == saved[5]);
    assert(q6asm_capture_s24_period(&prtd, 2));
    assert(le32toh(words[4]) == 1 && le32toh(words[5]) == 2);
    memcpy(saved, words, sizeof(words));
    assert(!q6asm_capture_s24_period(&prtd, 3));
    assert(!q6asm_capture_s24_period(&prtd, UINT32_MAX));
    prtd.periods = UINT32_MAX;
    assert(!q6asm_capture_s24_period(&prtd, UINT32_MAX - 1));
    prtd.pcm_size = 16;
    assert(!q6asm_capture_s24_period(&prtd, 2));
    prtd.pcm_size = 32;
    assert(!q6asm_capture_s24_period(&prtd, 0));
    prtd.pcm_size = sizeof(words);
    prtd.pcm_count = 32;
    assert(!q6asm_capture_s24_period(&prtd, 0));
    prtd.pcm_count = 0;
    assert(!q6asm_capture_s24_period(&prtd, 0));
    prtd.pcm_count = 7;
    assert(!q6asm_capture_s24_period(&prtd, 0));
    prtd.pcm_count = 8;
    stream.dma_buffer.area = NULL;
    assert(!q6asm_capture_s24_period(&prtd, 0));
    assert(!locked && !memcmp(saved, words, sizeof(words)));
    puts("Late completion, fixed DMA storage, period selection and bounds passed.");
    return 0;
}
'''
(work / 'test-period.c').write_text(harness)
subprocess.run(['cc', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', str(work / 'test-period.c'),
                '-o', str(work / 'test-period')], check=True)
subprocess.run([str(work / 'test-period')], check=True)
