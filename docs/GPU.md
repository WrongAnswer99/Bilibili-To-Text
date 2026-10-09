> 历史记录：以下为迁入独立项目之前的 SDK/GPU 测试。当前应用结构和协议流程见根目录 README.md。

# Whisper GPU 使用与测试记录

2026-10-09 已改为使用 `My-Local-OCR-ASR-Toolkit` 导出的原生 SDK。CPU/GPU 都通过 `dist/asr.py` 调用 `dist/asr.dll`，进程内推理；GPU DLL 和模型都在 `dist`。下面的 CUDA CLI 部分为迁移前的历史记录，当前不再使用应用目录的独立 Whisper 程序。

新 SDK 同一 19.203 秒音轨的一次测量：CPU 推理 2356 ms、含初始化调用 2618 ms；GPU 推理 1750 ms、含初始化调用 2185 ms，文字逐字一致。CPU 模式使用官方自动选择的动态 CPU 后端，比历史静态 CPU SDK 快，因此当前模式不能继续沿用历史 6.1 倍加速比。应用完整 GPU 流程总计 2.3 秒（音轨提取 101 ms、推理 1780 ms），仅输出 MP4/TXT。

## 迁移前记录

本项目默认使用 NVIDIA GPU。双击 `start.cmd`，识别设备默认选中 GPU；也可在下拉框选择 CPU。命令行默认相同：

```powershell
python transcribe_video.py "https://www.bilibili.com/video/BV1ewwxesEu4/"
python transcribe_video.py "https://www.bilibili.com/video/BV1ewwxesEu4/" --device cpu --overwrite
```

两份输出都存在时直接复用结果；`--overwrite` 会重新生成文字，并复用已经下载的视频。输出仍仅有 `output/BVxxx.mp4` 与 `output/BVxxx.txt`。临时音频和 CLI 中间文字位于 `.work`，完成后清理。

## 后端与准备

CPU 通过原有 `dist/asr.dll` 的 C ABI 调用 Whisper；GPU 通过 `whisper_gpu.py` 调用本项目下载的官方 `whisper-gpu/whisper-cli.exe`，无需重建旧 SDK、安装 CUDA Toolkit 或新 Python ASR 包。

GPU 程序为 [whisper.cpp b5454 官方 CUDA x64 发布包](https://github.com/ggml-org/whisper.cpp/releases/tag/b5454)，程序报告版本 1.9.5。1.9.5 语义版本标签未附二进制资源，因此固定到对应构建资源。官方 GPU 支持的实现说明见 [whisper.cpp NVIDIA GPU 支持](https://github.com/ggml-org/whisper.cpp/blob/master/README.md#nvidia-gpu-support)。

为 RTX 5060 配置 cuBLAS 12.9.1.4 和 CUDA runtime 12.9.79，组件来源为 [NVIDIA CUDA 12.9.1 官方再分发清单](https://developer.download.nvidia.com/compute/cuda/redist/redistrib_12.9.1.json)。安装程序下载官方归档，验证固定 SHA-256，再提取运行库和许可证。模型直接复用 `dist/models/whisper/ggml-small-q5_1.bin`。

```powershell
# 历史安装命令（该脚本已迁入 SDK 项目）
powershell -ExecutionPolicy Bypass -File tools/setup_whisper_gpu.ps1
```

本机已完成安装。重复执行会校验已安装文件并复用。运行库目录 `whisper-gpu`、下载缓存 `.source`、工作目录 `.work` 均由 Git 忽略。安装记录和每个运行库的 SHA-256 保存于 `whisper-gpu/runtime.json`。

| 归档 | 固定 SHA-256 |
|---|---|
| 官方 Windows CUDA b5454 | `afef0b881c500958921c3f5523b50e59ee2ec9b6f5cbd25b324c51ed308a957a` |
| cuBLAS 12.9.1.4 | `d534d98b0b453a98914dbf3adf47d7e84b55037abf02f87466439e1dcef581ed` |
| CUDA runtime 12.9.79 | `179e9c43b0735ffe67207b3da556eb5a0c50f3047961882b7657d3b822d34ef8` |

## GPU 运行证据

GPU 模式不仅检查 CUDA DLL 存在，还要求本次执行的 Whisper 日志明确出现 `using CUDA0 backend`；即使程序成功返回文字，只要没有 CUDA 激活证据，也会报错，不接受静默 CPU 回退。

实际日志同时显示：

```text
Device 0: NVIDIA GeForce RTX 5060 Laptop GPU, compute capability 12.0
whisper_model_load: CUDA0 total size = 189.53 MB
whisper_backend_init_gpu: using CUDA0 backend
```

测试期间 `nvidia-smi` 观测到 `F:\projects\BilibiliToText\whisper-gpu\whisper-cli.exe` 进程。采样中的整张显卡显存使用约 3157–3445 MiB、利用率约 39–59%；这些指标包含电脑其他 GPU 应用，不能全部归于 Whisper。

## 短视频实测（2026-10-09）

测试链接为 [BV1ewwxesEu4](https://www.bilibili.com/video/BV1ewwxesEu4/)，由 SnapAny 真实网页解析下载。视频文件 1,839,726 字节；完整提取音轨为 19.2029375 秒。

机器为 RTX 5060 Laptop GPU，8151 MiB 显存，驱动 592.01。CPU/GPU 使用相同 small Q5_1 模型、zh、8 线程、greedy、best-of 1、temperature 0、不增加 temperature、抑制非语音符号；两次各自创建引擎或新进程，不复用模型上下文。系统文件缓存和 CUDA 编译缓存已预热。

下面记录完整 ASR 调用墙钟耗时，包含初始化/模型加载；不包含网页解析、视频下载或 FFmpeg 提取。CPU 是既有 SDK 调用，GPU 是新增 CUDA CLI 调用，两者同时包含各自的启动开销。

| 模式 | 第一次 | 第二次 | 平均 |
|---|---:|---:|---:|
| CPU SDK | 12637.30 ms | 12810.78 ms | 12724.04 ms |
| GPU CUDA | 2099.40 ms | 2042.50 ms | 2070.95 ms |

该样本 GPU 平均约快 **6.14 倍**。最终以默认 GPU 工具完成同一缓存视频的完整处理，音频提取 96 ms、GPU 调用 2294 ms、总计约 2.4 秒，输出 MP4/TXT。首次 CUDA 初始化可能包含内核编译缓存建立，因此首次启动可比表中更慢。此次没有测量 59 分钟整段内容的 GPU 总耗时。

该短视频 CPU 与 GPU 的文字均为重复的“ 不 ”（无空格），输出逐字一致；这确认了两个模式的结果一致，没有把该视频当作带人工标注的准确率评测。另用此前 14 秒中文样本做有预期原文的校验：GPU 完整文字与预期一致（忽略标点），调用 1211.81 ms。也验证了中文与空格路径、临时文件清理及拒绝 CPU 回退。

原始结果保存在 `.work/gpu-test/summary.json`、`gpu-run-1.log`、`gpu-run-2.log` 和 `chinese-control.log`；这些本地测试产物不提交 Git。
