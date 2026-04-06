---
name: auto-redbook
description: 小红书自动发帖（narrative 链路）。含 MCP 发布、note_id 安全恢复、内容准备、图片生成。用户说"发小红书"、"发帖"、"publish to XHS"时触发。
user-invocable: true
allowed-tools: Bash Read Write
---

# XHS Auto Publish Skill

## 0. Single Source Of Truth

本技能以"可执行脚本"为唯一真相，禁止在会话中临时发明流程。

## 0.1 Module Architecture

`publish_all_in_one.py` 是薄入口（CLI 参数、常量、redirect wrappers），实际逻辑分布在以下模块：

| 模块 | 职责 |
|------|------|
| `content_prep.py` | 内容准备：markdown 解析、标题验证、tags 提取、长度压缩 |
| `publish_pipeline.py` | 发布执行：MCP/local 路由、重试、幂等摘要 |
| `note_recovery.py` | note_id 恢复：feed 解析、标题匹配 |
| `publish_state.py` | 状态管理：锁文件、pending_sync、task_id 推断 |
| `orchestrator.py` | 流程编排：发布流程、恢复流程、sync 触发 |

子进程统一使用 `~/myenv/bin/python3`（Python 3.12）。

## 1. Narrative Pipeline

### Step N1: 改写文档

改写后保存为 `{sanitized_title}.md`，含 front matter：

```yaml
---
title: 标题（<=20字）
emoji: 🚀
tags: [tag1, tag2, tag3, tag4, tag5]
style: tech|interview|product|philosophy
---
```

强约束：
- 标题 <= 20 字
- tags 5-10 个，保留 `gegeewu`, `Gegeewu`, `嗝嗝巫`
- 正文 <= 850 字（含签名，不含标题和 tags；XHS 硬限制 1000 字）

### Step N2: 发布

```bash
cd ~/gegeewu-skills/.claude/skills/auto-redbook
USE_XHS_MCP=1 ~/myenv/bin/python3 scripts/publish_all_in_one.py {title}.md --num-images N [--private]
```

脚本分 3 步执行：
- **Step 1**: 内容准备（解析 front matter、校验标题/tags/长度）
- **Step 2**: 图片生成（调用 generate_xhs_images.py）
- **Step 3**: MCP 发布 + 回写

## 2. Safety Rules

### note_id 安全恢复
1. 优先使用 MCP 发布返回的 note_id
2. 如缺失：优先查询 `/api/v1/feeds/list`，标题匹配
3. 恢复失败时保留 `pending_sync.json`

### 幂等与锁
- 每日幂等锁：`locks/published_{lock_type}_YYYY-MM-DD.lock`
- MCP 进程锁：`/tmp/xhs_mcp.lock`

## 3. Style Selection

| style | 适用内容 |
|-------|---------|
| tech | 代码、工程、SaaS 工具、开发者向 |
| interview | 人物、对话、采访、叙事性 |
| product | 产品评测、功能介绍、消费类 |
| philosophy | 观点、趋势分析、思考类 |

## 4. num-images Selection

- 1 张：内容简短（300 字以内）或单一主题
- 2 张：内容中等（300-600 字）或有 2 个清晰段落
- 3 张：内容丰富（600 字以上）或 3+ 主题模块

## Reference Documents
| File | Content |
|------|---------|
| `reference/workflow.md` | 发布流程详细说明 |
| `reference/troubleshooting.md` | 故障排查 |
| `reference/content-rules.md` | 内容规则 |
| `reference/image-spec.md` | 图片规格 |
| `reference/env-baseline.md` | XHS MCP 环境变量基线 |
| `reference/xhs-comment-cli.md` | 评论工具 CLI 用法 |
