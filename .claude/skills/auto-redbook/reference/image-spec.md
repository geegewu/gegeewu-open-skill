# Image Specification & Generation Rules

## Image Format
- Minimum resolution: 1080×1440 (3:4)
- Format: PNG
- Naming: `{task_id}_cover.png`, `{task_id}_image_1.png` ~ `{task_id}_image_8.png`
- Count: 1-9 per note (AI decides based on content)
- No slide numbers / page indicators on images

## Generation Pipeline (generate_xhs_images.py)
- Model: nano-banana-pro (Gemini API)
- Concurrent batch: up to 6 images at a time
- Timeout: 120s per image
- Retry: 3 attempts per image with API key rotation

## Style-Based Visual Identity System

Each style has a distinct aesthetic. The **single source of truth** is `get_style_identity()` in `generate_xhs_images.py`. Both cover and detail prompts reference this identity — neither defines its own color palette.

### Architecture principle

```
get_style_identity(style)     ← SOLE visual authority (colors, bg, typography, layout)
  ├── generate_cover_prompt   ← references identity, adds content-specific structure
  └── generate_detail_prompt  ← references identity, adds section-specific focus
```

Cover and detail images MUST be visually indistinguishable in style. Only content differs.

### Document Fidelity (CRITICAL)

All cover images MUST extract labels/terms directly from document content:
- ✅ Use EXACT terminology from document (e.g., "空间管理", "内存优化", "自动归档")
- ❌ Do NOT use generic placeholders (e.g., "高速", "安全", "易用") unless document explicitly uses them
- ✅ Show specific data from document if available (e.g., "8G→3G", "60标签页")
- Tech style: Show only modules/components mentioned in document
- Product style: Extract feature names directly from document text
- Interview style: Use topic names from document instead of generic themes
- Philosophy style: Extract central metaphor/scene from article emotional core

### `tech` style — UI Wireframe
- Reference: Figma mockup, Dribbble UI concept, technical blueprint
- Palette: Grayscale base + muted blue accent (#4A90D9) only — NO other colors
- Background: Off-white (#F5F5F5) with subtle dot grid
- Elements: Rounded-rect wireframe cards, thin gray borders, line icons
- Depth: NO shadows, NO gradients — flat and clean
- Cover: System architecture as polished wireframe diagram (exact modules from doc)
- Detail: Focused module detail, same wireframe aesthetic

### `interview` style — New Yorker Editorial
- Reference: New Yorker covers, Christoph Niemann sketches, Monocle editorial
- Palette: Ink black (#2C2C2C), cream (#FAF8F3), dusty rose (#C4A882), sage (#8B9E7C), terra cotta (#C67B5C)
- Background: Warm cream paper (#FAF8F3)
- Elements: Hand-drawn ink lines, organic shapes, decorative quotation marks, editorial figures
- Cover: Conversation themes as hand-drawn editorial vignettes (NOT digital speech bubbles), use specific topic names from document
- Detail: Topic insights with hand-drawn warmth

### `product` style — Corporate Memphis
- Reference: Notion/Slack/Linear product pages, flat vector illustration
- Palette: Coral (#FF8A80), teal (#4DB6AC), mustard (#FFD54F), lavender (#B39DDB)
- Background: Clean white / warm gray (#FAFAFA)
- Elements: Flat solid fills (NO gradients), geometric shapes, abstract figures with oversized limbs
- Cover: Feature showcase with labels extracted from document (NOT generic "高速/安全/易用")
- Detail: Individual feature with same Memphis aesthetic

### `philosophy` style — Classical Ukiyo-e Life Scene
- Reference: Hokusai, Hiroshige, Utamaro woodblock prints — life scenes, nature, solitude
- Palette: Hiroshige blue (#2E6FA3), vermilion (#C0392B), aged ivory (#F5EDD6), ochre (#C4922A), ink black
- Background: Washi paper texture with woodblock ink grain
- Elements: Life scenes — solitary figures, natural/tech juxtaposition, atmospheric depth, graceful ink outlines
- Mood: Melancholic, wistful, quietly beautiful — NOT geometric poster design
- Cover: Single ukiyo-e scene capturing article's emotional core (e.g., owl under moonlight, lone figure at glowing screen)
- Detail: Different scenes from same world, each exploring one philosophical dimension

### Layout rules (all styles)
- Content fills 70-80% of canvas with balanced margins
- No extreme whitespace or overcrowding
- Typography specs are for AI understanding only — NEVER rendered as visible text

## API Key Rotation
6 Gemini API keys in `GEMINI_API_KEYS` env var (comma-separated).
Rotation: `key_index % len(keys)`, increment on each call.
Fallback: cycle through all keys before declaring failure.

## Known Constraints
- Gemini image generation can be slow (30-120s per image)
- Some styles may get rejected (content policy) — auto-retry with softer prompt
- Max 9 images per XHS note (platform limit)
- Typography px/weight values in prompts may leak as visible text — use semantic descriptions instead
- AI may default to generic labels if document extraction is not explicitly enforced — now fixed in all style prompts (2026-02-16)
