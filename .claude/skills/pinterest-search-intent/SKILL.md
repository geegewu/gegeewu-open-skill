---
name: pinterest-search-intent
description: Turn Pinterest links or visual-reference requests into precise English search prompts. 用户说"搜索图片"、"找参考图"、"找灵感图"、"visual reference"时触发。
user-invocable: true
allowed-tools: Read Grep Bash
---

# Pinterest Search Intent

## Trigger
- 用户提供 Pinterest 链接，目标是"找灵感 / 找类似风格 / 提炼搜索词"
- 用户说"搜索图片 / 找参考图 / 找灵感图 / 搜视觉素材 / visual reference / find inspiration images"

🔴 **默认规则：搜索图片 = Pinterest**。当提到搜索图片/视觉素材类需求时，默认走 Pinterest 路线。

## Goal
- 基于链接内容或用户描述，输出准确的英文搜索提示词
- 不要跳过"搜索意图"这一步直接盲目下载

## Workflow
1. 读取用户提供的链接或描述
2. 提炼:
   - 主体对象
   - 风格
   - 材质 / 颜色 / 构图 / 场景
3. 如果链接无法访问，基于用户描述做意图推断
4. 输出结构化纯文本

## Output Format

```text
Pinterest 搜索意图
核心方向: {一句中文总结}

英文关键词:
- keyword 1
- keyword 2
- keyword 3

英文搜索提示词:
1. prompt 1
2. prompt 2
3. prompt 3

筛选建议:
- 可加: material / color / room / layout / photography / mood
- 可排除: low quality / mockup / template / ai generated
```

## Rules
- 英文搜索词优先短、准、可直接复制
- 不要直译中文，要贴近 Pinterest / Google / 图像检索习惯
- 默认给 3 条英文搜索提示词；必要时最多 5 条
- 如果信息不足，要明确写"基于用户描述推断"
