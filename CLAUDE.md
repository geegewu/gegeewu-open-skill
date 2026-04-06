# gegeewu-skills — Project Convention

## 路径约定
- 所有脚本通过 `${CLAUDE_SKILL_DIR}/scripts/` 相对路径引用
- Python 环境: `~/myenv/bin/python3`（Python 3.12，含 PIL 等依赖）
- 输出存储: `~/gegeewu-skills/archive/<skill-name>/`
- Archive 目录不 git 追踪

## 环境变量

所有 API key / secret 通过环境变量注入，不硬编码。  
默认从 `~/.env` 加载（各脚本内有 fallback 读取逻辑）。

| 变量 | 用途 | 依赖 Skill |
|------|------|-----------|
| `GEMINI_API_KEY` | 单 key（summarize / nano-banana-pro） | summarize, nano-banana-pro |
| `GEMINI_API_KEYS` | 逗号分隔多 key 轮替 | auto-redbook (图片生成) |
| `ANTHROPIC_API_KEY` | Anthropic Claude API | podcast-pipeline (step3 Round 1 并发) |
| `INSTAGRAM_ACCESS_TOKEN` | Instagram Graph API | instagram |
| `INSTAGRAM_ACCOUNT_ID` | Instagram 账号 ID | instagram |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary 图片托管 | instagram |
| `CLOUDINARY_API_KEY` | Cloudinary API | instagram |
| `CLOUDINARY_API_SECRET` | Cloudinary Secret | instagram |
| `OBSIDIAN_REST_API_KEY` | Obsidian Local REST API | library-intake, library-search, library-delete |
| `XHS_COOKIE` | 小红书 Cookie | auto-redbook |
| `USE_XHS_MCP` | 启用 XHS MCP 发布（设为 `1`） | auto-redbook |
| `TELEGRAM_BOT_TOKEN` | Telegram 推送（可选） | podcast-pipeline, daily-digest |
| `PYTHON` | Python 解释器路径覆盖 | podcast-pipeline, funasr-asr |
| `BLOGWATCHER_BIN` | blogwatcher Go binary 路径覆盖 | daily-digest |
| `FONT_DIR` | 字体目录（默认 `~/Library/Fonts`） | auto-redbook, podcast-pipeline |
| `TELEGRAM_CHAT_ID` | Telegram 推送目标 Chat ID | podcast-pipeline, auto-redbook, funasr-asr |
| `OBSIDIAN_VAULT_PATH` | Obsidian vault 本地路径 | podcast-pipeline, meeting-summary |

## 本地模型

### 语音转录（funasr-asr）

提供 **两套本地模型**，按场景选择：

| 引擎 | 模型 | 语言 | 适用场景 | 硬件要求 |
|------|------|------|---------|---------|
| **FunASR** | paraformer-zh + VAD + 标点 + 说话人分离 | 中文为主 | 中文会议、播客、通话录音 | CPU 可跑，GPU 更快 |
| **mlx-whisper** | `mlx-community/whisper-large-v3-turbo` | 多语言 | 英文播客、多语言内容 | Apple Silicon（MLX 加速） |

**FunASR 模型组件**（4 个模型协同工作）：
```
~/.cache/modelscope/hub/models/iic/
├── speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch  # ASR 主模型
├── speech_fsmn_vad_zh-cn-16k-common-pytorch                                  # 语音活动检测
├── punc_ct-transformer_cn-en-common-vocab471067-large                         # 标点恢复
└── speech_campplus_sv_zh-cn_16k-common                                        # 说话人分离
```

**mlx-whisper 模型**：
```
~/.cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo/  # 首次运行自动下载
```

**选择引擎**：
```bash
~/myenv/bin/python3 scripts/transcribe.py <音频> --engine funasr   # 中文
~/myenv/bin/python3 scripts/transcribe.py <音频> --engine mlx      # 英文/多语言
```

### 图片生成（nano-banana-pro）

| 模型 | 调用方式 | 说明 |
|------|---------|------|
| Gemini 3 Pro Image | REST API（`GEMINI_API_KEY`） | 远程调用，非本地模型 |

### 播客 Pipeline（podcast-pipeline）

| 步骤 | 模型 | 调用方式 |
|------|------|---------|
| Step 2 转录 | FunASR / mlx-whisper | 本地（同 funasr-asr） |
| Step 3 Round 1 并发摘要 | Claude（Anthropic API） | `ANTHROPIC_API_KEY` 远程调用 |
| Step 3 Round 2-3 | Agent 原生模型 | 由 Claude Code agent 直接处理 |

## MCP 服务

| MCP Server | 用途 | 依赖 Skill | 启动方式 |
|-----------|------|-----------|---------|
| **XHS MCP** | 小红书笔记发布（go-rod 浏览器自动化） | auto-redbook | `USE_XHS_MCP=1`，脚本内自动管理进程 |
| **Obsidian Local REST API** | 知识库 CRUD（Obsidian 插件） | library-intake, library-search, library-delete | Obsidian 内启用插件，监听 `127.0.0.1:27124` |

**XHS MCP 配置**（auto-redbook 的 `reference/env-baseline.md` 有完整基线）：
- 需要 `XHS_COOKIE` 环境变量（从 Chrome 导出）
- MCP 进程锁：`/tmp/xhs_mcp.lock`
- Cookie 过期检查：`tools/cookies.json`

**Obsidian REST API 配置**：
- 安装 Obsidian 插件 `Local REST API`
- 设置 API Key → 写入 `OBSIDIAN_REST_API_KEY` 环境变量
- 默认端口 `27124`（HTTPS）

## 外部依赖

| 工具 | 安装 | 用途 |
|------|------|------|
| `ffmpeg` | `brew install ffmpeg` | 音频格式转换（funasr-asr） |
| `yt-dlp` | `pip install yt-dlp`（myenv） | YouTube 字幕下载（podcast-pipeline） |
| `opencli` | `/opt/homebrew/bin/opencli` | X/Twitter 抓取（daily-digest） |
| `blogwatcher` | Go binary `~/go/bin/blogwatcher` | RSS 博客扫描（daily-digest） |
| `uv` | `brew install uv` | Python 包运行（nano-banana-pro） |
| `npx markmap-cli` | npm 全局 | 思维导图渲染（meeting-summary） |

## 输出规则
- 所有产出写入 `archive/` + 终端输出
- 需要推送时由用户手动决定，skill 不自动发送
- archive/ 下按 skill 名分子目录，文件名含日期

## Python 执行
- 优先 `~/myenv/bin/python3`（可通过 `PYTHON` 环境变量覆盖）
- 不依赖系统 python3（macOS 默认 3.9 缺包）
