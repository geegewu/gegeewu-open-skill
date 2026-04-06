# Podcast Monitor Reference

详细参考信息，按需加载。

---

## 中文播客处理差异

- **转录引擎**：与英文相同，使用 mlx-whisper large-v3-turbo（Whisper 原生支持中文）
- **Step 3 提炼**：中文播客转录结果已经是中文，**无需翻译**，直接提炼核心文本
- **Step 4 文案**：格式与英文播客完全相同，无差异
- **语言检测**：通过 `PODCAST_FEEDS.md` 中的 `语言` 字段标识，`zh` = 中文播客

---

## Architecture

| Step | 执行模式 | 说明 |
|------|----------|------|
| Step 1 | 脚本 + Agent | `rss_downloader.py` 下载 + cron agent 提取元信息（subagent 模型） |
| Step 2 | 纯脚本（detach 进程） | `transcribe_queue.py` 独立后台，无 agent 参与 |
| Step 3 | 脚本 + Agent 协作 | `step3_pipeline.py prepare/finalize`（确定性逻辑）+ Agent 处理 LLM 部分（使用 subagent 模型） |
| Step 4 | Agent 直接执行 | Agent 读 reference 文档，生成文案 |
| Step 5 | Agent + Python 调用 | Agent 调用 `podcast_card_renderer.py` 渲染 + `podcast_post_pipeline.py` 发送 |

---

## 文件结构

```
├── SKILL.md                   # 核心指令
├── PODCAST_FEEDS.md           # 12 个 feed 清单
├── reference/
│   ├── writing-guide.md       # 写作原则（Step 3 + Step 4）
│   ├── social-format.md       # 社交文案格式规则
│   ├── step3-prompts.md       # Step 3 batch/narrative prompt 模板
│   └── podcast-reference.md   # 本文件
├── rss_downloader.py          # RSS 增量下载 + detach 转录队列
├── transcribe_queue.py        # 独立后台转录进程
├── podcast_card_renderer.py   # Pillow 卡片渲染（渲染参数在此定义）
├── episode_meta_extractor.py  # 元信息提取 prompt 模板
├── step3_pipeline.py          # Step 3 辅助脚本（prepare / finalize）
├── podcast_post_pipeline.py   # 工具库（send_telegram / validate_cards）
├── test_feeds.py              # RSS 连通性测试
├── transcripts/               # 转录输出（YYYY-MM-DD/<slug>.md）
├── logs/                      # 日志（rss_downloader + transcribe_queue）
└── output/                    # 生成的图片和文案
```

---

## Error Handling

| 错误 | 处理 |
|------|------|
| feed 解析失败 | 跳过，记录 logs/rss_downloader_YYYY-MM-DD.log |
| 转录失败/超时 | state 标记 transcribed:false，Telegram 推送，不重试 |
| yt-dlp extract_info 超时 | ThreadPoolExecutor 60s 超时，跳过该视频 |
| yt-dlp 字幕下载超时 | ThreadPoolExecutor 60s 超时，state 标记 subtitle_download_timeout |
| 音频下载总超时 | 单文件 600s 上限，超时清理 .tmp 文件 |
| 元信息提取失败 | agent 模型调用失败时降级跳过，不阻塞下载流程 |
| 全部 feed 并发超时 | asyncio.wait_for 1200s，超时后取消未完成任务，继续通知+转录 |
| yt-dlp 未安装 | `pip install yt-dlp`（myenv 环境） |
| YouTube 字幕下载失败 | state 标记 skipped:true, reason:subtitle_download_failed |
| YouTube 无可用字幕 | 跳过该视频，记录日志 |
| PIL 未安装 | 使用 `$PYTHON`（myenv 含 PIL） |
| Telegram 发送失败 | 检查 `TELEGRAM_BOT_TOKEN` 环境变量（`~/.env`） |

---

## Runtime Visibility

| 日志 | 路径 |
|------|------|
| RSS 下载日志 | `logs/rss_downloader_YYYY-MM-DD.log` |
| 转录队列日志 | `logs/transcribe_queue_YYYY-MM-DD.log` |
| Step 3 pipeline | stdout（脚本直接输出） |
| Telegram 通知 | 下载完成/转录完成/失败均推送 |
