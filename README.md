# nabu-audio

**English** | [中文](README.zh.md)

Audio fixes for the Xiaomi Pad 5 (nabu) on Linux `6.14.11-nabu-audio1`.
It maintains the complete driver source under `kernel-overlay/sound/soc/qcom/` and `codecs/`
directly, and these files are compiled as-is at build time.

## Layout

Uses the same direct source overlay layout as nabu-camera and nabu-iris:

```text
kernel-overlay/   complete audio driver source and local headers preserving Linux relative paths
config/           WirePlumber configuration used to identify the old S16 temporary limitation
scripts/          module build, install, and on-device verification tools
tests/            sample conversion and buffer lifecycle regression tests
LICENSES/         source license texts
```

## Putting it into the kernel tree

The target Linux Git worktree must be at baseline `5181e1358ddd6ea8028e841d928942373e6aebc8`.
This repository no longer ships an overlay script; the sibling `nabu-main` resets, applies
`kernel-overlay`, and composes by product:

```sh
cd ../nabu-main && make apply
```

You can also compile the overlay source inside the module directly (see "Build" below) without
copying it into the kernel tree first.

## Verified fixes

- `sm8150.c`: configures the amplifier DAI on QUATERNARY_TDM_RX_0, which previously used DSP_A, as
  I²S, fixing the silent BR (bottom-right) speaker. The user has confirmed it produces sound.
- `qdsp6/q6asm-dai.c`: converts the high-aligned 24-bit samples returned by PCM V2 into ALSA's
  S24_LE Q23 format, preserving all 24 valid bits and fixing recording playback spikes.
  The conversion happens in the period completion callback, covering mmap; it uses fixed DMA
  storage, filters late callbacks after stop within the stream lock, and checks the token, period
  length, and buffer bounds.

On-device verification on 2026-09-05: 4 seconds each of 16-bit and 24-bit stereo recording, data
complete, not all zero, no out-of-range samples; the default capture is MMAP_INTERLEAVED / S24_LE /
48 kHz / stereo.
Playback exits normally, and the user recorded voice and confirmed the spikes were gone. The
temporary S16 configuration has been disabled.

## Build

Requires a configured, fully built directory matching the target kernel (including Module.symvers),
plus `aarch64-linux-gnu-gcc`, binutils, make, and kmod. The current scripts only support
`6.14.11-nabu-audio1`. The default build directory is the local `out/audio1/build`; you can also set
`KERNEL_BUILD=/path/to/configured/build`. Kernel headers and symbols come from that build directory,
and the driver source and local headers come from this repository; external kernel source is not
modified.

```sh
bash scripts/build-br-i2s.sh
bash scripts/build-mic-align.sh
python3 tests/test-mic-conversion.py
python3 tests/test-mic-period.py
python3 tests/test-pcm-allocation.py
python3 tests/test-speaker-routes.py
```

The artifacts are in `out/br-i2s/` and `out/mic-align/` respectively, containing the module and
SHA256SUMS.
The tests extract the conversion function from this repository's source directly: they iterate all
16777216 signed 24-bit values and check post-stop callbacks, fixed DMA storage, period selection,
and exceptional bounds, with UBSan/ASan enabled.

## Install and rollback

The following are maintenance scripts for the current audio1 environment; they require the original
full bundle to already exist: `out/audio1/bundle/rootfs/lib/modules/6.14.11-nabu-audio1/`.
This bundle, the full kernel build directory, and the EFI are not committed with this repository.
The install scripts verify the module, version, hashes, and original backups, and only update the
audio1 module.

```sh
sudo bash scripts/install-br-i2s.sh
sudo bash scripts/install-mic-align.sh
```

The recording install script uses `restore-pcm-v2.sh` to confirm the original q6asm PCM V2 has been
restored, and only allows retracting the identified and backed-up old V4 experiment. Environments
using the original V2 do not need the experiment backup.
After a successful install, reboot the same audio1 kernel.

```sh
sudo bash scripts/install-mic-align.sh --rollback
sudo bash scripts/install-br-i2s.sh --rollback
```

