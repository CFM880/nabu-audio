#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise the machine driver's legacy-route repair with immutable DT routes."""
from pathlib import Path
import subprocess
import tempfile
source = (Path(__file__).resolve().parent.parent /
          'kernel-overlay/sound/soc/qcom/sm8150.c').read_text()
start = source.index('static const struct snd_soc_dapm_widget nabu_speaker_widgets[]')
end = source.index('\nstatic int sm8150_platform_probe', start)
harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define BIT(n) (1U << (n))
#define GENMASK(h,l) (((1U << ((h)+1))-1) & ~((1U << (l))-1))
#define GFP_KERNEL 0
struct snd_soc_dapm_widget { const char *name; };
#define SND_SOC_DAPM_SPK(n,e) { .name = (n) }
struct snd_soc_dapm_route { const char *sink, *control, *source; };
struct snd_soc_card {
 void *dev;
 const struct snd_soc_dapm_route *of_dapm_routes;
 int num_of_dapm_routes;
 const struct snd_soc_dapm_widget *dapm_widgets;
 int num_dapm_widgets;
};
static bool nabu, fail_alloc;
static bool of_machine_is_compatible(const char *name)
{ assert(!strcmp(name, "xiaomi,nabu")); return nabu; }
static void *devm_kmemdup(void *dev, const void *data, size_t size, int flags)
{
 (void)dev; (void)flags;
 if (fail_alloc) return NULL;
 void *copy=malloc(size); assert(copy); memcpy(copy,data,size); return copy;
}
#define dev_info(...) ((void)0)
''' + source[start:end] + r'''
static bool has_edge(const struct snd_soc_card *c, const char *source, const char *sink)
{
 for (int i=0; i<c->num_of_dapm_routes; i++)
  if (!strcmp(c->of_dapm_routes[i].source,source) &&
      !strcmp(c->of_dapm_routes[i].sink,sink)) return true;
 return false;
}
int main(void)
{
 const struct snd_soc_dapm_route original[] = {
  {"RX_BIAS",NULL,"MCLK"}, {"AMIC1",NULL,"MIC BIAS3"},
  {"MultiMedia1 Playback",NULL,"BR SPK"},
  {"MultiMedia1 Playback",NULL,"TR SPK"},
  {"MultiMedia1 Playback",NULL,"BL SPK"},
  {"MultiMedia1 Playback",NULL,"TL SPK"},
  {"other sink",NULL,"BR SPK"},
  {"MultiMedia1 Playback","special control","BR SPK"},
 };
 struct snd_soc_card card={.of_dapm_routes=original,.num_of_dapm_routes=ARRAY_SIZE(original)};
 assert(!sm8150_fix_nabu_speaker_routes(&card));
 assert(card.of_dapm_routes==original && !card.num_dapm_widgets);
 nabu=true; fail_alloc=true;
 assert(sm8150_fix_nabu_speaker_routes(&card)==-ENOMEM);
 assert(card.of_dapm_routes==original && !card.num_dapm_widgets);
 fail_alloc=false;
 assert(!sm8150_fix_nabu_speaker_routes(&card));
 assert(card.of_dapm_routes!=original && card.num_dapm_widgets==4);
 const char *outputs[]={"BR SPK","TR SPK","BL SPK","TL SPK"};
 for (int j=0;j<4;j++) {
  assert(!strcmp(original[j+2].sink,"MultiMedia1 Playback"));
  assert(!strcmp(card.of_dapm_routes[j+2].source, outputs[j]));
  assert(!strcmp(card.of_dapm_routes[j+2].sink,card.dapm_widgets[j].name));
  assert(!card.of_dapm_routes[j+2].control);
 }
 /* The three unguarded outputs cannot feed the frontend anymore. The
  * explicit, unrelated controlled BR route is intentionally preserved. */
 assert(!has_edge(&card,"TR SPK","MultiMedia1 Playback"));
 assert(!has_edge(&card,"BL SPK","MultiMedia1 Playback"));
 assert(!has_edge(&card,"TL SPK","MultiMedia1 Playback"));
 assert(!memcmp(card.of_dapm_routes,original,2*sizeof(*original)));
 assert(!memcmp(card.of_dapm_routes+6,original+6,2*sizeof(*original)));
 free((void *)card.of_dapm_routes);
 /* A partial or already corrected DT must not be overwritten. */
 card=(struct snd_soc_card){.of_dapm_routes=original,.num_of_dapm_routes=3};
 assert(!sm8150_fix_nabu_speaker_routes(&card));
 assert(card.of_dapm_routes==original && !card.num_dapm_widgets);
 const struct snd_soc_dapm_route corrected[]={ {"BR Speaker",NULL,"BR SPK"} };
 card=(struct snd_soc_card){.of_dapm_routes=corrected,.num_of_dapm_routes=1};
 assert(!sm8150_fix_nabu_speaker_routes(&card));
 assert(card.of_dapm_routes==corrected && !card.num_dapm_widgets);
 puts("All four legacy routes repaired; immutable, unrelated, other-machine and allocation-failure cases passed.");
}
'''
with tempfile.TemporaryDirectory(prefix='nabu-speaker-routes-') as directory:
    src = Path(directory)/'test.c'
    binary = Path(directory)/'test'
    src.write_text(harness)
    subprocess.run(['cc','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                    str(src),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
