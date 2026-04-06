# Skills Index

## 独立 Skill

| Skill | 调用 | 功能 | 依赖 |
|-------|------|------|------|
| pinterest-search-intent | `/pinterest-search-intent` | 视觉参考→英文搜索提示词 | 无 |
| apple-notes | `/apple-notes` | macOS 备忘录 CRUD | AppleScript |
| summarize | `/summarize` | URL/PDF/文件内容摘要 | summarize CLI |
| nano-banana-pro | `/nano-banana-pro` | AI 生图/编辑图（Gemini 3 Pro Image） | uv, GEMINI_API_KEY |
| instagram | `/instagram` | Instagram 管理/发帖 | Instagram API, Cloudinary, python3.12 |
| funasr-asr | `/funasr-asr` | 语音/视频转录 + 录制控制 | FunASR/mlx-whisper, ffmpeg, Python 3.12 |
| meeting-summary | `/meeting-summary` | 会议纪要 HTML 报告 | npx markmap-cli, Python 3.12 |
| library-intake | `/library-intake` | 知识内容归档入库 | Obsidian REST API |
| library-search | `/library-search` | 三层知识库搜索 | Obsidian REST API |
| library-delete | `/library-delete` | 知识库条目删除 | Obsidian REST API, Python 3.12 |
| auto-redbook | `/auto-redbook` | 小红书发帖（MCP 链路） | XHS MCP, Python 3.12, nano-banana-pro |

## Pipeline Skill（编排）

| Pipeline | 调用 | 子 Skill | 触发词 |
|----------|------|---------|--------|
| audio-to-report | `/audio-to-report` | funasr-asr → meeting-summary | 会议录音、纪要 |
| daily-digest | `/daily-digest` | 推特抓取 → 博客抓取 → 合并评分 → 可选 auto-redbook | 跑日报、daily digest |
| podcast-pipeline | `/podcast-pipeline` | RSS → funasr-asr → 提炼 → 卡片 → 文案 | 处理播客 |

## 组合关系

- `/audio-to-report` = `/funasr-asr` + `/meeting-summary`
- `/podcast-pipeline` 内部调用 `/funasr-asr` 做转录
- `/daily-digest` 可选调用 `/auto-redbook` 发布到小红书
- `/library-intake` 入库前自动调用 `/library-search` 查重