A reboot is likewise required after rollback. The install scripts do not reboot the system or update
the EFI themselves.

## Verification

```sh
python3 scripts/verify-mic-pcm24.py
python3 scripts/test-speakers.py
```

The microphone verification first checks the build ID of the loaded module, then records S16_LE and
S24_LE.
Only after the complete, non-silent, range-checked result passes does it disable the old S16
configuration matching the repository contents and restart WirePlumber. User-edited configurations
are preserved. Speak normally while the recording check runs.

Default recording audition:

```sh
timeout -s INT 5s pw-record ~/mic-test.wav
pw-play ~/mic-test.wav
```

Diagnostic tools: `scripts/diagnose.sh`, `scripts/qrtr-services.py`,
`scripts/inspect-amp-format.py`. Local logs and recordings are kept in the git-ignored
`diagnostics/` and are not committed with the code.

## Known issues and scope

`Memory_map_regions failed` still appears during boot and WirePlumber probing.
As of 2026-09-05 this has been reproduced through ioctl tracing and standalone replay: MultiMedia1
playback, S24_LE, 48 kHz, 8 channels, 2048 frames/period, 8 periods (512 KiB) mapping fails; the same
format changed to 1024 frames/period (256 KiB) succeeds. Normal stereo small buffers also succeed.
The diagnostic record after reboot is DSP address `0x1fff80000` (the high bits contain SID 1),
allocation length 512 KiB. A 508 KiB request succeeds; increasing the request further, after the DSP
aligns to 4 KiB the mapping end lands exactly on the next 32-bit address window and fails
immediately. A standalone test mapping the same 512 KiB at a lower address succeeds, so it is not a
general 256 KiB capacity limit.

Current source corrects the recording side's misuse of playback hardware limits and makes
mapping-failure logs record the DSP address, actual allocation length, and request size, preserving
the original error code to ALSA. These changes have been verified after reboot: S16/S24 stereo
recording is complete, non-silent, and free of out-of-range samples.

The latest fix adds only one page (4 KiB) to the end of nabu's fixed PCM allocation, avoiding the
largest DSP mapping hitting the address boundary above while preserving the original 512 KiB
playback capacity. Build, allocation-boundary, and sample-conversion regression tests pass. After
the 2026-09-05 22:24 reboot, the loaded module was verified; there were no mapping failures during
boot and two WirePlumber restarts, and all seven boundary parameter sets, including the full
512 KiB, succeeded.
S16/S24 stereo recording is complete for 4 seconds each, non-silent, and free of out-of-range
samples. When playback is idle you can re-run the following script; it only prepares buffers and
does not start playback:

```sh
python3 scripts/probe-pcm-boundary.py
```

**Do not hot-unload the audio modules or rebind APR.** On this machine, the dependency removal from
a hot unload causes the APR service registration to be lost; rebinding APR then produces GLINK
duplicate devices and send failures. Even restoring the original module cannot recover the
communication state of that run; a reboot is required. After installation, follow the existing flow
to reboot the same audio1 kernel for verification.

The amplifier shutdown timeout disappeared in testing after the 2026-09-05 23:11 reboot. Earlier
inspection found that the old DT connected `BR/TR/BL/TL SPK` back to `MultiMedia1 Playback`, forming
a DAPM loop; with the device idle, the frontend stream was already inactive, yet all four Main AMPs
were still On, with both GLOBAL_EN and AMP_EN held asserted.
The current `sm8150.c` only corrects this set of old routes for nabu before sound card registration,
rewiring to the four physical Speaker endpoints while preserving other routes such as the microphone
and the BR I²S fix. No DTB/EFI replacement is needed.
After the 2026-09-05 22:53 reboot, the loaded module build ID was checked, and the DAPM states of
the four amplifiers were checked via idle=Off → playback=On → closed=Off. Shutdown timeouts still
occurred during boot and on prepare/close only; DAPM Off does not equal the chip having completed
power-down, and register and clock timing still need inspection.
S16/S24 recording and the seven PCM buffer-size regression checks pass.

