---
name: funasr-asr
description: 本地语音识别（FunASR paraformer-zh / mlx-whisper），输出带时间戳的 transcript.md。支持录制控制。用户说"转录"、"语音识别"、"开始录制"、"停止录制"时触发。
user-invocable: true
allowed-tools: Bash Read
---

# funasr-asr

调用本地 FunASR 模型（paraformer-zh 套件）或 mlx-whisper 进行语音识别，输出带时间戳和说话人分离的 transcript.md。

## 依赖

```bash
pip install funasr>=1.0.14 modelscope>=1.9.0  # FunASR
pip install mlx mlx-whisper                     # MLX Whisper (Apple Silicon)
```

## 模型路径

```
~/.cache/modelscope/hub/models/iic/
├── speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch
├── speech_fsmn_vad_zh-cn-16k-common-pytorch
├── punc_ct-transformer_cn-en-common-vocab471067-large
└── speech_campplus_sv_zh-cn_16k-common
```

## 录制控制

```bash
# 开始会议录制（BlackHole Aggregate Device）
~/myenv/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/meeting_rec.py start-meeting

# 开始通话录音（内置麦克风）
~/myenv/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/meeting_rec.py start-phone

# 查询状态
~/myenv/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/meeting_rec.py status

# 停止录制
~/myenv/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/meeting_rec.py stop
```

## 转录

```bash
# 单文件转录
~/myenv/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/transcribe.py <音频文件> --engine funasr|mlx|whisper

# 文件夹批量
~/myenv/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/transcribe.py <文件夹> --engine mlx

# 停止录制 + 自动转录（一键）
~/myenv/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/stop_and_transcribe.py [--engine funasr]
```

支持格式：wav / mp3 / m4a / flac / aac / ogg

## 停止录制 → 完整流水线

收到"停止录制"时，自动执行：
1. `stop_and_transcribe.py` — 停止录制 + 转录
2. 从输出解析 `TRANSCRIPT_PATH:/path/to/file`
3. 调用 `/meeting-summary` 处理 transcript → HTML 报告

或使用 `/audio-to-report` pipeline 一键完成。

## 输出格式 transcript.md

```
# 转录结果

**文件**：audio.mp3
**时长**：MM:SS
**说话人数**：N
**句子数**：N

## 转录

[00:01.5 - 00:03.2] 说话人0: 今天天气怎么样
[00:03.5 - 00:06.8] 说话人1: 天气很好，适合出门

## 纯文本

今天天气怎么样天气很好，适合出门
```
