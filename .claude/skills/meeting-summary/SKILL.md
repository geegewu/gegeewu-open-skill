---
name: meeting-summary
description: 将会议文字稿（带时间戳 Markdown）提炼为思维导图、会议纪要、待办事项，生成 HTML 报告。用户说"会议纪要"、"生成报告"、"meeting summary"时触发。
user-invocable: true
allowed-tools: Bash Read Write
---

# meeting-summary

输入带时间戳的会议 Markdown 文字稿，输出包含思维导图、会议纪要、待办事项的 HTML 报告。

## Environment
- `PYTHON`: `$HOME/myenv/bin/python3`
- `npx markmap-cli` — 思维导图渲染

## 触发方式

```
/meeting-summary /path/to/transcript.md
/meeting-summary （直接粘贴文字稿内容）
```

## 输入格式

兼容 `/funasr-asr` 生成的 `transcript.md`，或任意带时间戳的 Markdown 文字稿。

## Workflow

### Step 0：转录（若输入为音视频文件）

```bash
FUNASR_SCRIPT="<funasr-asr skill>/scripts/transcribe.py"
~/myenv/bin/python3 "$FUNASR_SCRIPT" "${INPUT_FILE}" --engine funasr
```

如果输入已经是 transcript.md，跳过此步。

### Step 1：读取文字稿

读取 transcript.md 内容。

### Step 2：LLM 提炼

读取 reference/step2-prompts.md 获取 JSON schema + 提炼规则，输出 JSON。

### Step 3：生成 HTML 报告

```bash
MEETING_DIR="archive/${DATE}-${SAFE_TITLE}"
mkdir -p "$MEETING_DIR"

# 保存 JSON
printf "%s\n" "$LLM_JSON_OUTPUT" > "$MEETING_DIR/summary.json"

# 生成 HTML + MD 报告（自动同步 Obsidian + Apple Reminders）
~/myenv/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/generate_report.py \
  --json "$MEETING_DIR/summary.json" \
  --output "$MEETING_DIR/${DATE}-${SAFE_TITLE}.html"
```

### Step 4：输出

报告保存到 archive/ 目录，终端输出文件路径。

## Guardrails
- 输出路径必须用 archive/，禁止 /tmp
- 不暴露 API key 或 token
- 不捏造未在文字稿中出现的内容