Subsequent on-device A/B/A comparison: with the frontend `pmdown_time=5000`, the seven buffer probes
produced 6 timeouts; temporarily setting it to 0 produced 0, and restoring 5000 produced 7. The dummy
frontend codec delays close by default, making the amplifier shut down later than the backend clock
stops. The current source sets `ignore_pmdown_time=1` for nabu's dynamic frontend, letting hw_free
close DAPM promptly.
After the 2026-09-05 23:11 reboot, the new module build ID was checked: boot, the seven buffer
probes, and two WirePlumber restarts all showed no amplifier shutdown timeout or DSP mapping
failure. The four amplifiers passed the Off → On → Off check, and S16/S24 recording was complete,
non-zero, and free of out-of-range samples.
Default PipeWire recording obtained non-zero data and exited about 9 ms after the stop request, and
the playback command succeeded.
Check command:

```sh
sudo python3 scripts/verify-speaker-power.py
```

The script requires the playback device to be idle and checks that the four amplifiers are idle=Off,
On while playing three seconds of silence, and Off after closing. It does not unload the driver,
change the mixer, or stop desktop services. You should also check whether the new boot log still has
`Enable(0) failed` / `POST_PMD`. The routing fix and the frontend close-timing fix together passed
the above verification.
Verification only covers the above device and kernel; the sample-alignment behavior of other
Qualcomm devices is not verified.

The old QRTR, PCM V4, and all-amplifier-format experiments are not part of the current source. The
old scripts, experiment files, and detailed process records have been moved to this machine's
`diagnostics/pre-submit-20260905/` archive.
For the kernel provenance and license, see SOURCE.md and COPYING.

## Follow-up microphone fixes

`scripts/fix-ucm-mic-channels.py --install` only changes the system UCM Mic `PlaybackChannels 2` to
`CaptureChannels 2`, backs it up under `/var/lib/nabu-audio/ucm-mic/` by the original file's SHA256,
and preserves other configuration. On 2026-09-05 it was installed and verified that ALSA returns
CaptureChannels=2; after restarting WirePlumber the original Mic playback device warning
disappeared, and three default recordings all obtained non-zero data and stopped normally. No system
reboot is needed.

On-device comparison of three consecutive prepare/close cycles: S16 produced 15 READ response
warnings, S24 produced 0. The current source applies the original S24 running-state and
period-boundary checks to S16 as well, and only S24 performs the shift conversion, avoiding
processing a late callback and submitting another read when S16 closes.
After the 2026-09-05 23:24 reboot, the module was checked: three prepare/close cycles each for
S16/S24 all produced 0 READ warnings; boot and WirePlumber restart also did not reproduce it.
S16/S24 four-second recordings are complete, non-zero, and free of out-of-range samples.

Previously each recording STOP produced one EOS response warning. The current source instead sends
CMD_PAUSE for capture, after which prepare/close cleans up the session, while playback still uses
CMD_EOS.
`tests/test-pcm-stop.py` extracts the actual trigger function and verifies the direction, stop state,
and error returns; the test passes. After the 2026-09-05 23:28 reboot, the loaded module was checked,
and S16/S24 four-second recordings passed. Three read/drop/prepare cycles on the same recording
handle all completed, three default PipeWire recordings reopened and obtained non-zero data with a
stop time of about 8–16 ms, and default playback succeeded. The seven buffer probes passed, and the
service was normal after the WirePlumber restart.
In this boot and the above tests, READ/EOS warnings, amplifier shutdown timeouts, DSP mapping
errors, and UCM Mic playback device errors were all 0.

## WCD934x port close diagnostics

Follow-up checks on 2026-09-05 still found FIFO overflow/underflow on the WCD934x TX5/TX6, which is
not part of the READ/EOS or DSP mapping errors eliminated above. Six rounds of 6-second S16/S24
recordings exited normally, and the three observed FIFO errors were all at the end and carried the
PORT_CLOSED status bit.
This correlation cannot prove the root cause is resolved, nor can the absence of logs alone prove
recording is error-free: the driver rate-limits FIFO logs and masks the corresponding port interrupt
after a FIFO error.

