# Source provenance

Kernel repository: https://gitlab.postmarketos.org/soc/qualcomm-sm8150/linux.git

Baseline commit: `5181e1358ddd6ea8028e841d928942373e6aebc8`.

`kernel-overlay/sound/soc/qcom/sm8150.c`, `common.h`, and the files in
`kernel-overlay/sound/soc/qcom/qdsp6/` are derived from that baseline. Original SPDX and
copyright headers are retained. Local headers are included so module builds
compile the checked-in driver sources without depending on an untracked source
snapshot. Kernel APIs and exported symbols still require a matching kernel build.

Local driver changes:

- `sm8150.c`: I²S format for the QUATERNARY_TDM_RX_0 codec DAI previously
  configured as DSP_A, verified to restore the BR speaker on nabu.
- `qdsp6/q6asm-dai.c`: convert high-aligned PCM V2 capture samples to signed
  Q23 for S24_LE before period notification. The conversion uses fixed PCM
  storage and filters stopped-stream callbacks under the PCM stream lock.
  Format behavior was measured on nabu firmware; it is not a claim about all
  Qualcomm firmware implementations.
- `qdsp6/q6asm-dai.c`: preserve the capture hardware limits rather than
  overwriting them with playback limits at the end of open; report mapping
  parameters on DSP errors and preserve the original return code. The runtime
  selection correction follows the upstream change "ASoC: qcom: q6asm: set
  runtime correctly for each stream" (Srinivas Kandagatla, 2025-10-23,
  Message-ID `20251023102444.88158-10-srinivas.kandagatla@oss.qualcomm.com`).
  These additions passed clean-boot S16/S24 capture checks on nabu.
- `qdsp6/q6asm-dai.c`: add a 4 KiB tail to Nabu's fixed PCM allocations,
  leaving PCM limits unchanged, to keep the DSP mapping's exclusive end below
  the next 32-bit address window. Based on local mapping failures at
  `0x1fff80000 + 512 KiB` and successful 512 KiB mapping at a lower address.
  The production allocation change passed clean-boot validation: seven PCM
  buffer cases, S16/S24 capture, and WirePlumber restart checks.
- `sm8150.c`: repair the legacy Nabu DT speaker-to-frontend feedback routes
  before card registration, terminating them at four physical speaker widgets.
  Read-only DAPM inspection confirmed all four amps remained powered with the
  frontend stream inactive. Clean boot on 2026-09-05 at 22:53 verified the
  loaded module and all four DAPM widgets transitioning Off/On/Off. Shutdown
  timeouts initially persisted; the additional frontend timing fix below
  resolves them in the tested scenarios. S16/S24 and buffer probes pass.

No q6asm PCM V4 protocol changes or QRTR changes are included.

`kernel-overlay/sound/soc/codecs/wcd934x.c`, `wcd-clsh-v2.h` and
`wcd-mbhc-v2.h` are copied from the same baseline. The only codec change is
to log normal SLIMbus PORT_CLOSED notifications at debug level. FIFO errors
and interrupt handling are unchanged. Local phase-separated S16/S24 tests
place the notification in snd_pcm_drop; the local Android downstream
`techpack/audio/asoc/codecs/wcd934x/wcd934x.c` also uses dev_dbg for closure.
The new module has been built but has not been deployed or boot-tested.

Shell/Python tools and tests carry GPL-2.0-only SPDX identifiers. Kernel sources
retain their existing licenses; see LICENSES/preferred/GPL-2.0. Firmware,
third-party system UCM files, recordings and compiled modules are not included.

- `sm8150.c`: ignore delayed frontend power-down on Nabu dynamic links.
  Local A/B/A testing with frontend pmdown_time 5000/0/5000 produced 6/0/7
  CS35L41 shutdown timeouts across seven buffer prepares per phase. The dummy
  frontend requests delayed DAPM stop; DPCM closes backend clocks before the
  final stream STOP. This change lets hw_free stop the frontend immediately.
  Clean boot at 23:11 verified the loaded module: boot, seven buffer probes
  and two WirePlumber restarts had zero shutdown timeouts or map failures.
  All four amplifier widgets passed Off/On/Off; S16/S24 capture passed.

- `q6asm-dai.c`: extend capture completion validation to S16 without converting
  its samples. Three prepare/close cycles reproduced 15 READ warnings in S16
  and none in S24. Shared stopped-stream and bounds checks pass regression
  tests. Clean boot at 23:24 verified zero READ warnings for three S16 and
  three S24 prepare/close cycles, boot and WirePlumber restart. S16/S24
  capture each completed four seconds without invalid samples.
- `scripts/fix-ucm-mic-channels.py`: surgical local UCM direction correction
  with a content-addressed backup; no third-party configuration is vendored.

- `q6asm-dai.c`: send PAUSE on capture STOP rather than playback EOS; keep
  playback STOP unchanged. Actual-trigger regression covers both directions,
  stopped state and error propagation. Clean boot at 23:28 verified S16/S24
  capture, three read/drop/prepare cycles per format on the same handle,
  three default PipeWire capture cycles and playback, buffer probes and
  WirePlumber restarts. No READ/EOS, amp shutdown or map errors occurred.
