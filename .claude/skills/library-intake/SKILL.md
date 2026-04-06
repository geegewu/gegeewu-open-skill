---
name: library-intake
description: Intake any content type (project, skill, tool, article, concept, collection) for gegeewu-library. Classifies type, generates category/tags, checks duplicates, writes Obsidian archive. 用户说"归档"、"入库"、"收录"时触发。
user-invocable: true
allowed-tools: Bash Read Write WebFetch WebSearch Grep
---

# library-intake

Use this skill for any new content intake.

## Default Goal
- Turn a raw clue into a reusable archive entry.
- Always produce:
  - Terminal structured summary
  - Obsidian full Markdown archive with YAML frontmatter
  - Unified JSON index update

## Required Flow

### Step 1: Input Preprocessing
根据输入形态选择处理路径，目标是获取足够信息供 Step 2 分类。

#### 1a. GitHub Link
1. 解析 owner/repo
2. fetch README 摘要 + 顶层目录结构
3. 将 README 内容 + 目录结构作为分类依据传递给 Step 2
4. 对于最终判定为 skill 的：额外执行 source capture

#### 1b. Non-GitHub Link
**必须**获取页面正文内容，按优先级尝试：
1. fetch + `Accept: text/markdown`（首选）
2. WebFetch 获取页面内容
3. 标准 fetch 获取 HTML
4. 以上全部失败 → 退化为 1c 文本处理

#### 1c. Pure Text (name/keyword/concept)
1. LLM 判断可能的 type 方向
2. WebSearch 搜索目标信息
3. 搜索到 URL 后按 1b 提取页面正文

### Step 2: LLM Classification
基于 Step 1 获取的内容，综合判断：
- `type`: project / skill / tool / article / concept / collection
- `category`: 从预设值选取
- `tags`: 3-8 个英文小写标签
- `summary`: 100 字以内中文摘要

#### Classification Matrix

| Priority | Signal | → type |
|----------|--------|--------|
| 1 | 有 SKILL.md + 触发条件 | `skill` |
| 2 | 仓库名含 awesome / curated list | `collection` |
| 3 | 协议规范 / 方法论 / 抽象概念 | `concept` |
| 4 | 博客文章 / 教程 / 技术分享 | `article` |
| 5 | SaaS / 商业产品 / 不可自部署 | `tool` |
| 6 | GitHub 仓库 + 可安装部署 / 开源库 | `project` |

### Step 3: Duplicate Check (Three Layers)
1. **JSON index**: search `reference/library-index.json` for name/slug/aliases match
2. **Obsidian REST API**: `POST /search/simple/?query=<keyword>` for full-text search
3. If found → update existing entry. Do not create parallel entry.

### Step 4: Search & Gather
- Official sources first, community second.

### Step 5: Terminal Output
输出结构化摘要到终端，按 type 选择模板。

#### Output Templates

**project**: `[project] <name> — <category> | <tags> | <summary>`
**skill**: `[skill] <name> — <category> | <tags> | <summary>`
**tool**: `[tool] <name> — <category> | <tags> | <summary>`
**article**: `[article] <title> — <category> | <tags> | <summary>`
**concept**: `[concept] <name> — <category> | <tags> | <summary>`
**collection**: `[collection] <name> — <category> | <tags> | <summary>`

包含：类型、分类、标签、一句话摘要、核心功能（5-8条）、官方链接、Obsidian 路径。

### Step 6: Obsidian Output

Write full Markdown archive with YAML frontmatter via Obsidian REST API.

```
PUT /vault/knowledge-base/<types>/<slug>/README.md
Content-Type: text/markdown
Authorization: Bearer ${OBSIDIAN_REST_API_KEY}
Host: 127.0.0.1:27124 (HTTPS, skip TLS verify)
```

路径是 vault 相对路径：
```
PUT /vault/knowledge-base/projects/bb-browser/README.md
```

### Step 7: Index Update
Update `reference/library-index.json` with all fields:
name, slug, type, category, tags, summary, aliases, official_url, github_url, obsidian_path, updated_at, source_captured.

## Hard Rules
- Do not skip type classification
- Do not skip duplicate checks
- Do not write only terminal output without writing the archive
- Do not update JSON without updating Obsidian
- Obsidian 写入必须通过 REST API（`https://127.0.0.1:27124`）
- `OBSIDIAN_REST_API_KEY` must be available in environment
- REST API 路径使用 vault 相对路径

## Error Handling
- If duplicate-check results disagree between JSON and Obsidian: report drift, prefer update
- If `OBSIDIAN_REST_API_KEY` is missing: stop archive writing and report
- If REST API is unavailable: stop and report error