A new diagnostic script separates prepare, read, drop, hw_free, and close, saving monotonic clock
timestamps, sample counts/ranges, and the kernel log for the run; audio data is only counted in
memory and recordings are not saved:

```sh
python3 scripts/probe-capture-lifecycle.py --cycles 3 > lifecycle.json
```

The script requires the capture device to be idle and permission to read the kernel log. In the first
round of the 100 ms buffer test, S16/S24 each obtained 384000 frames of non-zero data with no ALSA
read errors; PORT_CLOSED appeared about 4–8 ms after drop, and there were no new port notifications
during hw_free and close.

The subsequent six rounds with a 500 ms buffer also read the full eight seconds, with non-zero data
within the valid range for S16/S24. Two FIFO overflows appeared about 4–5 ms after drop, one with
status `1` (no PORT_CLOSED) and the other with status `5` (also carrying PORT_CLOSED). Therefore this
problem cannot be solved by filtering errors that "also carry the close bit". No new FIFO errors
were recorded during the recording read, hw_free, and close phases; the stream-stop timing still
needs further tracing. The raw local data is in `diagnostics/tx-port-20260905-234239/`, including
the initial diagnostic attempt that timed out because it was not explicitly started; the current
script explicitly calls snd_pcm_start, and subsequent runs succeeded.

`codecs/wcd934x.c` only demotes PORT_CLOSED notifications to debug logs, keeping the FIFO error
level, interrupt masking, and clear logic unchanged. Android downstream also logs ordinary close
notifications at debug level.
This change fixes the log level and does not claim to fix FIFO timing or improve recording quality.
The companion audio1 module has been built but not yet installed or reboot-verified:

```sh
bash scripts/build-codec-port-log.sh
sudo bash scripts/install-codec-port-log.sh
# Re-test after the next reboot of the same audio1 kernel; do not hot-unload the audio modules.
```

The installer verifies and backs up the original audio1 bundle and module hashes, and supports
`sudo bash scripts/install-codec-port-log.sh --rollback`.

## Fixes: intermittent missing sound card and TX FIFO overflow (2026-09-22)

Two audio problems found on the unified `6.14.11-nabu1` kernel are fixed and verified.

### Intermittent missing sound card (SLIM NGD)
Symptom: on some boots `/proc/asound/cards` is empty, with
`qcom,slim-ngd-ctrl ... QMI wait timeout` and
`platform sound: deferred probe pending: snd-sm8150: SLIM Capture 1: codec dai not found`.

Root cause: mainline `qcom_slim_ngd_up_worker()` waits only one second for the QMI service
(`wait_for_completion_interruptible_timeout(&ctrl->qmi_up, 1s)`) and returns without retrying. If the
QMI service arrives 1–2 s later, the SLIM controller is never registered and the WCD934x codec never
enumerates. Android's downstream `ngd_dom_up()` waits unbounded.

Fix: `kernel-overlay/drivers/slimbus/qcom-ngd-ctrl.c` now waits unbounded (matching Android), and
`nabu-module.toml` declares `slim-qcom-ngd-ctrl.ko`. Three consecutive reboots brought up the sound
card, codec enumeration, and capture every time.

### TX5/TX6 FIFO overflow
Root cause: `wcd934x_trigger()` only tore down the SLIM channel on STOP without first disabling the
codec-side TX port, so the decimator kept filling the port FIFO after the channel was removed,
raising `overflow error on TX port 6` about 1.3 ms after `drop`.

Fix: write `SLAVE_PORT_DISABLE` before the teardown, and use a `port_disabled` flag so the port is
re-enabled on START only after an actual teardown (avoiding a redundant first-start write that resets
the FIFO).

Verified with `scripts/probe-capture-lifecycle.py --cycles 3`: overflow 2 -> 0 across two runs, with
complete non-silent capture; only a rare setup-time underflow transient remains.
