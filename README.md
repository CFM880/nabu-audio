# nabu-audio

Xiaomi Pad 5（nabu）在 Linux `6.14.11-nabu-audio1` 上的音频修复。
直接维护 `kernel-overlay/sound/soc/qcom/` 下的完整驱动源码，构建时直接编译这些文件。

## 目录

与 nabu-camera、nabu-iris 使用相同的直接源码覆盖层布局：

```text
kernel-overlay/   保留 Linux 相对路径的完整音频驱动源码及本地头文件
config/           用于识别旧 S16 临时限制的 WirePlumber 配置
scripts/          源码覆盖、模块构建、安装和实机验证工具
tests/            采样转换与缓冲区生命周期回归测试
LICENSES/         源码许可证文本
```

## 放入内核树

目标 Linux Git 工作树必须位于基线
`5181e1358ddd6ea8028e841d928942373e6aebc8`：

```sh
./scripts/apply-overlay.sh ../linux
```

脚本复制完整源码，可重复运行，允许相机、Iris 等不重叠改动；遇到目标路径的
未知修改会停止。复制后可用 `git -C ../linux diff` 审查。
也可使用下面的模块构建流程，直接编译本仓库覆盖层，无需先复制到内核树。

## 已验证的修复

- `sm8150.c`：将 QUATERNARY_TDM_RX_0 上原先使用 DSP_A 的功放 DAI
  配置为 I²S，修复 BR（右下角）扬声器无声。用户已确认出声。
- `qdsp6/q6asm-dai.c`：将 PCM V2 返回的高位对齐 24 位采样转为 ALSA
  S24_LE 的 Q23 格式，保留全部 24 位有效数据，修复录音回放尖刺。
  在 period 完成回调中转换，覆盖 mmap；使用固定 DMA 存储，在流锁内
  过滤停止后的迟到回调，并检查 token、period 长度和缓冲区边界。

2026-09-05 实机验证：16 位及 24 位双声道录音各 4 秒，数据完整、非全零、
无越界样本；默认采集为 MMAP_INTERLEAVED / S24_LE / 48 kHz / 双声道。
播放正常退出，用户录制人声并回放确认尖刺消失。临时 S16 配置已停用。

## 构建

需要与目标内核一致的已配置、完整构建目录（包含 Module.symvers），以及
`aarch64-linux-gnu-gcc`、binutils、make、kmod。当前脚本只支持
`6.14.11-nabu-audio1`。默认构建目录为本地 `out/audio1/build`，也可设置
`KERNEL_BUILD=/path/to/configured/build`。内核头文件和符号来自该构建目录，
驱动源码及本地头文件均来自本仓库；不会修改外部内核源码。

```sh
bash scripts/build-br-i2s.sh
bash scripts/build-mic-align.sh
python3 tests/test-mic-conversion.py
python3 tests/test-mic-period.py
python3 tests/test-pcm-allocation.py
python3 tests/test-speaker-routes.py
```

产物分别位于 `out/br-i2s/` 和 `out/mic-align/`，包含模块及 SHA256SUMS。
测试直接提取本仓库源码的转换函数：遍历全部 16777216 个有符号 24 位值，
并检查停止后回调、固定 DMA 存储、period 选择和异常边界，启用 UBSan/ASan。

## 安装与回退

以下是当前 audio1 环境的维护脚本，要求已有原始完整 bundle：
`out/audio1/bundle/rootfs/lib/modules/6.14.11-nabu-audio1/`。
此 bundle、完整内核构建目录和 EFI 不随本仓库提交。
安装脚本核对模块、版本、哈希及原始备份，只更新 audio1 模块。

```sh
sudo bash scripts/install-br-i2s.sh
sudo bash scripts/install-mic-align.sh
```

录音安装脚本通过 `restore-pcm-v2.sh` 确认原始 q6asm PCM V2 已恢复，
仅允许撤回已识别并备份的旧 V4 实验。使用原始 V2 的环境不需要实验备份。
安装成功后重启同一个 audio1 内核。

```sh
sudo bash scripts/install-mic-align.sh --rollback
sudo bash scripts/install-br-i2s.sh --rollback
```

回退后同样需要重启。安装脚本不会自行重启系统或更新 EFI。

## 验证

```sh
python3 scripts/verify-mic-pcm24.py
python3 scripts/test-speakers.py
```

麦克风验证先核对已加载模块 build ID，然后录制 S16_LE 和 S24_LE。
仅在完整、非静音、范围检查通过后，停用与仓库内容一致的旧 S16 配置，
重启 WirePlumber。用户编辑过的配置会保留。运行录音检查时正常说话。

默认录音试听：

```sh
timeout -s INT 5s pw-record ~/mic-test.wav
pw-play ~/mic-test.wav
```

诊断工具：`scripts/diagnose.sh`、`scripts/qrtr-services.py`、
`scripts/inspect-amp-format.py`。本机日志及录音保存在被 Git 忽略的
`diagnostics/` 中，不随代码提交。

## 已知问题与范围

启动和 WirePlumber 探测阶段仍出现 `Memory_map_regions failed`。
2026-09-05 已通过 ioctl 跟踪与独立重放复现：MultiMedia1 播放，S24_LE、
48 kHz、8 声道、2048 帧/period、8 periods（512 KiB）映射失败；同样格式
改为 1024 帧/period（256 KiB）成功。正常双声道小缓冲区也成功。
重启后的诊断记录为 DSP 地址 `0x1fff80000`（高位包含 SID 1），分配长度
512 KiB。508 KiB 请求成功；再增大请求，DSP 按 4 KiB 对齐后映射末端恰好
到下一个 32 位地址窗口，立即失败。独立测试在较低地址映射同样的 512 KiB
成功，因此不是通用的 256 KiB 容量限制。

