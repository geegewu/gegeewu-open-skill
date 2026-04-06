---
name: podcast-pipeline
description: 播客完整处理流程。RSS下载→转录→提炼核心文本→卡片渲染→社交文案。用户说"处理播客"、"播客流程"、"podcast pipeline"时触发。
user-invocable: true
allowed-tools: Bash Read Write
context: fork
agent: general-purpose
---

# podcast-pipeline

AI 播客自动化：RSS/YouTube → 转录 → 提炼核心文本 → 卡片渲染 → 社交文案。

全部手动触发，无 cron。

## Environment
- `PYTHON`: `~/myenv/bin/python3`（含 PIL 等依赖）
- `ffmpeg`: 音频格式转换

## 播客订阅清单
见 `reference/PODCAST_FEEDS.md`（12 个 feed，含 2 个 YouTube 频道）。

## 完整 Pipeline（5 步）

### Step 1：RSS 抓取 + 下载音频

```bash
cd ${CLAUDE_SKILL_DIR}
~/myenv/bin/python3 scripts/rss_downloader.py --limit 1
```

- 每 feed 最多下 1 集，guid 去重，AI/科技关键词过滤
- YouTube 频道：下载自动字幕 → transcript → 跳过 Step 2
- 下载完成后自动 detach 启动 transcribe_queue.py

### Step 2：音频转录

```bash
~/myenv/bin/python3 scripts/transcribe_queue.py
```

- 引擎：调用 `/funasr-asr` 的 transcribe.py（mlx-whisper）
- 串行执行，完成后自动删除音频
- transcript 存入 `transcripts/YYYY-MM-DD/<podcast-slug>.md`

### Step 3：转录 → 核心文本

**3a. 脚本切分：**
```bash
~/myenv/bin/python3 scripts/step3_pipeline.py prepare \
  --transcript transcripts/YYYY-MM-DD/<slug>.md \
  --output-dir output/<podcast>/
```

**3b. 并发处理 batch（Round 1）：**
- 读取 `reference/step3-prompts.md` 获取 prompt
- 并发生成各 batch 400-500 字摘要（最多 5 路）

**3c. 汇总生成叙事文本（Round 2）：**
- 读取 `reference/writing-guide.md`
- 生成 2800-3500 字叙事文本

**3d. 脚本校验：**
```bash
~/myenv/bin/python3 scripts/step3_pipeline.py finalize \
  --narrative-file output/<podcast>/narrative.md \
  --output-dir output/<podcast>/
```

### Step 4：生成社交媒体文案

读取 `reference/writing-guide.md` + `reference/social-format.md`

产出三个文件：
- `output/<podcast>/title.txt`：≤14 字中文标题
- `output/<podcast>/social.txt`：≤900 字符正文
- `output/<podcast>/tags.txt`：纯文本 tags

### Step 5：Pillow 卡片渲染 + 输出

```bash
~/myenv/bin/python3 scripts/podcast_card_renderer.py \
  --cards output/<podcast>/cards.json \
  --podcast-name "<name>" \
  --title "<title_cn>" \
  --output-dir output/<podcast>/cards/
```

卡片 + 社交文案输出到 `archive/podcasts/{date}-{slug}/`

## 关键规则
- Round 2 太长必须重跑，禁止放宽 max-chars
- 严禁调用外部 LLM 重写 narrative
- Round 3 重试最多 1 次
- 社交文案禁止"读后感"语气

## Reference Documents
| File | Content |
|------|---------|
| `reference/step3-prompts.md` | Round 1-3 prompt 模板 |
| `reference/writing-guide.md` | 叙事写作原则 + 禁止模式 |
| `reference/social-format.md` | 社交文案格式规范 |
| `reference/podcast-reference.md` | 架构表 + 错误处理 |
| `reference/PODCAST_FEEDS.md` | 12 个播客订阅清单 |
