#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare (without starting) 8-channel PCM buffers around the old DSP boundary.

Run on nabu with playback idle. Prints JSON per case; exits nonzero when any
configuration cannot be prepared. The unpatched kernel fails the last four.
"""
import argparse
import ctypes as C
import json

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--device', default='hw:X5,0')
options = parser.parse_args()
lib=C.CDLL('libasound.so.2')
p=C.c_void_p
specs={
 'snd_pcm_open':([C.POINTER(p),C.c_char_p,C.c_int,C.c_int],C.c_int),
 'snd_pcm_close':([p],C.c_int),
 'snd_pcm_hw_params_malloc':([C.POINTER(p)],C.c_int),
 'snd_pcm_hw_params_free':([p],None),
 'snd_pcm_hw_params_any':([p,p],C.c_int),
 'snd_pcm_hw_params_set_access':([p,p,C.c_int],C.c_int),
 'snd_pcm_hw_params_set_format':([p,p,C.c_int],C.c_int),
 'snd_pcm_hw_params_set_channels':([p,p,C.c_uint],C.c_int),
 'snd_pcm_hw_params_set_rate':([p,p,C.c_uint,C.c_int],C.c_int),
 'snd_pcm_hw_params_set_period_size':([p,p,C.c_ulong,C.c_int],C.c_int),
 'snd_pcm_hw_params_set_buffer_size':([p,p,C.c_ulong],C.c_int),
 'snd_pcm_hw_params':([p,p],C.c_int),
 'snd_pcm_prepare':([p],C.c_int),
}
for name,(args,result) in specs.items():
 f=getattr(lib,name); f.argtypes=args; f.restype=result
results=[]
for frames in [1024, 2016, 2032, 2033, 2040, 2047, 2048]:
 pcm=p(); params=p(); stage='open'; rc=lib.snd_pcm_open(C.byref(pcm),options.device.encode(),0,1)
 if rc<0: raise RuntimeError(rc)
 try:
  lib.snd_pcm_hw_params_malloc(C.byref(params))
  for name,args in [('any',()),('set_access',(3,)),('set_format',(6,)),('set_channels',(8,)),('set_rate',(48000,0)),('set_period_size',(frames,0)),('set_buffer_size',(frames*8,))]:
   stage=name; rc=getattr(lib,'snd_pcm_hw_params_'+name)(pcm,params,*args)
   if rc<0: break
  if rc>=0:
   stage='hw_params'; rc=lib.snd_pcm_hw_params(pcm,params)
  if rc>=0:
   stage='prepare'; rc=lib.snd_pcm_prepare(pcm)
  row=dict(period_frames=frames,bytes=frames*8*32,mapped_bytes=(frames*8*32+4095)//4096*4096,stage=stage,rc=rc)
  results.append(row); print(json.dumps(row),flush=True)
 finally:
  if params: lib.snd_pcm_hw_params_free(params)
  lib.snd_pcm_close(pcm)

raise SystemExit(1 if any(row["rc"] < 0 for row in results) else 0)
