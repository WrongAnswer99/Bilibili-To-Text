# BilibiliToText

油猴负责下载 B 站视频，本地应用负责把本地视频转成文字和字幕，两者可以独立使用，也可通过 bilibilitotext:// 联动。Whisper、语音检测模型、CPU/GPU 运行库与繁简转换都在本项目内，不依赖另一个项目的 SDK。

## 首次使用

1. 准备 Windows x64、64 位 Python 和本项目的模型、运行库及 FFmpeg。当前电脑已经配置完成，可直接运行；从源码新建环境的步骤见下方“项目结构与依赖”。GPU 识别需要兼容的 NVIDIA 驱动，也可以在窗口选择 CPU。
2. 本地视频转换只需双击根目录 **start.cmd**。
3. 需要从浏览器下载并自动转换时，先双击根目录 **register_protocol.cmd** 注册协议，再按下方教程安装油猴脚本。移动项目文件夹或更换 Python 后，双击 **register_protocol_force.cmd** 更新协议路径。
4. 浏览器默认下载目录、油猴面板中的目录、注册协议时设置的目录必须一致。目前本机使用 **C:\Users\admin\Downloads**。

## 本地软件使用教程

双击 **start.cmd**，或右键 **start.ps1 → 使用 PowerShell 运行**。

1. 填写视频路径，或点击 **打开文件...** 选择视频。
2. 选择识别设备、识别语言与 CPU 线程数。语言下拉提供英语、简体中文、日语、俄语，并保留繁体中文及自动检测。默认 GPU、简体中文、zh、8 线程。
3. 点击 **开始转换**，下方显示处理阶段与进度，百分比日志更新同一行。
4. 点击 **完成** 左侧的 **打开输出文件夹**，在视频原文件夹打开同名 **.txt** 或 **.srt**。未选择有效视频时该按钮禁用。普通模式可再次选择其他视频继续转换，最后点击窗口右下角 **完成** 关闭窗口。

TXT 和 SRT **与视频同目录、同名**，原视频不移动、不改名：

~~~text
D:\Videos\
  会议.mp4
  会议.txt
  会议.srt
~~~

支持 MP4、MKV、MOV、WEBM、AVI、M4V、FLV、TS，视频需要有音轨。TXT/SRT 使用 UTF-8。**TXT 每个非空识别片段一行，不带时间戳**；SRT 保留 Whisper 分段时间轴，可作为视频字幕使用。分行以识别片段为准。临时 WAV 放在项目 .work，正常结束会清理。

已有 TXT/SRT 默认复用，并根据字幕分段自动把旧 TXT 更新为一段一行，无需重新识别；可以直接切换简繁体。需要用新的设备、语言等参数重新识别时，勾选 **重新识别**；该选项只覆盖文字和字幕。转换期间可取消；“完成”按钮暂时禁用，关闭窗口会停止当前任务。

识别语言应与视频中实际说话的语言一致。例如英语视频选 **英语**，日语视频选 **日语**；不确定时选 **自动检测**。简体/繁体选项识别中文并转换字形，其他语言保留原文，这些选项不提供翻译。

本地窗口不接受视频网址，不再访问下载网站。

## 油猴安装与使用教程

本机已注册协议，下载目录为 **C:\Users\admin\Downloads**。

