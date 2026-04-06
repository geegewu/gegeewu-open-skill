---
name: daily-digest
description: 每日内容日报。整合推特+博客抓取、AI评分筛选、生成Markdown报告、可选发布小红书。用户说"跑日报"、"生成日报"、"daily digest"时触发。
user-invocable: true
allowed-tools: Bash Read Write WebFetch
context: fork
agent: general-purpose
---

# daily-digest

整合推特日报 + 博客日报，统一评分筛选，生成 Markdown 报告，可选发布 XHS。

全部手动触发，无 cron。

## Pipeline

### Step 1: 推特抓取

```bash
~/myenv/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/scrape-batch-opencli.py
```

- 批量抓取 X 账号推文（Playwright/opencli）
- 监控账号列表见 `reference/watchlist.md`
- 输出 JSON 到 stdout

### Step 2: 博客抓取

```bash
~/myenv/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/generate-digest.py
```

- 扫描 HN Top 92 RSS 博客（Karpathy 2025 榜单）
- 并发获取文章摘要（5 workers）
- 输出结构化 JSON

### Step 3: AI 评分筛选

- 合并推特 + 博客两路数据
- 统一评分，不硬编码来源比例
- 筛选后产出候选集合

### Step 4: 生成 Markdown 报告

- 详细报告 → `archive/digests/{date}-digest.md`
- 报告格式见 `reference/report-template.md`

### Step 5: 可选 — XHS 发布

用户确认后，调用 `/auto-redbook` 发布精简版到小红书。

## 日期规则

- 抓取的是**昨天**的内容
- 文件命名用昨天日期：`ai-digest-YYYY-MM-DD.md`、`YYYY-MM-DD.md`

## Validation

推特日报生成后运行验证：
```bash
~/myenv/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/validate_digest.py <markdown-file>
```

博客文章预处理（降低 token 消耗）：
```bash
~/myenv/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/preprocess_articles.py <markdown-file>
```

## Output Format

### Markdown 文件
- 每篇：中文标题 + 300-500 字详细摘要
- 保留关键英文术语

### Terminal Summary
- 每篇三行：来源域名 → 加粗标题 → 2-3 句摘要（≤80字）

## Reference Documents
| File | Content |
|------|---------|
| `reference/watchlist.md` | 推特监控账号列表 |
| `reference/report-template.md` | 推特日报 Markdown 模板 |
