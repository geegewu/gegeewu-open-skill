# gegeewu-open-skill

**一个人的内容工厂，14 个经过实战打磨的 AI Agent Skill。**

这不是一个周末写出来的 demo 集合。这里的每一个 skill，都是在真实的内容创作、知识管理和社交媒体运营中反复使用、反复修正、最终沉淀下来的工具链。41 个 Python 脚本，29 份配置文档，覆盖了从语音转录到社交媒体发布的完整链路。

它们被设计成可以被任何 AI Agent 复用的能力模块——不绑定特定框架，不依赖特定平台，只需要一个能调用 shell 的 agent 和一份 `.env` 文件。

---

## 从声音到文字：两套本地转录引擎

`funasr-asr` 是整个技能集的基石之一。它集成了两套完全本地化的语音识别引擎：FunASR（中文场景，paraformer-zh 四模型协同——ASR 主模型、语音活动检测、标点恢复、说话人分离）和 mlx-whisper（英文及多语言场景，Apple Silicon 原生加速）。没有任何数据上传云端，录音文件在本地完成转录后自动清理。它还包含完整的录制控制——开始录制、停止录制、一键转录，对会议和通话场景开箱即用。

在此基础上，`meeting-summary` 接过转录文本，生成结构化的 HTML 会议纪要报告，含思维导图、待办事项提取和 Apple Reminders 同步。两者组合成 `audio-to-report` pipeline——从一段录音到一份完整的会议纪要，中间不需要任何人工介入。这个流程每周都在真实会议中运行，经历过嘈杂的多人讨论、两小时的马拉松会议、以及各种方言口音的考验。

---

## 播客处理：五步全自动流水线

`podcast-pipeline` 是最复杂的编排技能，也是投入调试时间最长的一个。它从 12 个 RSS feed（含 2 个 YouTube 频道）自动抓取最新剧集，下载音频后调用本地转录引擎，再通过两轮 LLM 处理——第一轮并发摘要各段落，第二轮汇总生成 2800-3500 字的叙事文本——最后渲染为精美的信息卡片和社交媒体文案。YouTube 频道走字幕直取路径跳过转录步骤，RSS 音频则串行转录后自动删除源文件。整条链路处理过上百期中英文播客，从下载到出图平均 15 分钟。

---

## 每日信息聚合：推特 + 博客双源日报

`daily-digest` 融合了两条信息源：一路通过 Playwright 无头浏览器批量抓取 X/Twitter 监控账号的推文，另一路扫描 HN Top 92 RSS 博客（Karpathy 2025 年度榜单）。两路数据合并后统一 AI 评分筛选，最终生成 Markdown 格式的每日 AI 日报。评分不硬编码来源比例，让模型自行判断内容价值。可选一键发布到小红书。这套流程从 2026 年初开始每天运行，筛选过数千条推文和数百篇博客文章。

---

## 社交媒体自动化：小红书全链路

`auto-redbook` 是文件数量最多的技能（21 个脚本 + 6 份参考文档），也是模块化最彻底的一个。它经历过一次大规模重构——从 1650 行的单体脚本拆分为内容准备、发布流水线、笔记恢复、状态管理和流程编排五个独立模块。支持 MCP 浏览器自动化发布、Cookie 过期检测、发布失败后的 note_id 安全恢复、每日幂等锁防重复发布。图片生成调用 Gemini API 并支持多 key 轮替和代理透传。每一个容错机制都是真实踩过坑之后加上去的。

---

## 知识库管理：Obsidian 三件套

`library-intake`、`library-search`、`library-delete` 构成了基于 Obsidian 的个人知识库管理闭环。入库时自动查重防止重复内容，搜索支持三层递进（关键词 → 模糊 → 语义），删除操作同时清理 vault 文件和索引条目。通过 Obsidian Local REST API 实现，数据完全留在本地。

---

## 创作辅助：图片生成与内容摘要

`nano-banana-pro` 封装了 Gemini 3 Pro Image 的图片生成和编辑能力，支持 6 个 API key 自动轮替应对配额限制，支持 HTTPS 代理透传。`summarize` 是一个轻量的内容摘要工具，支持 URL、PDF 和本地文件。`pinterest-search-intent` 将视觉灵感转化为精准的英文搜索提示词。`instagram` 集成了 Graph API 和 Cloudinary，实现 Instagram 发帖自动化。

---

## Skill 一览

### 独立 Skill（11 个）

| Skill | 功能 | 依赖 |
|-------|------|------|
| `pinterest-search-intent` | 视觉参考 → 英文搜索提示词 | 无 |
| `summarize` | URL/PDF/文件内容摘要 | summarize CLI |
| `nano-banana-pro` | AI 生图/编辑图（Gemini 3 Pro Image） | uv, GEMINI_API_KEY |
| `instagram` | Instagram 管理/发帖 | Instagram API, Cloudinary |
| `funasr-asr` | 语音/视频转录 + 录制控制 | FunASR/mlx-whisper, ffmpeg |
| `meeting-summary` | 会议纪要 HTML 报告 | npx markmap-cli |
| `library-intake` | 知识内容归档入库 | Obsidian REST API |
| `library-search` | 三层知识库搜索 | Obsidian REST API |
| `library-delete` | 知识库条目删除 | Obsidian REST API |
| `auto-redbook` | 小红书发帖（MCP 链路） | XHS MCP, nano-banana-pro |

### Pipeline Skill（3 个）

| Pipeline | 子步骤 |
|----------|--------|
| `audio-to-report` | funasr-asr → meeting-summary |
| `daily-digest` | 推特抓取 → 博客抓取 → AI 评分 → 可选 auto-redbook |
| `podcast-pipeline` | RSS 下载 → 转录 → 叙事提炼 → 卡片渲染 → 社交文案 |

---

## 设计哲学

**所有凭证通过环境变量注入，零硬编码。** 每个脚本都有 `~/.env` fallback 读取逻辑，部署时只需一份环境变量文件。

**Skill 之间通过文件系统和标准 I/O 松耦合。** 没有私有协议，没有 RPC 调用，任何能执行 shell 命令的 agent 都可以直接使用。Pipeline skill 通过 `context: fork` 启动独立 agent 编排子步骤，单体 skill 则直接执行。

**每个 skill 都是真实工作流中跑出来的。** 不是为了展示写的 toy project，而是每天在用的生产工具。错误处理、重试逻辑、幂等保护——这些都不是预先设计的，而是在真实失败中一条一条加上去的。

---

## 环境要求

- macOS (Apple Silicon)
- Python 3.12+（`~/myenv/bin/python3`）
- ffmpeg, uv, yt-dlp
- 环境变量配置见 `CLAUDE.md`

## Disclaimer

使用 `auto-redbook` 或其他 skill 进行自动化操作可能违反相关平台的服务条款或使用政策，由此产生的一切风险和后果由使用者自行承担。

## 本skill引用了baoyu以及其他skill 不再赘述

## License

GPL-3.0
