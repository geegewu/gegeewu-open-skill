---
name: nano-banana-pro
description: Generate/edit images with Nano Banana Pro (Gemini 3 Pro Image). Use for image create/modify requests. Supports text-to-image + image-to-image; 1K/2K/4K. 用户说"生成图片"、"生图"、"编辑图片"时触发。
user-invocable: true
allowed-tools: Bash Read
---

# Nano Banana Pro Image Generation & Editing

Generate new images or edit existing ones using Google's Nano Banana Pro API (Gemini 3 Pro Image).

## Usage

**Generate new image:**
```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/generate_image.py --prompt "your image description" --filename "output-name.png" [--resolution 1K|2K|4K] [--api-key KEY]
```

**Edit existing image:**
```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/generate_image.py --prompt "editing instructions" --filename "output-name.png" --input-image "path/to/input.png" [--resolution 1K|2K|4K] [--api-key KEY]
```

**Important:** Always run from the user's current working directory so images are saved where the user is working.

## Default Workflow (draft → iterate → final)

- Draft (1K): quick feedback loop
- Iterate: adjust prompt in small diffs; keep filename new per run
- Final (4K): only when prompt is locked

## Resolution Options

- **1K** (default) - ~1024px resolution
- **2K** - ~2048px resolution
- **4K** - ~4096px resolution

Map user requests:
- No mention → `1K`
- "low resolution", "1080p", "1K" → `1K`
- "2K", "2048", "medium resolution" → `2K`
- "high resolution", "hi-res", "4K", "ultra" → `4K`

## API Key

Check order:
1. `--api-key` argument
2. `GEMINI_API_KEY_1` to `GEMINI_API_KEY_6` (rotation)
3. `GEMINI_API_KEY` fallback

## Proxy

Supports proxy via `GEMINI_PROXY`, `HTTPS_PROXY`, or `HTTP_PROXY` environment variables.

## Filename Generation

Pattern: `yyyy-mm-dd-hh-mm-ss-descriptive-name.png`

Examples:
- "A serene Japanese garden" → `2025-11-23-14-23-05-japanese-garden.png`
- Unclear context → `2025-11-23-17-12-48-x9k2.png`

## Image Editing

Use `--input-image` with editing instructions in `--prompt`.
Resolution auto-detected from input image when not explicitly set.

## Prompt Templates (high hit-rate)

- Generation: "Create an image of: <subject>. Style: <style>. Composition: <camera/shot>. Lighting: <lighting>. Background: <background>. Color palette: <palette>. Avoid: <list>."
- Editing: "Change ONLY: <single change>. Keep identical: subject, composition/crop, pose, lighting, color palette, background, text, and overall style."

## Output

- Saves PNG to current directory
- Script outputs the full path to the generated image
- Do not read the image back — just inform the user of the saved path
