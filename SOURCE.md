# Source provenance

Kernel repository: https://gitlab.postmarketos.org/soc/qualcomm-sm8150/linux.git

Baseline commit: `5181e1358ddd6ea8028e841d928942373e6aebc8`.

`sound/soc/qcom/sm8150.c`, `common.h`, and the files in
`sound/soc/qcom/qdsp6/` are derived from that baseline. Original SPDX and
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

No q6asm PCM V4 protocol changes or QRTR changes are included.

Shell/Python tools and tests carry GPL-2.0-only SPDX identifiers. Kernel sources
retain their existing licenses; see LICENSES/preferred/GPL-2.0. Firmware,
third-party system UCM files, recordings and compiled modules are not included.
