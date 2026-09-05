#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise the actual driver helper over every signed 24-bit sample."""
import subprocess
from pathlib import Path
repo = Path(__file__).resolve().parent.parent
source = (repo / 'kernel-overlay/sound/soc/qcom/qdsp6/q6asm-dai.c').read_text()
start = source.index('static void q6asm_capture_s24(')
end = source.index('\n}', start) + 2
helper = source[start:end]
harness = r"""
#include <stdint.h>
#include <stdio.h>
#include <endian.h>
typedef uint32_t __le32;
typedef int32_t s32;
#define cpu_to_le32(x) htole32(x)
#define le32_to_cpu(x) le32toh(x)
""" + helper + r"""
int main(void)
{
    __le32 words[3];
    for (int32_t value = -8388608; value <= 8388607; value++) {
        words[0] = 0x12345678;
        words[1] = htole32((uint32_t)value << 8);
        words[2] = 0x87654321;
        q6asm_capture_s24(&words[1], 1);
        if ((int32_t)le32toh(words[1]) != value ||
            words[0] != 0x12345678 || words[2] != 0x87654321)
            return 1;
    }
    words[0] = 0x12345678;
    q6asm_capture_s24(words, 0);
    if (words[0] != 0x12345678)
        return 2;
    puts("All 16777216 signed 24-bit values preserved; bounds and zero count passed.");
    return 0;
}
"""
work = repo / 'out/mic-align'
work.mkdir(parents=True, exist_ok=True)
(work / 'test-conversion.c').write_text(harness)
subprocess.run(['cc', '-O2', '-Wall', '-Wextra', '-Werror', '-fsanitize=undefined',
                str(work / 'test-conversion.c'), '-o', str(work / 'test-conversion')], check=True)
subprocess.run([str(work / 'test-conversion')], check=True)