1. 在 Edge 或 Chrome 中安装并启用 **Tampermonkey（油猴）** 扩展。
2. 点击油猴图标 → **添加新脚本**，删除编辑器中的默认内容，把根目录 [bilibili-download.user.js](bilibili-download.user.js) 的全部内容复制进去并保存。已安装旧脚本时，在管理面板打开原脚本全文替换，避免同时启用两个版本。
3. 油猴管理面板 → 设置 → **配置模式：高级** → 下载模式 **浏览器 API**，按提示允许下载权限。扩展名白名单允许 mp4；分离轨道还需要 m4s。
4. 核对浏览器默认下载目录，并关闭“下载前询问每个文件的保存位置”。油猴面板目录、浏览器默认目录、config.json 的 download_directory 保持一致。面板中的目录只用于推算位置，不会修改浏览器设置。
5. 在浏览器登录 B 站，打开 **www.bilibili.com/video/BV…/** 视频页面；安装或更新脚本后刷新页面，确认面板显示 **v0.3.1**。
6. 在 B 站页面切换到要下载的分 P，在脚本面板选择识别语言、CPU/GPU。只要下载视频就点击 **下载视频**；需要自动生成文字和字幕就点击 **下载并提取文字**。
7. 联动时，下载完成后允许浏览器打开 **bilibilitotext** 本地应用，窗口会自动开始转换。处理进度和最终结果以本地窗口为准。

面板有三个主要按钮：

| 按钮 | 行为 |
| --- | --- |
| 下载视频 | 仅下载，不调用本地应用；可独立使用 |
| 下载并提取文字 | 下载完成后打开本地窗口，自动转换；当前分 P 已完整下载时直接复用，避免重试重复下载 |
| 打开文件所在位置 | 通过本地协议在资源管理器中选中下载文件；不转换 |

浏览器传入的任务会先解析成**真实本地视频路径**。窗口自动填写路径并锁定，“打开文件...”变为 **打开文件所在位置**，仍可调整转换参数、查看状态及点击“完成”。**完成按钮左侧有“转换其他视频”**：转换结束后点击，当前窗口切换到普通模式，清空并解锁路径，“打开文件所在位置”恢复为“打开文件...”；选取另一个视频后点击“开始转换”。切回普通模式后，同一位置显示 **打开输出文件夹**，选择有效视频即可打开其所在目录。该切换保留识别参数，转换期间“转换其他视频”按钮禁用。TXT/SRT 写在该视频原文件夹，不再使用项目 output 目录。

下载名带 BV、分 P 和时间戳，转换保留该文件名。例如：

~~~text
C:\Users\admin\Downloads\
  BV1ewwxesEu4_20261009083024124.mp4
  BV1ewwxesEu4_20261009083024124.txt
  BV1ewwxesEu4_20261009083024124.srt
~~~

优先下载带声音 MP4。若接口仅返回 DASH 轨道或 MP4 分段，“下载视频”会保存这些分离文件；“下载并提取文字”由本地 FFmpeg 在下载目录合并成 MP4，再转写。合并失败保留原件；成功提交 MP4 后才清理本次轨道/分段。

油猴不能直接打开 Windows 文件夹，因此“打开文件所在位置”和联动转换需要注册本地协议。仅下载不需要本地应用。浏览器不会确认本地转换结果，转换状态以本地窗口为准。

## 注册协议

当前用户注册，无需管理员权限。其他电脑首次使用双击 **register_protocol.cmd**，更换下载目录时执行：

~~~powershell
powershell -ExecutionPolicy Bypass -File register_protocol.ps1 -DownloadDirectory "D:\Downloads"
powershell -ExecutionPolicy Bypass -File register_protocol.ps1 -Check
powershell -ExecutionPolicy Bypass -File register_protocol.ps1 -Unregister
# 移动项目或更换 Python 后，在新的项目目录更新协议路径：
powershell -ExecutionPolicy Bypass -File register_protocol.ps1 -Force
# 专用的强制注册入口，也可带 -DownloadDirectory 或 -Check：
powershell -ExecutionPolicy Bypass -File register_protocol_force.ps1
~~~

普通注册会拒绝覆盖其他路径；确认要迁移时，双击根目录 [register_protocol_force.cmd](register_protocol_force.cmd)，或运行 [register_protocol_force.ps1](register_protocol_force.ps1)。PS1 入口默认强制注册，支持 **-DownloadDirectory** 和只读检查 **-Check**；上面的普通脚本 **-Force** 命令也可使用。重新注册默认保留 config.json 中的下载目录；需要更改时指定 **-DownloadDirectory**。**-Unregister** 可在新目录清除旧注册。

协议只传 BV、分 P、下载文件名与转换参数，不传 Cookie。本地仅从配置的下载目录解析浏览器任务，拒绝未知操作、路径穿越、混合任务和不完整转换任务。重复转换同一个本地文件会被任务锁拒绝。

油猴不保证返回完整真实路径，“预期位置”按配置推算。另存或改名后以浏览器记录为准；也可在本地窗口手动选择视频。

## 命令行

~~~powershell
python transcribe_video.py "D:\Videos\会议.mp4"
python transcribe_video.py "D:\Videos\会议.mp4" --device cpu
python transcribe_video.py "D:\Videos\会议.mp4" --chinese-script traditional
python transcribe_video.py "D:\Videos\会议.mp4" --lang zh --threads 8 --overwrite
python transcribe_video.py "D:\Videos\English.mp4" --lang en
python transcribe_video.py "D:\Videos\日本語.mp4" --lang ja
python transcribe_video.py "D:\Videos\video.mp4" --lang auto
~~~

支持 --lang zh/en/auto 等 Whisper 语言代码、--threads、--runtime-dir。所有结果固定保存到视频原文件夹。--overwrite 重新生成文字与字幕，不修改视频。

## 项目结构与依赖

- bilibili-download.user.js：浏览器下载与本地协议请求。
- launch_local.py / register_protocol.py：协议桥接与注册。
- import_job.py：浏览器文件名校验、原目录合并、文件位置解析、任务锁。
- start.ps1 / transcribe_video.py：本地窗口、FFmpeg 提取与转写流程。
- chinese_text.py / .vendor/：OpenCC 简繁转换。
- whisper_engine.py / native/：项目内 Whisper 调用与后处理。
- third_party/whisper.cpp/：固定版本 1.9.5 源码。
- runtime/：本项目编译的 whisper_bridge.dll 与 Whisper/ggml/CUDA DLL。
- models/whisper/：small Q5_1 多语言模型、Silero VAD 模型与许可证。
- ffmpeg.exe：本应用的 FFmpeg。
- .work/：临时文件、诊断、测试结果；gui-last-run.json 保存最近窗口结果。

旧 dist 与网站下载代码只保存在 .work 的历史归档中，当前程序不使用。

需要 Windows x64 和 64 位 Python；GPU 需要兼容的 NVIDIA 驱动。准备依赖或重新编译：

~~~powershell
python -m pip install --target .vendor OpenCC==1.4.2
powershell -ExecutionPolicy Bypass -File tools/setup_whisper.ps1
powershell -ExecutionPolicy Bypass -File tools/setup_whisper_gpu.ps1
powershell -ExecutionPolicy Bypass -File tools/build_whisper.ps1
# 可选纯 CPU 构建，替换当前 whisper_bridge.dll：
powershell -ExecutionPolicy Bypass -File tools/build_whisper.ps1 -Backend cpu
~~~

FFmpeg 放根目录。运行不需要编译器，重编译需要 CMake 和 MinGW-w64。运行库、模型、大文件和本机配置由 Git 忽略；第三方许可证应随依赖保留。

## 常见问题

- **下载设置找不到**：先把油猴配置模式切到“高级”。
- **找不到脚本面板**：确认扩展和脚本已启用，页面是 B 站视频页，刷新页面。
- **浏览器没有打开本地窗口**：运行 register_protocol.cmd；允许浏览器打开本地应用，再点“下载并提取文字”重试，已完整下载的当前分 P 会复用。
- **提示本地文件不存在**：核对三个下载目录，确认没有另存或改名。也可以用普通模式手动选择视频。
- **GPU 初始化失败**：检查 NVIDIA 驱动，或选择 CPU。GPU 模式不会静默回退到 CPU。
- **换了语言还是旧结果**：勾选“重新识别”再转换；不勾选时复用已有结果，只更新 TXT 排版或中文简繁体。
- **TXT 仍然挤在一行**：用新版程序对该视频再点一次“开始转换”，现有 SRT 会用于分行，不需要勾选“重新识别”。
- **接收模式不能改视频路径**：转换结束后点击“转换其他视频”，即可进入普通模式。

## 验证

2026-10-09，v0.3.1：

- 20 个 Python 测试、16 个油猴模拟场景及 6 个语言选项检查通过，包括下载独立性、联动、打开位置、协议重试、完整失败诊断。
- 同一约 20 秒视频真实 CPU/GPU 转写通过，GPU 确认 CUDA；源视频哈希不变，TXT/SRT 保存在源目录。
- 普通本地窗口真实完成 CPU 转换，路径可编辑、文件选择按钮正常、完成按钮可用。
- Windows 实际调用已注册协议，自动打开窗口并用 GPU 转换；真实路径只读、按钮变为打开所在位置、结果保存在下载目录。
- 真实 FFmpeg 合并 DASH 和 MP4 分段通过，合并文件保存在原目录，合并后仍可解析文件位置。
- 普通及传入模式的窗口渲染检查通过。
- TXT 新识别结果分行、旧结果无需识别即可分行；接收模式完成后切到普通模式并转换其他视频已验证。

历史流程测试报告：.work/verify-v03/results.json；本次 TXT 排版与模式切换验证：.work/verify-layout/results.json。20 秒视频用于验证流程，不作为人工转写准确率评测。

~~~powershell
python -m unittest discover -s tests -v
node tests/test_userscript.cjs
powershell -ExecutionPolicy Bypass -STA -File start.ps1 -Check
~~~

[油猴说明](docs/USERSCRIPT.md)。[历史 GPU/SDK 记录](docs/GPU.md)保留迁入独立项目前的测试经历。

[长音频重复字幕的排查与修复](docs/WHISPER-REPETITION.md)。SDK 和本项目均已修复，两个问题视频的原目录 TXT/SRT 已重新生成；语音语言选项用于识别原语言，不提供翻译。
