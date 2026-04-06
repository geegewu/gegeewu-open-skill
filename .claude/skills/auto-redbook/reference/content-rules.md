# Content Generation Rules

## Style Detection & Rewriting

### Four Content Styles
| Style | Characteristics | Template | Image Style |
|-------|----------------|----------|-------------|
| `tech` | Technical docs, code, architecture | TECH_DOC_TEMPLATE | UI wireframe / SaaS dashboard |
| `interview` | People stories, conversations, experiences | INTERVIEW_TEMPLATE | New Yorker watercolor/gouache |
| `product` | Products, tools, reviews, comparisons | PRODUCT_TEMPLATE | Corporate Memphis flat |
| `philosophy` | Philosophical essays, literary prose, social critique | PHILOSOPHY_TEMPLATE | Classical ukiyo-e life scene |

### Classification (via prompts_storytelling.py)
- `STYLE_CLASSIFIER_TEMPLATE`: Receives full document, returns one of four labels
- Kimi executes classification; Sonnet orchestrates

### Rewriting
- Each template transforms formal content → XHS narrative style
- Output: markdown with YAML front matter:
  ```yaml
  ---
  title: "带emoji的标题"
  emoji: "🔥"
  style: "tech"
  tags: ["tag1", "tag2", "tag3"]
  ---
  ```

## XHS Copy Standards

### Title (Updated v3 — Accurate & Natural)
- Include emoji (≥1, ≤3)
- **≤ 20 characters** (aim for natural phrasing, not forced compression)
- **Preserve quantifiers**: Keep "页/个/次/倍/小时/分钟/天" etc. — do NOT delete for brevity
  * ✅ "60个标签页不卡顿" / "3倍速度提升" / "30分钟搞定"
  * ❌ "60标签不卡顿" / "3倍提升" / "30min搞定"
- Tone by style:
  * `tech`: Smart builder sharing — like chatting about a project over coffee
  * `interview`: Editorial quality — like a magazine subtitle
  * `product`: Friend recommending — like a private "try this" message (with specific value, not generic praise)
  * `philosophy`: Literary / contemplative — an image or metaphor that makes you pause, not a summary
- AVOID: clickbait (震惊/绝了/神器/yyds), urgency words (必看/赶紧收藏), tutorial tone (手把手)

### Body
- 800-1500 characters (XHS narrative sweet spot for tech/interview content)
- Rich storytelling with scenarios, data, and examples
- **Paragraph spacing**: Double newline (`\n\n`) between paragraphs
- **Section dividers**: All four styles MUST use `━━━━━━━━━━━━━━━` to separate sections/chapters/features
- Must include: hook opener, value body, call-to-action closer
- Tone: conversational, relatable, slightly opinionated

### Tags
- **MANDATORY**: 3-5 tags per note (strictly enforced)
- Mix: 1-2 broad + 2-3 niche + 1-2 trending
- Format: `#标签1 #标签2 #标签3` (separate line before signature)

## Length Validation (publish_all_in_one.py)
- `MAX_TITLE_LENGTH = 20` (XHS platform limit, strictly enforced)
- `MAX_CONTENT_LENGTH = 2000` (relaxed for narrative richness)
- Auto-compression only if exceeds 2000 chars
- Front matter stripped before publishing

## Common Issues
- ❌ Too formal / academic tone → rewrite with more colloquial language
- ❌ Content too long (>1000 chars) → auto-truncate with summary
- ❌ Missing emoji in title → auto-inject based on style
- ❌ Tags contain spaces → auto-replace with underscores