当前源码纠正了录音端误用播放硬件限制的问题，并让映射失败日志记录 DSP
地址、实际分配长度和请求大小，向 ALSA 保留原始错误码。这些改动已经重启
验证，S16/S24 双声道录音完整、非静音且无越界采样。

最新修复只在 nabu 的固定 PCM 分配末尾增加一页（4 KiB），避免最大 DSP
映射碰到上述地址边界，保留原有 512 KiB 播放容量。构建、分配边界和采样
转换回归测试通过。2026-09-05 22:24 重启后已验证加载模块，启动及两次
WirePlumber 重启无映射失败；包括完整 512 KiB 在内的七组边界参数全部成功。
S16/S24 双声道录音各 4 秒完整、非静音且无越界采样。播放空闲时可运行以下
脚本复测；它只准备缓冲区，不启动播放：

```sh
python3 scripts/probe-pcm-boundary.py
```

**不要热卸载音频模块或重新绑定 APR。** 本机热卸载的依赖移除会导致 APR
服务注册丢失；重新绑定 APR 又会出现 GLINK 重复设备和发送失败。即使恢复原
模块也无法恢复该次运行的通信状态，需要重启。安装后按既有流程重启同一
audio1 内核验证。

功放关闭超时已在 2026-09-05 23:11 重启后的测试中消失。此前检查发现旧 DT 将 `BR/TR/BL/TL SPK`
反接回 `MultiMedia1 Playback`，形成 DAPM 环路；实机空闲时前端 stream
已 inactive，四个 Main AMP 却仍为 On，GLOBAL_EN 和 AMP_EN 均保持置位。
当前 `sm8150.c` 在声卡注册前只修正 nabu 的这组旧路由，改接四个物理
Speaker 端点，保留麦克风等其他路由及 BR 的 I²S 修复。无需替换 DTB/EFI。
2026-09-05 22:53 重启后，已核对加载模块 build ID，四个功放的 DAPM 状态
通过 idle=Off → 播放=On → 关闭=Off 检查。启动及仅 prepare/close 时
仍出现关闭超时；DAPM Off 不等于芯片已完成掉电，仍需检查寄存器和时钟时序。
S16/S24 录音及七种 PCM 缓冲区大小回归检查通过。

随后实机 A/B/A 对照：前端 `pmdown_time=5000` 时七种缓冲区探测产生
6 次超时，临时改为 0 后为 0 次，恢复 5000 后为 7 次。dummy 前端 codec
默认延迟关闭，使功放关闭晚于后端时钟停止。当前源码对 nabu 的 dynamic
前端设置 `ignore_pmdown_time=1`，让 hw_free 及时关闭 DAPM。
2026-09-05 23:11 重启后已核对新模块 build ID：启动、七种缓冲区探测、
两次 WirePlumber 重启均未出现功放关闭超时或 DSP 映射失败。四个功放
通过 Off → On → Off 检查，S16/S24 录音完整、非全零且无越界采样。
默认 PipeWire 录音取得非零数据并在停止请求后约 9 ms 退出，回放命令成功。
检查命令：

```sh
sudo python3 scripts/verify-speaker-power.py
```

脚本要求播放设备空闲，检查四个功放 idle=Off、播放三秒静音时=On、关闭后=Off。
不卸载驱动、不改 mixer、不停止桌面服务。应同时检查新启动日志是否仍有
`Enable(0) failed` / `POST_PMD`。路由修正与前端关闭时序修正共同通过了上述验证。
验证仅覆盖上述设备和内核，未验证其他 Qualcomm 设备的采样对齐行为。

旧 QRTR、PCM V4 和全功放格式实验不属于当前源码。旧脚本、实验文件及
详细过程记录已移入本机 `diagnostics/pre-submit-20260905/` 归档。
内核来源和许可证见 SOURCE.md、COPYING。

## 后续麦克风修复

`scripts/fix-ucm-mic-channels.py --install` 只将系统 UCM 的 Mic
`PlaybackChannels 2` 改为 `CaptureChannels 2`，按原文件 SHA256 备份到
`/var/lib/nabu-audio/ucm-mic/`，保留其他配置。2026-09-05 已安装并验证
ALSA 返回 CaptureChannels=2，重启 WirePlumber 后原 Mic 播放设备警告
消失，三次默认录音均取得非零数据并正常停止。无需重启系统。

连续三次 prepare/close 的实机对照：S16 产生 15 条 READ 响应警告，
S24 为 0。当前源码将原 S24 的运行状态及周期边界检查用于 S16，
仅 S24 执行位移转换，避免 S16 关闭时处理迟到回调并再次提交读取。
2026-09-05 23:24 重启后已核对模块，S16/S24 各三次 prepare/close
均为 0 条 READ 警告；启动和 WirePlumber 重启亦未复现。S16/S24
各四秒录音完整、非全零且无越界采样。

此前录音 STOP 各产生一条 EOS 响应警告。当前源码改为对 capture 发送
CMD_PAUSE，随后由 prepare/close 清理会话，播放仍使用 CMD_EOS。
`tests/test-pcm-stop.py` 提取实际 trigger 函数，验证方向、停止状态及
错误返回；测试通过。2026-09-05 23:28 重启后已核对加载模块，
S16/S24 各四秒录音通过。同一录音句柄各三次 read/drop/prepare 循环
全部完成，三次默认 PipeWire 录音重开取得非零数据，停止耗时约 8–16 ms，
默认回放成功。七种缓冲区探测通过，WirePlumber 重启后服务正常。
本次启动及上述测试中 READ/EOS 警告、功放关闭超时、DSP 映射错误和
UCM Mic 播放设备错误均为 0。
