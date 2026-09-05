# nabu-audio

Xiaomi Pad 5（nabu）在 Linux `6.14.11-nabu-audio1` 上的音频修复。
直接维护 `sound/soc/qcom/` 下的完整驱动源码，构建时直接编译这些文件。

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

启动和 WirePlumber 探测阶段仍出现 `Memory_map_regions failed`；其具体
触发参数尚未定位。实测后续录音、播放可用，不能宣称映射问题已经修复。
验证仅覆盖上述设备和内核，未验证其他 Qualcomm 设备的采样对齐行为。

旧 QRTR、PCM V4 和全功放格式实验不属于当前源码。旧脚本、实验文件及
详细过程记录已移入本机 `diagnostics/pre-submit-20260905/` 归档。
内核来源和许可证见 SOURCE.md、COPYING。
