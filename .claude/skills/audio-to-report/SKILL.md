---
name: audio-to-report
description: 会议录音完整处理流程：转录→提炼→HTML报告。用户说"处理会议录音"、"会议纪要"、"录音转纪要"时触发。
user-invocable: true
allowed-tools: Bash Read Write
context: fork
agent: general-purpose
---

# audio-to-report

会议录音 → 文字稿 → 结构化纪要 → HTML 报告，一键完成。

## 流程

1. **转录** — 调用 `/funasr-asr` 转录音频文件
   - 输出: `archive/transcripts/{date}-{title}_transcript.md`
2. **生成报告** — 调用 `/meeting-summary` 处理 transcript
   - 输出: `archive/{date}-{title}/{date}-{title}.html` + `.md`
3. 终端输出报告路径和摘要

## 使用

```
/audio-to-report /path/to/meeting.wav
/audio-to-report （停止录制后自动衔接）
```

## 可附带参数

- 说话人映射：如「说话人0=wenshan，说话人1=亚龙」
- 引擎选择：funasr（中文优先）/ mlx（Apple Silicon 默认）
