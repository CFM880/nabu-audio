#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise the actual PCM trigger's command direction and error propagation."""
from pathlib import Path
import subprocess
import tempfile
repo = Path(__file__).resolve().parent.parent
source = (repo/'kernel-overlay/sound/soc/qcom/qdsp6/q6asm-dai.c').read_text()
start = source.index('static int q6asm_dai_trigger(')
end = source.index('\nstatic int q6asm_dai_open(', start)
c = r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
enum { SNDRV_PCM_TRIGGER_START, SNDRV_PCM_TRIGGER_RESUME,
 SNDRV_PCM_TRIGGER_PAUSE_RELEASE, SNDRV_PCM_TRIGGER_STOP,
 SNDRV_PCM_TRIGGER_SUSPEND, SNDRV_PCM_TRIGGER_PAUSE_PUSH };
enum { SNDRV_PCM_STREAM_PLAYBACK, SNDRV_PCM_STREAM_CAPTURE };
enum { Q6ASM_STREAM_STOPPED = 1, Q6ASM_STREAM_RUNNING, CMD_EOS, CMD_PAUSE };
struct snd_soc_component { int unused; };
struct q6asm_dai_rtd { void *audio_client; int stream_id, state; };
struct snd_pcm_runtime { void *private_data; };
struct snd_pcm_substream { struct snd_pcm_runtime *runtime; int stream; };
static int command, result, calls;
static struct q6asm_dai_rtd *active;
static int q6asm_cmd_nowait(void *client, int stream, int cmd)
{
 assert(client == active->audio_client && stream == active->stream_id);
 command = cmd; calls++;
 return result;
}
static int q6asm_run_nowait(void *client, int stream, int a, int b, int c)
{
 assert(!a && !b && !c);
 return q6asm_cmd_nowait(client, stream, -1);
}
''' + source[start:end] + r'''
int main(void)
{
 struct q6asm_dai_rtd data = { .audio_client = &data, .stream_id = 7 };
 struct snd_pcm_runtime runtime = { .private_data = &data };
 struct snd_pcm_substream stream = { .runtime = &runtime };
 active = &data;
 for (int dir = 0; dir < 2; dir++) {
  stream.stream = dir;
  for (int failure = 0; failure < 2; failure++) {
   data.state = Q6ASM_STREAM_RUNNING; calls = 0;
   result = failure ? -EIO : 0;
   assert(q6asm_dai_trigger(NULL, &stream, SNDRV_PCM_TRIGGER_STOP) == result);
   assert(calls == 1 && data.state == Q6ASM_STREAM_STOPPED);
   assert(command == (dir == SNDRV_PCM_STREAM_PLAYBACK ? CMD_EOS : CMD_PAUSE));
  }
  result = 0;
  assert(!q6asm_dai_trigger(NULL, &stream, SNDRV_PCM_TRIGGER_PAUSE_PUSH));
  assert(command == CMD_PAUSE);
  assert(!q6asm_dai_trigger(NULL, &stream, SNDRV_PCM_TRIGGER_START));
  assert(command == -1);
 }
 calls = 0;
 assert(q6asm_dai_trigger(NULL, &stream, 999) == -EINVAL && !calls);
 puts("Capture STOP uses PAUSE; playback EOS and error propagation preserved.");
}
'''
with tempfile.TemporaryDirectory() as d:
 src=Path(d)/'test.c'; exe=Path(d)/'test';src.write_text(c)
 subprocess.run(['cc','-Wall','-Wextra','-Wno-unused-parameter','-fsanitize=address,undefined',str(src),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
