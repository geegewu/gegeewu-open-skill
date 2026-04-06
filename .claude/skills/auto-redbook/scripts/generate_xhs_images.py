#!/usr/bin/env python3
"""
小红书图片生成引擎（单图/多图智能生成）

使用场景：
  # 单图（默认）
  python3 generate_xhs_images.py content.md
  
  # 多图（2-9张，包括首图）
  python3 generate_xhs_images.py content.md --num-images 3

架构：
  - 动态拆分文案（自动提取标题、关键词）
  - 基于风格参数生成 prompts（tech/interview/product/philosophy）
  - 并发生成图片（API key 轮换 + 重试机制）
  - 失败快速终止（清理已生成图片）
"""

# STYLE_VISUAL_DNA removed — use get_style_identity(doc_style) instead (defined below)


def get_style_identity(doc_style):
    """Return style-specific visual identity block for prompt injection.
    
    Each style has a distinct aesthetic to avoid generic AI-infographic look.
    The identity block is injected into EVERY image prompt in a series
    to maintain cross-image consistency.
    """
    if doc_style == 'tech':
        return """SERIES VISUAL IDENTITY — Polished UI Design Style (High-Fidelity)
- Art style: High-fidelity UI design — like a polished Dribbble shot or premium SaaS dashboard, NOT a wireframe
- Line work: Clean strokes in medium gray (#9B9B9B), dashed lines for secondary connections
- Color: Monochrome grayscale base + ONE accent: muted blue (#4A90D9) for highlights and active states only
- Background: Soft off-white (#F5F5F5) with subtle dot grid (#E0E0E0). Apply a very gentle radial vignette (edges 2-3% darker) for depth.
- Shapes: Rounded rectangles, pill buttons, toggle switches, input fields
- Typography: System UI sans-serif (like San Francisco). Titles in semibold dark gray (#2C2C2C), body labels in medium gray (#5C5C5C), captions in light gray (#9B9B9B). Generous spacing for Chinese characters. Left-aligned text, centered titles.
- Icons: Simple line icons (Feather/Lucide style), thin stroke, same gray as lines
- Depth & Elevation (IMPORTANT — adds polish):
  * Primary cards: Very subtle soft shadow (blur 12-16px, color rgba(0,0,0,0.06)), slight white fill (#FFFFFF) to lift off background
  * Secondary cards: Slightly darker fill (#F0F0F0) with no shadow — creates 2-layer depth
  * Active/highlighted elements: Very faint blue tint background (rgba(74,144,217,0.08)) applied ONLY to specific component boxes — NOT as background decoration, NO glow, NO blur halo
  * Background → Cards → Accent overlays = 3 clear visual layers
  * Keep shadows VERY subtle — the goal is gentle elevation, not dramatic 3D
- Decorative: Corner radius labels, status dots (green/amber), breadcrumb paths
- AVOID: Bright saturated colors, Apple marketing gradients, stock photo feel, heavy 3D, handwritten fonts, blue/purple/green gradient fills, harsh drop shadows, decorative gradient blobs, color fog, bokeh overlays, light leak effects, background color splashes, colored shadows (ALL shadows MUST be rgba(0,0,0,x) only — NO blue/purple/tinted shadows)
- LAYOUT: Content fills 70-80% of the canvas with balanced margins on all sides. No extreme whitespace or overcrowding.
- NEVER render typography specifications (font sizes, weight numbers, pixel values) as visible text in the image
- NEVER render "R8", "R10", or any revision/round markers as visible text in the image
- NEVER use dark fills anywhere — ALL surfaces (background, cards, panels, headers) MUST be white (#FFFFFF) or light gray (#F0F0F0) MAXIMUM. Dark-themed sections are ABSOLUTELY REJECTED.
- ALL rendered text MUST be in Simplified Chinese (简体中文). Traditional Chinese characters (繁體字) are ABSOLUTELY FORBIDDEN — if any appear, the image is rejected.
- All images in this series MUST look like they came from the same Figma design file

ABSOLUTE NEGATIVE CONSTRAINTS — PALETTE LOCK (image rejected if ANY violated):
- The ONLY non-grayscale color allowed in the entire image is #4A90D9 (muted blue)
- Permitted grayscale values: #FFFFFF, #F5F5F5, #F0F0F0, #E8E8E8, #E0E0E0, #9B9B9B, #5C5C5C, #2C2C2C
- To distinguish multiple items, tools, or categories, use SHAPE and ICON differences — solid vs dashed border, circle vs square, filled vs outlined — NEVER color differences
- ANY pixel of red, green, orange, purple, teal, yellow, pink, or any hue other than #4A90D9 = image REJECTED
- NO layout elements not defined in this identity (no tabs, sidebars, floating toolbars, or novel UI patterns)
- NO decorative elements not specified above — if it is not in this identity block, it must NOT appear
"""
    elif doc_style == 'interview':
        return """SERIES VISUAL IDENTITY — New Yorker Editorial Illustration Style (Watercolor & Gouache)
- Art style: Hand-drawn editorial illustration with watercolor and gouache washes — like New Yorker magazine covers painted by Christoph Niemann or Maira Kalman. NOT digital vector. NOT infographic.
- Medium feel: Gouache and watercolor on textured paper. Paint strokes are visible. Edges are soft and slightly uneven. Colors bleed gently at boundaries.
- Line work: Expressive ink outlines with visible hand pressure — thicker at curves and corners, tapering at stroke ends. Lines are slightly imperfect, like a fine-tipped brush pen on absorbent paper.
- Color (CRITICAL — watercolor/gouache palette):
  * Base washes: warm ivory (#F7F2E8), dusty blush (#DEB8A0), sage grey-green (#8B9E8C), muted cobalt (#5B7A9D)
  * Gouache accents: terra cotta (#C67B5C), ink black (#2C2C2C), soft ochre (#C9A84C)
  * Max 4 colors per image. Colors should look hand-mixed, slightly desaturated, never neon or pure digital.
  * Washes overlap and layer — earlier washes show through later ones (wet-on-wet effect)
- Background: Aged watercolor paper texture — warm cream with visible fiber grain and subtle tooth. Apply faint coffee-stain or paper aging effect at corners.
- Figures & objects: Simplified editorial figures with gestural quality — loose brushwork, expressive silhouettes. Characters have warmth and personality, NOT geometric abstraction.
- Depth & Texture (CRITICAL for warmth):
  * Foreground elements: heavier gouache opacity, darker outlines
  * Background elements: lighter watercolor wash, softer edges, less detail
  * Key focal areas: small gouache highlights (near-white strokes) to create painted depth
  * Paper grain should be visible throughout — especially in light wash areas
  * Ink lines should show slight bleeding into watercolor wash (natural absorption effect)
- Typography (if any): Hand-lettered serif, slightly irregular baseline, ink wash behind text blocks
- AVOID: Perfect vector geometry, digital gradients, flat fills, infographic grids, mind maps, corporate illustration, neon colors, clean white backgrounds, smooth airbrushed gradients
- LAYOUT: Single strong compositional focal point. Generous breathing room. NOT a diagram or chart.
- NEVER render typography specifications or revision markers as visible text in the image
- ALL rendered text MUST be in Simplified Chinese (简体中文). Traditional Chinese characters (繁體字) are ABSOLUTELY FORBIDDEN.
- All images MUST feel like they belong on the cover of The New Yorker — painted, thoughtful, quietly witty

ABSOLUTE NEGATIVE CONSTRAINTS — PALETTE LOCK (image rejected if ANY violated):
- The ONLY colors allowed are: warm ivory (#F7F2E8), dusty blush (#DEB8A0), sage grey-green (#8B9E8C), muted cobalt (#5B7A9D), terra cotta (#C67B5C), ink black (#2C2C2C), soft ochre (#C9A84C) — MAX 4 per image
- NO neon, saturated, or digitally pure colors — all colors must look hand-mixed and slightly desaturated
- NO digital gradients, flat vector fills, or clean geometric edges
- NO elements that look computer-generated — every stroke must feel hand-painted
- If it is not in this identity block, it must NOT appear in the image
"""

    elif doc_style == 'philosophy':
        return """SERIES VISUAL IDENTITY — Classical Ukiyo-e Woodblock Print (Life Scene, Emotional & Melancholic)
- Art style: Classical Japanese ukiyo-e woodblock print — inspired by Hokusai, Hiroshige, Utamaro. Rich in storytelling, life scenes, and quiet emotional weight. NOT a geometric poster. NOT graphic design.
- Medium feel: Woodblock ink on washi paper — visible printing texture, slight ink bleed at edges, layered color blocks with natural registration variation (slight misalignment between color layers, as in real woodblock prints)
- Color palette (authentic ukiyo-e):
  * Prussian blue / Hiroshige blue (#1B4F8A, #2E6FA3) — dominant atmosphere color
  * Vermilion / persimmon (#C0392B, #E8604C) — warm accent for focal elements
  * Aged ivory / cream (#F5EDD6) — paper base, breathing space
  * Ochre gold (#C4922A) — secondary warm tone
  * Ink black (#1A1A1A) — outlines and fine detail
  * MAX 5 colors. Flat woodblock fills with subtle ink grain texture.
- Scene & composition:
  * A LIFE SCENE — human figures, natural elements, quiet moments of solitude or contemplation
  * Strong diagonal composition typical of ukiyo-e (figure in foreground, vast landscape behind)
  * Foreground element (figure, object) contrasted against expansive background (sky, sea, city at night)
  * Natural and technological elements woven together — an owl on a server rack, a lone figure facing a glowing screen like a lantern in fog, a server tower beside ancient pine trees
  * Technology appears ONLY as distinct physical objects (server rack, laptop, screen glow, LED lights) — NEVER as textures or patterns embedded in natural elements (no circuit traces on water/mountains/sky/trees)
  * Asymmetric but balanced — ukiyo-e masters never center-aligned everything
- Line work: Precise, deliberate ink outlines with natural variation in weight — thicker contour lines, thinner interior detail lines. Graceful curves, no harsh mechanical lines.
- Texture:
  * Washi paper grain visible across entire image
  * Woodblock ink texture on flat color fills — subtle grain, NOT smooth digital fills
  * Slight color bleeding at outline edges (natural woodblock registration)
- Mood: Melancholic, wistful, quietly beautiful. The loneliness of modern life rendered in the visual language of 200 years ago. Time has changed; solitude has not.
- AVOID: Geometric poster layouts, flat vector graphics, corporate illustration, speech bubbles, diagrams, text-heavy compositions, anime style, modern manga aesthetic
- LAYOUT: 3:4 vertical. Single unified scene, NOT a collage or diagram. Sky/negative space in upper portion, grounded elements below — classical ukiyo-e vertical structure.
- NEVER render typography specifications or revision markers as visible text in the image
- ALL rendered text MUST be in Simplified Chinese (简体中文). Traditional Chinese characters (繁體字) are ABSOLUTELY FORBIDDEN.
- All images MUST feel like they could hang in a museum — printed, atmospheric, emotionally resonant

ABSOLUTE NEGATIVE CONSTRAINTS — PALETTE LOCK (image rejected if ANY violated):
- The ONLY colors allowed are: Prussian blue (#1B4F8A, #2E6FA3), vermilion (#C0392B, #E8604C), aged ivory (#F5EDD6), ochre gold (#C4922A), ink black (#1A1A1A) — MAX 5 per image
- ALL color fills must have woodblock ink grain texture — NO smooth digital fills
- NO modern graphic design elements — no flat vector shapes, no geometric poster layouts, no infographic elements
- NO anime, manga, or contemporary illustration styles
- Technology must appear ONLY as distinct physical objects (server, screen, cables) — NEVER as patterns or textures merged with natural scenery
- If it is not in this identity block, it must NOT appear in the image
"""
    elif doc_style == 'product':
        return """SERIES VISUAL IDENTITY — Corporate Memphis / Modern SaaS Style (Polished)
- Art style: Corporate Memphis illustration — like Notion, Slack, Dropbox, or Linear marketing pages
- Shapes: Geometric flat vector — circles, rounded rectangles, abstract human figures with oversized limbs
- Color: Restrained Memphis palette with max 4 colors:
  * Primary: soft coral (#FF8A80), muted teal (#4DB6AC)
  * Accent: warm mustard (#FFD54F), soft lavender (#B39DDB)
  * Neutral: warm gray (#F5F5F5 bg, #616161 text)
  * NO pure black — use dark charcoal (#37474F) instead
- Background: Clean white or very light warm gray (#FAFAFA). Apply a very subtle warm radial glow in center (2-3% brighter) for visual focus.
- Fills: Solid fills as primary method. Allow very subtle single-direction gradients ONLY within colored cards (e.g., coral top → slightly darker coral bottom, max 10% shift) for gentle dimension.
- Typography: Rounded sans-serif (Nunito/Poppins style). Titles in bold dark charcoal (#37474F), body labels in semibold charcoal (#616161), short labels on cards in bold white on colored backgrounds. Centered titles, left-aligned body. Friendly and approachable feel.
- Icons: Filled geometric icons with rounded corners, matching the 4-color palette
- Characters (if any): Abstract geometric people, disproportionate limbs, minimal facial features
- Depth & Polish (IMPORTANT — adds premium feel):
  * Feature cards: Soft shadow (blur 12-16px, rgba(0,0,0,0.06)) to float above background
  * Colored cards: A very subtle inner highlight at top edge (1px lighter shade) for soft bevel effect
  * Floating decorative shapes: Apply 30-50% opacity so they recede into background depth layer
  * Primary cards sit on Layer 2 (shadow), decorative shapes on Layer 1 (behind, faded) — creates depth
  * Keep it GENTLE — think Linear or Vercel landing page polish, not heavy skeuomorphism
- Decorative: Floating geometric shapes (circles, squiggles, abstract blobs), subtle confetti dots — all at reduced opacity
- AVOID: Realistic illustrations, photo-realism, sharp angles, dark/moody tones, complex multi-stop gradients, serif fonts, blue/purple/green gradient fills, harsh shadows
- LAYOUT: Content fills 70-80% of the canvas with balanced margins on all sides. No extreme whitespace or overcrowding.
- NEVER render typography specifications (font sizes, weight numbers, pixel values) as visible text in the image
- NEVER render "R8", "R10", or any revision/round markers as visible text in the image
- NEVER use dark fills anywhere — ALL surfaces (background, cards, panels) MUST be white (#FAFAFA), light gray (#F5F5F5), or pastel Memphis colors (coral/teal/mustard/lavender). Dark-themed sections are ABSOLUTELY REJECTED.
- ALL rendered text MUST be in Simplified Chinese (简体中文). Traditional Chinese characters (繁體字) are ABSOLUTELY FORBIDDEN.
- All images in this series MUST feel like slides from the same SaaS product landing page

ABSOLUTE NEGATIVE CONSTRAINTS — PALETTE LOCK (image rejected if ANY violated):
- The ONLY accent colors allowed are: soft coral (#FF8A80), muted teal (#4DB6AC), warm mustard (#FFD54F), soft lavender (#B39DDB) — MAX 4 per image
- Neutrals: warm gray (#F5F5F5), charcoal (#37474F, #616161) — NO pure black
- NO realistic illustrations, photographic elements, or complex multi-stop gradients
- NO dark or moody tones — all surfaces must be light and warm
- NO sharp angular shapes — all shapes must have rounded corners
- If it is not in this identity block, it must NOT appear in the image
"""
    elif doc_style == 'digest':
        return """SERIES VISUAL IDENTITY — Economist-style News Card Style (Clean & Structured)
- Art style: Clean editorial design inspired by The Economist — structured, authoritative, minimal ornamentation
- Layout: Two distinct news cards stacked vertically per image (top card + bottom card), each card is a self-contained news summary
- Cards: White/light gray (#FAFAFA or #F5F5F5) rectangular cards with very subtle soft shadow (blur 8-12px, rgba(0,0,0,0.04)) to lift off background
- Card spacing: Generous 40-50px gap between the two cards, equal margins on all sides
- Background: Clean off-white (#F8F7F5) or very light warm gray, NO patterns, NO grids, NO decorative elements
- Typography (CRITICAL — editorial restraint):
  * Headlines: Bold serif-like weight (simulating Economist's custom font), dark charcoal (#2C2C2C), max 12-15 characters per headline
  * Sub-headlines/Metrics: Medium weight sans-serif, slightly smaller, muted gray (#5A5A5A) — for numbers, data points, or single-sentence summaries
  * Max 2 lines of text per card (headline + 1 data point), absolutely NO paragraphs or prose
  * All text left-aligned within cards, generous line spacing
- Color: Restrained palette — white cards, dark charcoal text, ONE subtle accent color for small highlights (muted burgundy #8B4557 or deep navy #2E4A62, NOT bright red/blue)
- Borders: Very subtle 1px light gray (#E5E5E5) card borders, optional — cards can also float without visible borders using shadow only
- Icons (optional, minimal): Tiny geometric icons (6-8px) next to metrics — arrow trends, small dots, or simple shapes — monochromatic gray (#8A8A8A)
- AVOID: Illustrations, diagrams, flowcharts, photos, gradients, decorative shapes, multiple colors, mind maps, bullet lists, more than 2 lines per card, body paragraphs
- LAYOUT: Each card fills ~45% of vertical space, total two cards = 90% height with 10% margins. Horizontal margins 8-10%. Content breathes.
- NEVER render typography specifications, font sizes, weight numbers, or revision markers as visible text in the image
- NEVER use dark fills, dark backgrounds, or dark cards anywhere — ALL surfaces MUST be white or very light gray
- ALL rendered text MUST be in Simplified Chinese (简体中文). Traditional Chinese characters (繁體字) are ABSOLUTELY FORBIDDEN.
- All images in this series MUST look like they came from the same premium editorial news app
"""
    else:
        return get_style_identity('tech')


import argparse
import os
import sys
import re
import subprocess
import yaml
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# Load Gemini API keys from env var (comma-separated) with fallback
_keys_str = os.environ.get("GEMINI_API_KEYS", "")
if not _keys_str:
    _single = os.environ.get("GEMINI_API_KEY", "")
    _keys_str = _single
API_KEYS = [k.strip() for k in _keys_str.split(",") if k.strip()]
if not API_KEYS:
    print("❌ No Gemini API keys found. Set GEMINI_API_KEYS (comma-separated) or GEMINI_API_KEY in .env", file=sys.stderr)
    sys.exit(1)

# Look for nano-banana-pro in sibling skill directory
_nano_paths = [
    Path(__file__).resolve().parent.parent.parent / "nano-banana-pro" / "scripts" / "generate_image.py",
    Path.home() / "gegeewu-skills/.claude/skills/nano-banana-pro/scripts/generate_image.py",
]
NANO_SCRIPT = None
for _i, p in enumerate(_nano_paths):
    if p.exists():
        NANO_SCRIPT = str(p)
        if _i == 0:
            print(f"📍 generate_image.py: {p}")
        else:
            print(f"⚠️  generate_image.py fallback to: {p} (gegeewu-post copy not found)", file=sys.stderr)
        break
if not NANO_SCRIPT:
    print("❌ nano-banana-pro 脚本入口未找到（路径缺失）", file=sys.stderr)
    print("   已检查路径:", file=sys.stderr)
    for p in _nano_paths:
        print(f"   - {p}", file=sys.stderr)
    print("   这类错误表示本地脚本不存在，不是 API 调用失败。", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="小红书图片生成引擎")
    parser.add_argument("markdown_file", help="Markdown 文件路径")
    parser.add_argument("--num-images", type=int, default=1, 
                       help="图片数量（1-9，默认1）")
    parser.add_argument("--output-dir", default=".", help="输出目录")
    parser.add_argument("--style", default="tech",
                       choices=["tech", "interview", "product", "philosophy", "digest"],
                       help="文档风格（默认 tech）")
    parser.add_argument("--task-id", default=None,
                       help="任务唯一标识（默认：时间戳_xhs）")
    parser.add_argument("--skip-cover", action="store_true",
                       help="跳过首图生成，仅生成分图（适用于汇总/日报类内容）")
    parser.add_argument("--sources-file", default=None,
                       help="per-item sources JSON 文件路径（digest 风格用，覆盖来源标签）")
    
    args = parser.parse_args()
    
    # 生成 task_id（如果未提供）
    if args.task_id is None:
        timestamp = int(time.time())
        args.task_id = f"{timestamp}_xhs"
    
    # 验证参数
    if not 1 <= args.num_images <= 9:
        print("❌ 图片数量必须在 1-9 之间", file=sys.stderr)
        sys.exit(1)
    
    md_file = Path(args.markdown_file)
    if not md_file.exists():
        print(f"❌ 文件不存在: {md_file}", file=sys.stderr)
        sys.exit(1)

    # 统一风格来源：front matter 优先，其次命令行参数。
    # 这可避免 style:digest 文档在未显式传 --style digest 时误走 Gemini 分支。
    metadata, _ = parse_markdown_frontmatter(md_file)
    effective_style = metadata.get('style', args.style)
    print(f"🎨 使用风格: {effective_style} (front matter 优先)")
    
    # 生成 prompts（动态）
    print(f"📝 生成 {args.num_images} 张图片的 prompts...\n")
    prompts = generate_prompts(md_file, args.num_images, effective_style, skip_cover=args.skip_cover)

    
    # 分批并发生成图片（每批3张）
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    task_id = args.task_id

    # digest 风格：使用本地 PIL 渲染器（非 Gemini）
    if effective_style == "digest":
        from digest_card_renderer import render_digest_image
        import re, json as _json
        with open(md_file, "r", encoding="utf-8") as f:
            md_content = f.read()
        body = re.sub(r"^---\n.*?---\n", "", md_content, count=1, flags=re.DOTALL)

        # 读取 per-item sources（优先 --sources-file，否则自动找同名 sidecar）
        per_item_sources = None
        sources_candidates = []
        if args.sources_file:
            sources_candidates.append(Path(args.sources_file))
        # auto-detect: md_file 同目录下的 .sources.json 或 payload 的 agent_output sidecar
        for ext in [".sources.json"]:
            sources_candidates.append(md_file.with_suffix(ext))
        for sc in sources_candidates:
            if sc.exists():
                try:
                    raw = _json.loads(sc.read_text(encoding="utf-8"))
                    if isinstance(raw, list) and any(raw):
                        per_item_sources = [s for s in raw if s]
                        print(f"  ↳ sources: {sc.name} ({len(per_item_sources)} 条)")
                        break
                except Exception:
                    pass

        items = extract_digest_items(body, per_item_sources=per_item_sources)
        pairs = [items[i:i+2] for i in range(0, len(items), 2)][:args.num_images]
        for idx, pair in enumerate(pairs):
            out_path = output_dir / f"{task_id}_image_{idx+1}.jpg"
            render_digest_image(pair, str(out_path))
        print(f"\n✅ digest 风格图片生成完成: {len(pairs)} 张")
        return

    
    BATCH_SIZE = min(len(API_KEYS), 6)
    total_images = len(prompts)
    failed_images = []
    api_key_idx = 0  # API key 轮换索引
    
    print(f"\n📸 开始生成 {total_images} 张图片（分批并发，每批{BATCH_SIZE}张）...")
    
    for batch_start in range(0, total_images, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total_images)
        batch_num = batch_start // BATCH_SIZE + 1
        batch_prompts = prompts[batch_start:batch_end]
        
        print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"  批次 {batch_num}（图片 {batch_start+1}-{batch_end} / {total_images}）")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        # 并发生成当前批次的图片
        with ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
            futures = {}
            
            for i, prompt in enumerate(batch_prompts, start=batch_start+1):
                if i == 1 and not args.skip_cover:
                    img_type = "封面"
                    filename = output_dir / f"{task_id}_cover.png"
                else:
                    img_num = i if args.skip_cover else i - 1
                    img_type = f"分图{img_num}"
                    filename = output_dir / f"{task_id}_image_{img_num}.png"
                
                # 获取当前 API key 并轮换
                current_api_key = API_KEYS[api_key_idx % len(API_KEYS)]
                api_key_idx += 1
                
                future = executor.submit(
                    call_nano_banana_pro, 
                    prompt, 
                    str(filename), 
                    current_api_key,
                    timeout=120
                )
                futures[future] = (i, img_type, filename)
            
            # 等待当前批次完成
            for future in as_completed(futures):
                i, img_type, filename = futures[future]
                try:
                    result = future.result()
                    if result.get("success"):
                        print(f"  ✓ [{i}/{total_images}] {img_type} 生成成功")
                    else:
                        print(f"  ✗ [{i}/{total_images}] {img_type} 生成失败: {result.get('error', '未知错误')}")
                        failed_images.append((i, img_type, filename))
                except Exception as e:
                    print(f"  ✗ [{i}/{total_images}] {img_type} 异常: {e}")
                    failed_images.append((i, img_type, filename))
    
    # 检查失败情况
    if failed_images:
        print(f"\n✗ {len(failed_images)} 张图片生成失败:")
        for i, img_type, filename in failed_images:
            print(f"  - [{i}] {img_type}: {filename}")
        sys.exit(1)
    
    print(f"\n✅ 所有图片生成成功（{total_images} 张）")

    # 压缩：PNG → JPEG 90%（macOS sips，无需安装依赖）
    print("\n🗜️ 压缩图片（PNG → JPEG 90%）...")
    import subprocess as _sp
    compressed_paths = []
    for i in range(1, total_images + 1):
        if i == 1 and not args.skip_cover:
            png_path = output_dir / f"{task_id}_cover.png"
            jpg_path = output_dir / f"{task_id}_cover.jpg"
        else:
            img_num = i if args.skip_cover else i - 1
            png_path = output_dir / f"{task_id}_image_{img_num}.png"
            jpg_path = output_dir / f"{task_id}_image_{img_num}.jpg"

        if png_path.exists():
            r = _sp.run(
                ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "90",
                 str(png_path), "--out", str(jpg_path)],
                capture_output=True
            )
            if r.returncode == 0 and jpg_path.exists():
                orig_size = png_path.stat().st_size
                new_size = jpg_path.stat().st_size
                print(f"  ✓ {png_path.name} → {jpg_path.name}  "
                      f"{orig_size//1024}KB → {new_size//1024}KB")
                png_path.unlink()  # 删除原 PNG
                compressed_paths.append(jpg_path)
            else:
                print(f"  ⚠ 压缩失败，保留原 PNG: {png_path.name}")
                compressed_paths.append(png_path)
        else:
            compressed_paths.append(jpg_path if jpg_path.exists() else png_path)

    # 输出 task_id（供后续流程使用）
    print(f"\n📝 TASK_ID: {task_id}")

    # 输出图片路径（供调用方使用）
    print("\n生成的图片路径:")
    for p in compressed_paths:
        print(p)


def parse_markdown_frontmatter(md_file):
    """解析 Markdown front matter"""
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if not content.startswith('---'):
        return {}, content
    
    parts = content.split('---', 2)
    if len(parts) < 3:
        return {}, content
    
    metadata = yaml.safe_load(parts[1])
    body = parts[2].strip()
    
    return metadata, body


def generate_prompts(markdown_file, num_images, doc_style, skip_cover=False):
    """
    生成所有图片的 prompts（完全动态）
    
    返回：
      [cover_prompt, detail_prompt_1, detail_prompt_2, ...]
      或 skip_cover=True 时：
      [detail_prompt_1, detail_prompt_2, ...]
    """
    metadata, body = parse_markdown_frontmatter(markdown_file)
    
    # 从 front matter 读取风格（优先级高于命令行参数）
    doc_style = metadata.get('style', doc_style)
    
    title = metadata.get('title', '小红书笔记')
    emoji = metadata.get('emoji', '✨')
    
    prompts = []
    
    # digest 风格：强制跳过封面，特殊处理（1图=2条，最多9图=18条）
    if doc_style == 'digest':
        skip_cover = True  # 强制不生成首图

        items = extract_digest_items(body, max_items=18)
        if not items:
            print("⚠️  digest 风格但未提取到新闻条目，返回空 prompts")
            return []

        # 按请求图数限制（最多9张）
        max_pairs = min(max(1, num_images), 9)
        items = items[:max_pairs * 2]

        paired_sections = []
        for i in range(0, len(items), 2):
            pair = items[i:i+2]
            facts1 = ' / '.join(pair[0].get('key_facts') or ['核心要点'])
            section_text = f"CARD 1:\n标题：{pair[0]['headline']}\n要点：{facts1}\n\n"
            if len(pair) > 1:
                facts2 = ' / '.join(pair[1].get('key_facts') or ['核心要点'])
                section_text += f"CARD 2:\n标题：{pair[1]['headline']}\n要点：{facts2}"
            paired_sections.append(section_text)

        print(f"  digest 风格：提取 {len(items)} 条新闻，生成 {len(paired_sections)} 张图（每图2条，最多9张）")

        for i, section_text in enumerate(paired_sections, 1):
            detail_prompt = generate_detail_prompt(
                section_body=section_text,
                index=i,
                doc_style='digest',
                title=title
            )
            prompts.append(detail_prompt)

        return prompts
    
    if skip_cover:
        # 汇总/日报内容：跳过封面，全部生成分图
        # 先切分正文为 N 份，每份对应一张分图
        body_sections = split_body_for_sections(body, num_images)
        for i, section_body in enumerate(body_sections, 1):
            detail_prompt = generate_detail_prompt(
                section_body=section_body,
                index=i,
                doc_style=doc_style,
                title=title
            )
            prompts.append(detail_prompt)
    else:
        # 正常叙事内容：1张封面 + (num_images-1)张分图
        cover_prompt = generate_cover_prompt(title, emoji, doc_style, body)
        prompts.append(cover_prompt)
        if num_images > 1:
            # 切分正文为 (num_images-1) 份，每份对应一张分图
            body_sections = split_body_for_sections(body, num_images - 1)
            for i, section_body in enumerate(body_sections, 1):
                detail_prompt = generate_detail_prompt(
                    section_body=section_body,
                    index=i,
                    doc_style=doc_style,
                    title=title
                )
                prompts.append(detail_prompt)
    
    return prompts


def generate_cover_prompt(title, emoji, doc_style, body=""):
    """生成首图 prompt（基于风格和文档内容）
    
    Args:
        title: 标题
        emoji: emoji
        doc_style: 文档风格
        body: 文档正文内容（完整传入，让AI自己提取架构）
    """
    
    # 获取风格视觉标识
    STYLE_PREFIX = get_style_identity(doc_style)
    
    # 直接传入完整body，让AI自己提取关键架构信息（类似分图机制）
    content_context = ""
    if body:
        # tech 风格封面只需要少量内容提取架构结构，其他风格需要更多内容感受情绪
        _limit = 600 if doc_style == 'tech' else 1500
        body_preview = body[:_limit] if len(body) > _limit else body
        content_context = f"\n\n**文档内容摘要（提取架构信息）**:\n{body_preview}\n"
    
    if doc_style == 'tech':
        prompt = f"""SERIES ANCHOR: This is the COVER of a multi-image series. All detail images that follow MUST share the EXACT same visual DNA: dot-grid background, card style, color palette (grayscale + #4A90D9 only), typography, shadow style.

Create a technical architecture diagram for a 3:4 vertical cover image.

GOAL: Fully present the complete system architecture from the document content.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ REQUIRED (Boundaries):

1. **Document Fidelity (CRITICAL)**: Show ONLY modules/components explicitly mentioned in the document
   - Do NOT invent or add modules not in the document
   - Do NOT extrapolate or assume additional architecture layers
   - If document mentions "三层缓存", show exactly 3 cache layers (not 5)
   - If document mentions "MySQL + Redis", show exactly MySQL + Redis (don't add MongoDB)
   - **Completeness = Show all mentioned components, NO MORE**

2. **Chinese Labels**: All module names, layer labels, and annotations in Chinese
   - Use exact terminology from the document
   - Examples: "数据库", "缓存层", "API网关", "前端UI", "业务逻辑"

3. **Flow Connectors**: Use **thin lines with small rounded dots** for connections, NOT arrows
   - Thin (1-2px), soft lines with small circular endpoints (·—·)
   - Keep dots subtle - don't compress node visuals
   - Avoid thick lines that dominate the diagram
   - Avoid sharp arrow heads (→) - too rigid

4. **Image Ratio**: 3:4 vertical (适合小红书)

5. **NO Watermark**: Do NOT include "by geegewu" or any watermark in the image

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ FORBIDDEN (Constraints — image rejected if violated):

- ANY color outside the palette (grayscale + #4A90D9) — red, green, orange, purple, teal, yellow, pink = REJECTED
- Using different colors to distinguish modules — use shape differences (solid vs dashed, square vs circle) instead
- NO article paragraphs or full sentences
- NO bullet point lists from document content
- NO code snippets or screenshots
- NO photographic elements
- NO simplifying architecture because "too many modules"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎨 STYLE:

Follow the SERIES VISUAL IDENTITY defined above EXACTLY — same colors, same depth, same background.
This cover MUST be visually indistinguishable in style from the detail slides that follow.
- Off-white background with dot grid and gentle radial vignette
- Grayscale modules with muted blue (#4A90D9) accent only
- Primary cards: white fill with shadow rgba(0,0,0,0.06) ONLY — NO colored or tinted shadows
- Secondary cards: light gray fill (#F0F0F0) without shadow (receded layer)
- 3 depth layers: background → secondary cards → primary cards with shadow
- Thin gray strokes for borders, connectors with small rounded dot endpoints

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{content_context}

🧠 YOUR DECISIONS (Auto-determine from document):

- How many modules to show (could be 3, 5, 8, 12+)
- Layout structure (layered? grid? flowchart? hybrid?)
- Whether to show a title (and where)
- Connection styles (arrows? lines? both?)
- Visual hierarchy (which components are primary/secondary)
- Icon usage (database cylinders, server boxes, cloud shapes - if helpful)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FINAL CHECK:
- [ ] All core modules from document are shown
- [ ] All labels in Chinese
- [ ] Architecture is complete and clear
- [ ] No article text rendered"""
        return STYLE_PREFIX + "\n\n" + prompt

    elif doc_style == 'interview':
        prompt = f"""Create a New Yorker-style editorial cover illustration (3:4 vertical).

GOAL: A single, evocative painted illustration that captures the central theme or mood of the article — NOT a diagram, NOT a mind map, NOT a flow chart.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ REQUIRED:

1. **Single Scene Illustration**: One coherent painted scene — a moment, a metaphor, a mood
   - Read the document and identify the central image, metaphor, or emotional core
   - Illustrate THAT — not a summary of all topics
   - Think: "What would a New Yorker illustrator paint for this article?"

2. **Watercolor + Gouache Medium**: This is a PAINTED illustration, not vector art
   - Visible brushstrokes, gouache opacity, watercolor wash undertones
   - Paint edges are soft, slightly uneven — NOT hard vector outlines
   - Layered paint: transparent watercolor wash beneath opaque gouache details

3. **Minimal Text**: At most a short title or one key phrase, hand-lettered in serif
   - If title is included, integrate it into the composition naturally
   - Do NOT render article body text or topic labels

4. **Image Ratio**: 3:4 vertical (适合小红书)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ FORBIDDEN:

- NO mind maps, flow charts, bubble diagrams, or topic node layouts
- NO infographic elements (arrows, percentage circles, lists)
- NO speech bubbles or conversation thread visuals
- NO corporate illustration style (flat Memphis, Notion-style)
- NO photographic realism
- NO multiple disconnected scenes

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎨 STYLE:

Follow the SERIES VISUAL IDENTITY defined above EXACTLY.
- Medium: gouache and watercolor on textured paper — paint is the primary language
- Background: aged cream paper (#F7F2E8) with visible fiber grain
- Ink outlines: expressive brush pen — varying pressure, natural imperfection
- Color washes: transparent layers, wet-on-wet bleeding at edges
- Gouache highlights: near-white strokes on focal areas for painted depth
- Palette: warm ivory, dusty blush, sage grey-green, muted cobalt, terra cotta — max 4 colors
- Mood: quiet, thoughtful, slightly melancholic — like a cover painting you want to look at twice

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Article content for illustration inspiration:
{content_context}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FINAL CHECK:
- [ ] Single painted scene, NOT a diagram
- [ ] Watercolor + gouache medium is visible
- [ ] Central metaphor or mood of the article is captured
- [ ] No mind maps, topic nodes, or flow charts"""
        return STYLE_PREFIX + "\n\n" + prompt

    elif doc_style == 'philosophy':
        prompt = f"""Create a classical ukiyo-e woodblock print illustration — a life scene, melancholic and beautiful (3:4 vertical).

GOAL: A single evocative ukiyo-e scene that captures the emotional core of the article through the visual language of classical Japanese woodblock prints — NOT a poster, NOT a diagram, NOT graphic design.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ REQUIRED:

1. **Life Scene — Read the article and find its emotional core**:
   - Translate the central metaphor into a ukiyo-e scene
   - Example for this article: a solitary figure at a glowing screen in a dark room, an owl perched on a server tower beneath a full moon, or a lone person standing on a bridge looking at city reflections — rendered in Hiroshige's style
   - The scene should feel timeless yet quietly modern

2. **Classical Ukiyo-e Composition**:
   - Strong diagonal — figure or object in foreground, vast atmosphere behind
   - Sky/moonlight/water occupying upper two-thirds; grounded life below
   - Asymmetric balance, never perfectly centered
   - Sense of depth through overlapping planes (Hiroshige's layered distance)

3. **Authentic Woodblock Colors**:
   - Hiroshige blue (#2E6FA3) for sky/atmosphere
   - Vermilion (#C0392B) for focal accent (lantern, screen glow, bird)
   - Aged ivory (#F5EDD6) for paper/moonlight/mist
   - Ochre (#C4922A) for warmth
   - Ink black for outlines
   - Max 5 colors, flat woodblock fills with ink grain texture

4. **Emotional Quality**: Wistful, melancholic, quietly beautiful — the loneliness of someone who lives between two worlds (human and machine, past and future)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ FORBIDDEN:

- NO geometric poster layouts, NO flat vector graphic design
- NO diagrams, mind maps, or infographic elements
- NO anime or manga style
- NO modern corporate illustration
- NO text blocks or labels in the scene
- NO circuit patterns, PCB traces, or tech textures overlaid on natural elements (water, mountains, trees, sky, ground) — technology must appear ONLY as distinct physical objects (server rack, laptop screen, LED, cables), never merged with or embedded in scenery

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎨 STYLE:

Follow the SERIES VISUAL IDENTITY exactly — woodblock ink on washi, layered flat color with ink grain, graceful outline variation.

Article content for scene inspiration:
{content_context}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FINAL CHECK:
- [ ] Single unified life scene — NOT a collage or poster
- [ ] Classical ukiyo-e composition (diagonal, atmospheric depth)
- [ ] Emotional quality: melancholic, wistful, beautiful
- [ ] Woodblock print aesthetic unmistakable"""
        return STYLE_PREFIX + "\n\n" + prompt

    elif doc_style == 'product':
        prompt = f"""Create a product feature visualization for a 3:4 vertical cover image.

GOAL: Fully present ALL core features/highlights from the document content.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ REQUIRED (Boundaries):

1. **Document Extraction (MANDATORY)**: Extract feature names DIRECTLY from document text
   - Read the document carefully and identify explicit features/highlights
   - Use EXACT wording from document (e.g., if doc says "空间管理 Space", show "空间管理")
   - Do NOT invent generic labels like "高速/安全/易用" unless document explicitly mentions them
   - If document says "内存优化 8.2G→3.1G", show "内存优化" (or even "8G→3G" if space allows)
   - If document says "分屏功能", show "分屏" not "高效"

2. **Complete Features**: Show ALL core features or highlights mentioned in the document
   - Do NOT omit features for "aesthetics"
   - Completeness > Visual simplicity

3. **Chinese Labels**: Feature names in Chinese (short, 2-4 characters preferred, exact document terms)
   - ✅ GOOD: "内存优化", "空间管理", "自动归档", "分屏", "全能搜索" (from document)
   - ❌ BAD: "高速", "安全", "易用", "智能", "同步", "私密" (generic, not from document)

4. **Visual Connectors** (if needed): Use **thin lines with small rounded dots**, NOT arrows
   - Thin (1-2px) smooth connections with small circular endpoints
   - Keep dots subtle - don't compress card visuals
   - Avoid sharp arrow heads

5. **Image Ratio**: 3:4 vertical (适合小红书)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ FORBIDDEN (Constraints):

- NO feature descriptions or full sentences
- NO bullet point lists from document
- NO "Pros/Cons" text blocks
- NO detailed specifications text
- NO simplifying feature list because "too many cards"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎨 STYLE:

Follow the SERIES VISUAL IDENTITY defined above EXACTLY — same colors, same depth, same background.
This cover MUST be visually indistinguishable in style from the detail slides that follow.
- Light warm gray background (#FAFAFA) with subtle center glow for visual focus
- Feature cards: solid fills from Memphis palette with soft shadow (blur 12-16px, rgba(0,0,0,0.06)) for floating feel
- Colors: coral (#FF8A80), teal (#4DB6AC), mustard (#FFD54F), lavender (#B39DDB)
- Optional subtle single-direction gradient within cards (max 10% shift) for gentle dimension
- Bold white text/icons on colored cards, dark charcoal (#37474F) text on white background
- Floating decorative shapes at 30-50% opacity (receded layer, behind cards)
- Geometric rounded shapes, abstract Memphis-style illustrations

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🧠 YOUR DECISIONS (Auto-determine from document):

- How many feature cards to show (could be 3, 4, 6, 8, 10+)
- Grid layout (2x2? 3x2? 4x2? 3x3?)
- Whether to show a title (and where)
- Icon styles (line-style, filled, or minimal)
  * Common icons: lightning (speed), shield (security), gear (customize), 
    chart (analytics), cloud (sync), lock (privacy), check (simple), star (quality)
- Card styles (rounded rectangles with shadows? flat? outlined?)
- Optional: number badges (1, 2, 3...) on cards

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FINAL CHECK:
- [ ] All core features from document are shown
- [ ] Feature labels use EXACT terms from document (not generic replacements like "高速/安全")
- [ ] All labels in Chinese (short, 2-4 chars preferred, exact document terms)
- [ ] Feature list is complete and clear
- [ ] If document has specific data (e.g., "60标签页", "8G→3G"), consider showing them
- [ ] No feature descriptions rendered (icons + labels only)"""
        return STYLE_PREFIX + "\n\n" + prompt

    else:
        # 默认回退为简化的 tech 风格
        prompt = f"""Create a clean architecture-style cover image (3:4 vertical ratio):

Subject: "{title} {emoji}"

LAYOUT:
- Top: Title + emoji
- Middle: 3-4 simple module boxes with thin lines + small dots showing flow

VISUAL:
- Module boxes: rectangles with short labels
- Connectors: thin lines (1-2px) + small rounded dots (·—·)
- Colors: Blue→Teal, Purple→Violet, Green→Lime gradients
- Text: **Bold weight**, deep black
- Background: white

FORBIDDEN:
- NO paragraphs or article text
- NO lists or full sentences
- NO watermark

REQUIRED:
- [ ] Simple architecture diagram (3-4 modules)
- [ ] Thin lines + small dots connectors
- [ ] Bold text for readability

Style: AWS/Azure architecture diagram."""
        return STYLE_PREFIX + "\n\n" + prompt


def extract_digest_items(body, max_items=18, source_hint=None, per_item_sources=None):
    """从日报正文提炼新闻条目（结构化摘要，非散文），最多 max_items 条。

    提取策略：
    0. ━━━━━━━ 分隔符格式（最高优先级）：新简化格式，每段第一行=emoji+标题，剩余=摘要
    1. Telegram 3-line 格式：🔹 source / **title** / summary
    2. 优先匹配 ### 开头的三级标题条目（最常见的新闻格式）
    3. 如果没有 ###，尝试按 --- 分隔符切分

    per_item_sources: list[str]，与 items 一一对应；优先级高于 source_hint
    """
    if not body or not body.strip():
        return []

    # 策略0：━━━━━━━ 分隔符格式（新简化流程）
    # 格式：emoji + 标题（第一行）
    #       2-4句叙述（剩余行）
    #       ━━━━━━━━━━━━━━━（分隔符）
    if '━━━━━━' in body:
        segments = re.split(r'\n━━━━━━━+\n', body.strip())
        items = []
        for i, seg in enumerate(segments):
            lines = [l.strip() for l in seg.strip().split('\n') if l.strip()]
            if len(lines) >= 2:
                headline = lines[0]  # emoji + 标题
                # 移除开头的 emoji（避免字体不支持导致显示为正方形框）
                headline = re.sub(r'^[^\w\s]+\s*', '', headline)
                summary = ' '.join(lines[1:])  # full body; card renderer handles line cap
                # source 优先级：per_item_sources[i] > source_hint > fallback
                if per_item_sources and i < len(per_item_sources) and per_item_sources[i]:
                    source = per_item_sources[i]
                else:
                    source = source_hint or "blog.com"
                items.append({
                    "headline": headline,
                    "source": source,
                    "category": "",
                    "summary": summary
                })
        if len(items) >= 2:
            return items[:max_items]

    # 策略1：优先提取 ### 开头的条目（新闻条目标准格式）
    # 匹配 ### 开头，直到下一个 ### 或文件结束
    h3_pattern = r'\n###\s+(.+?)(?=\n###\s+|\Z)'
    h3_matches = re.findall(h3_pattern, '\n' + body, re.DOTALL)
    
    raw_items = []
    if len(h3_matches) >= 2:  # 至少2条才算有新闻
        for m in h3_matches:
            # 提取标题（### 后的第一行）
            lines = [l.strip() for l in m.split('\n') if l.strip()]
            if lines:
                raw_items.append(m.strip())
    
    # 策略2：如果 ### 不足，按 --- 分隔符切分
    if len(raw_items) < 2 and '---' in body:
        parts = re.split(r'\n---\n', body)
        raw_items = [p.strip() for p in parts if p.strip() and len(p.strip()) > 50]
    
    # 策略3：按 ## 二级标题切分
    if len(raw_items) < 2:
        h2_chunks = re.split(r'\n##\s+', '\n' + body)
        raw_items = [c.strip() for c in h2_chunks if c.strip() and len(c.strip()) > 50]

    items = []
    for item in raw_items[:max_items]:
        lines = [l.strip() for l in item.split('\n') if l.strip()]
        if not lines:
            continue

        # 标题：第一行，清理 markdown 和序号
        headline = re.sub(r'^#{1,6}\s*', '', lines[0]).strip()
        headline = re.sub(r'^\d+\.\s*', '', headline).strip()
        # 清理 markdown 链接 [text](url) → text（blog-digest 格式）
        headline = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', headline).strip()

        # 来源：从 **来源**: @xxx (name) 提取 @xxx (name)
        source = ''
        source_match = re.search(r'\*\*来源\*\*[:：]\s*(@\S+\s*\([^)]+\))', item)
        if source_match:
            source = source_match.group(1).strip()
        else:
            # blog-digest 格式：**来源**: site.com | **发布**: date → 只取域名
            blog_src = re.search(r'\*\*来源\*\*[:：]\s*([^\s\|*\n]+)', item)
            if blog_src:
                source = blog_src.group(1).strip()
            else:
                # fallback: 找 @account
                acc = re.search(r'(@\w+(?:\s*[\(（][^)）]+[\)）])?)', item)
                if acc:
                    source = acc.group(1).strip()

        # 分类：从 **分类**: 🔥 AI Agent / xxx 提取（去掉 emoji 和多余符号）
        category = ''
        cat_match = re.search(r'\*\*分类\*\*[:：]\s*[^\w]*([\w\s/\-·]+)', item)
        if cat_match:
            category = cat_match.group(1).strip().rstrip('·\n-').strip()
            # 只取第一段（遇到换行截断）
            category = category.split('\n')[0].strip()

        # 摘要：优先取 **核心观点** / **要点** 行，其次取首个 > 引用句，最后取首个非元数据行
        summary = ''
        # 1) 核心观点字段
        kp = re.search(r'\*\*(?:核心观点|要点|摘要)\*\*[:：]\s*(.+)', item)
        if kp:
            summary = kp.group(1).strip()[:80]
        # 2) 第一个 > 引用行（非 URL、非空）
        if not summary:
            for line in lines:
                if line.startswith('>'):
                    s = line.lstrip('> ').strip()
                    if len(s) > 10 and 'http' not in s:
                        summary = s[:80]
                        break
        # 3) 第一个有实质内容的非元数据行
        if not summary:
            skip_prefixes = ('**来源', '**评分', '**互动', '**分类', '**原文', 'http', '>', '#', '-')
            for line in lines[1:]:
                clean = re.sub(r'\*\*[^*]+\*\*[:：]\s*', '', line).strip()
                clean = re.sub(r'\*', '', clean).strip()
                if len(clean) > 15 and not any(clean.startswith(p) for p in skip_prefixes):
                    summary = clean[:80]
                    break

        items.append({
            "headline": headline,
            "source": source,
            "category": category,
            "summary": summary,
        })

    return items


def split_body_for_sections(body, num_sections):
    """
    将正文机械切分成 N 份，用于分图生成（解决内容重叠问题）
    
    切分逻辑（按优先级）：
    1. 如果正文包含 `---` 分隔符 → 按 `---` 切分各段
    2. 如果正文包含 `## ` 标题 → 按二级标题切分
    3. 否则 → 按段落数量均分（`\n\n` 分段）
    
    返回：
      [section_body_1, section_body_2, ...]  # 长度 = num_sections
    """
    if not body or not body.strip():
        return [""] * num_sections
    
    # 优先级1：按 --- 分隔符切分
    if "---" in body:
        parts = [p.strip() for p in body.split("---") if p.strip()]
        if len(parts) >= num_sections:
            return parts[:num_sections]
    
    # 优先级2：按 ## 二级标题切分
    # 使用正则表达式匹配 ## 开头的段落
    h2_matches = list(re.finditer(r'\n##\s+', '\n' + body))
    if len(h2_matches) >= num_sections:
        sections = []
        for i in range(num_sections):
            start = h2_matches[i].start()
            if i + 1 < num_sections:
                end = h2_matches[i + 1].start()
            else:
                end = len(body)
            section = body[start:end].strip()
            sections.append(section)
        return sections
    
    # 优先级3：按段落数量均分
    paragraphs = [p.strip() for p in re.split(r'\n\n+', body) if p.strip()]
    if not paragraphs:
        return [body] * num_sections
    
    # 计算每份应该包含的段落数
    total_paras = len(paragraphs)
    base_size = total_paras // num_sections
    remainder = total_paras % num_sections
    
    sections = []
    start_idx = 0
    for i in range(num_sections):
        # 前 remainder 个section多分一个段落
        size = base_size + (1 if i < remainder else 0)
        end_idx = start_idx + size
        chunk_paras = paragraphs[start_idx:end_idx]
        section_text = '\n\n'.join(chunk_paras)
        sections.append(section_text)
        start_idx = end_idx
    
    return sections


def extract_sections(markdown_body, num_sections):
    """
    从 markdown 自动拆分为 N 个关键部分
    
    策略（优先级）：
      1. 按 ## 二级标题拆分
      2. 按 ### 三级标题拆分
      3. 按段落均分
    
    返回：
      [
        {"title": "...", "content": "...", "keywords": [...]},
        ...
      ]
    """
    
    # 策略 1：按 ## 标题拆分
    h2_pattern = r'## (.+?)(?=\n##|\Z)'
    matches = re.findall(h2_pattern, '\n' + markdown_body, re.DOTALL)
    
    if len(matches) >= num_sections:
        sections = matches[:num_sections]
        return [_parse_section(s) for s in sections]
    
    # 策略 2：按 ### 标题拆分
    h3_pattern = r'### (.+?)(?=\n###|\Z)'
    matches = re.findall(h3_pattern, '\n' + markdown_body, re.DOTALL)
    
    if len(matches) >= num_sections:
        sections = matches[:num_sections]
        return [_parse_section(s) for s in sections]
    
    # 策略 3：按段落均分
    paragraphs = [p.strip() for p in re.split(r'\n\n+', markdown_body) if p.strip()]
    
    if not paragraphs:
        # 回退：整个 body 作为一个部分
        return [_parse_section(markdown_body)] * num_sections
    
    chunk_size = max(1, len(paragraphs) // num_sections)
    
    result = []
    for i in range(num_sections):
        start = i * chunk_size
        end = min(start + chunk_size, len(paragraphs))
        chunk_text = '\n\n'.join(paragraphs[start:end])
        result.append(_parse_section(chunk_text))
    
    return result


def _parse_section(text):
    """
    解析单个部分，提取标题、内容、关键词
    
    返回：
      {"title": "...", "content": "...", "keywords": [...]}
    """
    # 提取标题（第一行）
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    title = lines[0] if lines else "要点"
    
    # 清理 markdown 标记
    clean = text
    clean = re.sub(r'```[\s\S]*?```', '', clean)  # 代码块
    clean = re.sub(r'[#*_`]', '', clean)  # markdown 符号
    
    # 提取内容（前 200 字）
    content = clean[:200].strip()
    
    # 提取关键词（自动）
    keywords = []
    
    # 1. 提取加粗词
    bold_words = re.findall(r'\*\*([^*]+)\*\*', text)
    keywords.extend(bold_words[:3])
    
    # 2. 提取数字+单位
    numbers = re.findall(r'\d+\s*[倍次个张小时分钟秒%×xX]', text)
    keywords.extend(numbers[:3])
    
    # 3. 提取专有名词（首字母大写）
    proper_nouns = re.findall(r'\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b', text)
    keywords.extend(proper_nouns[:2])
    
    # 去重，最多5个
    keywords = list(dict.fromkeys(keywords))[:5]
    
    return {
        "title": title[:50],
        "content": content,
        "keywords": keywords
    }


def generate_detail_prompt(section_body, index, doc_style, title=""):
    """Generate detail slide prompt with style-consistent visual identity.
    
    Args:
        section_body: 切分后的正文段落（已确保各图内容不重叠）
        index: 分图序号（从1开始）
        doc_style: 文档风格
        title: 文档标题
    """
    # 复用 get_style_identity() 确保分图与封面视觉完全一致
    style_dna = get_style_identity(doc_style)
    
    # 从 section_body 提取标题（第一行）和关键词
    lines = [l.strip() for l in section_body.split('\n') if l.strip()]
    section_title = lines[0] if lines else "要点"
    
    # 清理 markdown 符号用于提取关键词
    clean_text = re.sub(r'```[\s\S]*?```', '', section_body)  # strip code blocks
    clean_text = re.sub(r'[#*_`]', '', clean_text)  # strip markdown symbols
    
    # 提取关键词
    keywords = []
    bold_words = re.findall(r'\*\*([^*]+)\*\*', section_body)
    keywords.extend(bold_words[:3])
    numbers = re.findall(r'\d+\s*[倍次个张小时分钟秒%×xX]', section_body)
    keywords.extend(numbers[:3])
    proper_nouns = re.findall(r'\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b', section_body)
    keywords.extend(proper_nouns[:2])
    keywords = list(dict.fromkeys(keywords))[:5]
    keywords_str = ", ".join(keywords) if keywords else "核心要点"
    
    # 提取上下文（用于 prompt 中的背景信息）
    background_context = clean_text[:500].strip()
    
    if doc_style == 'tech':
        prompt = f"""{style_dna}

SERIES ANCHOR: This is image {index} of a multi-image series. ALL images share the EXACT same: dot-grid background, card style (white fill + rgba(0,0,0,0.06) shadow), color palette (grayscale + #4A90D9 only), typography hierarchy, shadow style. The ONLY difference between images is the topic inside the content zone.

Create a UI wireframe detail diagram (3:4 vertical).

INFORMATION STRUCTURE (visualize as diagram, NOT as text):
Topic: "{section_title}"
Key concepts: {keywords_str}

NOTE: Use the identity palette SHAPES and ICONS to differentiate concepts (solid vs dashed border, circle vs square, filled vs outlined). NEVER use color to distinguish different items.

REQUIRED:
1. VISUAL INFOGRAPHIC ONLY — This MUST be a diagram, chart, or UI mockup. NEVER a document screenshot, text list, or webpage capture.
2. Detail view of "{section_title}" — show ALL sub-components using visual elements (boxes, icons, flows, charts)
3. ALL text labels in Simplified Chinese (简体中文) ONLY — 繁體字 ABSOLUTELY FORBIDDEN
4. Same wireframe aesthetic: thin gray strokes, dot-grid background, muted blue accent (#4A90D9)
5. ALL card fills: white (#FFFFFF) or light gray (#F0F0F0) — NO dark sections, NO dark cards anywhere
6. 3:4 vertical ratio, content fills 70-80% of canvas

ABSOLUTELY FORBIDDEN (image rejected if violated):
- ANY color outside the palette (grayscale + #4A90D9) — red, green, orange, purple, teal, yellow, pink = REJECTED
- Using different colors to distinguish items/tools/categories — use shape differences instead
- Document screenshots, webpage captures, or text-paragraph-only layouts
- Traditional Chinese characters (繁體字)
- "R8", "R10", corner-radius labels, or any design spec annotations as visible text
- Font size, pixel value, or weight number annotations visible in the image
- Dark background fills, dark card fills, or high-contrast dark sections
- Decorative gradient blobs, color fog effects, bokeh overlays, light leak effects, background color splashes
- Colored shadows — ALL shadows MUST be rgba(0,0,0,x) only, NO blue/purple/tinted shadows"""

    elif doc_style == 'interview':
        prompt = f"""{style_dna}

SERIES ANCHOR: This is image {index} of a multi-image series. ALL images share the EXACT same: painted medium (watercolor + gouache on textured paper), color palette (max 4 from identity), ink-line quality, paper texture. The ONLY difference is the scene/subject depicted.

Create a New Yorker-style editorial detail illustration (3:4 vertical). This is a PAINTED illustration, NOT a diagram.

Focus: "{section_title}"
Theme keywords: {keywords_str}

⚠️ SCOPE CONSTRAINT (CRITICAL): Visualize ONLY the content below. Do NOT reference or repeat any content outside this section. Each image in this series is completely self-contained.

Content to visualize (THIS section only):
{section_body[:800]}

REQUIRED:
1. A single painted scene or vignette that captures the emotion/insight of "{section_title}"
2. Watercolor + gouache medium — paint strokes visible, edges soft and organic
3. Same ink-line quality: brush pen with natural pressure variation
4. ALL text in Simplified Chinese (简体中文) ONLY
5. 3:4 vertical ratio
6. Generous breathing room — NOT crowded

FORBIDDEN: Mind maps, flow charts, bubble diagrams, digital gradients, flat fills, corporate illustration, harsh shadows, infographic elements, "R8"/"R10" markers, Traditional Chinese characters (繁體字), document screenshots or text-only layouts"""

    elif doc_style == 'product':
        prompt = f"""{style_dna}

SERIES ANCHOR: This is image {index} of a multi-image series. ALL images share the EXACT same: background (#FAFAFA), card style (Memphis palette + soft shadow), color set (coral/teal/mustard/lavender only), typography, rounded shapes. The ONLY difference is the feature topic.

Create a Corporate Memphis feature detail (3:4 vertical).

INFORMATION STRUCTURE (visualize as illustration, NOT as text):
Topic: "{section_title}"
Key concepts: {keywords_str}

NOTE: Use the Memphis palette shapes and icons to differentiate concepts. Stay within the 4-color accent palette.

REQUIRED:
1. Showcase "{section_title}" feature with Memphis-style flat illustration
2. ALL text labels in Simplified Chinese (简体中文) ONLY — 繁體字 ABSOLUTELY FORBIDDEN
3. Same flat vector aesthetic: solid fills, geometric shapes, pastel Memphis colors
4. ALL surfaces: white (#FAFAFA), light gray, or pastel Memphis colors — NO dark fills anywhere
5. 3:4 vertical ratio, content fills 70-80% of canvas

FORBIDDEN: Feature descriptions, realistic art, heavy multi-stop gradients, dark themes, dark card fills, harsh shadows, "R8"/"R10" markers, Traditional Chinese characters (繁體字), document screenshots or text-only layouts"""

    elif doc_style == 'philosophy':
        prompt = f"""{style_dna}

SERIES ANCHOR: This is image {index} of a multi-image series. ALL images share the EXACT same: washi paper texture, woodblock ink grain, 5-color ukiyo-e palette (Hiroshige blue, vermilion, aged ivory, ochre, ink black), classical composition style. The ONLY difference is the life scene depicted.

Create a classical ukiyo-e woodblock life scene (3:4 vertical) — melancholic and beautiful.

Focus: "{section_title}"
Core concepts: {keywords_str}

⚠️ SCOPE CONSTRAINT (CRITICAL): Visualize ONLY the content below. Do NOT reference or repeat any content outside this section. Each image in this series is completely self-contained.

Content to visualize (THIS section only):
{section_body[:800]}

REQUIRED:
1. A distinct ukiyo-e life scene that evokes the emotion of "{section_title}"
   - Each detail image explores a different moment or angle of the article's themes
   - Think: different scenes from the same world — a figure in rain, an owl watching a sleeping city, moonlight on wires
2. Classical woodblock composition: foreground figure/element, atmospheric background
3. Same authentic palette: Hiroshige blue, vermilion, aged ivory, ochre, ink black
4. ALL text in Simplified Chinese (简体中文) ONLY — 繁體字 ABSOLUTELY FORBIDDEN
5. 3:4 vertical ratio

FORBIDDEN: Geometric posters, flat vector graphic design, anime style, corporate illustration, diagrams, text labels, infographic elements, "R8"/"R10" markers, Traditional Chinese characters (繁體字), document screenshots or text-only layouts"""

    elif doc_style == 'digest':
        # digest 风格的 section_body 已经是预处理后的结构化文本（CARD 1 / CARD 2 格式）
        # 解析出两个 card 的标题和要点
        cards = []
        current_card = {}
        for line in section_body.split('\n'):
            line = line.strip()
            if line.startswith('CARD '):
                if current_card:
                    cards.append(current_card)
                current_card = {'title': '', 'facts': []}
            elif line.startswith('标题：'):
                current_card['title'] = line.replace('标题：', '').strip()
            elif line.startswith('要点：'):
                current_card['facts'] = [f.strip() for f in line.replace('要点：', '').split('/') if f.strip()]
        if current_card:
            cards.append(current_card)
        
        # 构建 card 描述
        card_descriptions = []
        for i, card in enumerate(cards, 1):
            title = card.get('title', f'新闻{i}')
            facts = card.get('facts', [])
            facts_str = ' / '.join(facts[:2]) if facts else '无'
            card_descriptions.append(f"Card {i}: {title} | 关键数据: {facts_str}")
        
        card_info = "\n".join(card_descriptions) if card_descriptions else section_body[:200]
        
        prompt = f"""{style_dna}

CRITICAL: This is image {index} of a multi-image series. It MUST look like cards from the same premium editorial news app.

Create a clean news card layout (3:4 vertical) — Economist-style editorial design.

CONTENT TO VISUALIZE:
{card_info}

REQUIRED:
1. TWO distinct news cards stacked vertically on this image
2. Each card shows one news item with: bold headline (max 15 Chinese chars) + 1-2 key data points/metrics
3. Clean white/off-white card backgrounds with subtle shadow — NO dark fills
4. Minimalist typography: headlines in bold dark charcoal, metrics in muted gray
5. Editorial restraint: NO illustrations, NO diagrams, NO decorative elements, NO bullet lists, NO prose paragraphs
6. Maximum 2 lines of text per card (headline + 1 data point) — absolute limit
7. 3:4 vertical ratio, content fills ~90% with breathing room

ABSOLUTELY FORBIDDEN:
- More than 2 lines of text per card
- Body paragraphs, prose, or article text
- Illustrations, photos, diagrams, flowcharts
- Colored backgrounds, gradients, decorative shapes
- Traditional Chinese characters (繁體字)
- Dark card fills or dark backgrounds"""

    else:
        prompt = f"""{get_style_identity('tech')}

Detail slide (3:4 vertical). Focus: "{section_title}". Keywords: {keywords_str}.
Same wireframe style as cover. Chinese labels. Content fills 70-80% of canvas. No text paragraphs."""

    return prompt


def generate_images_concurrent(prompts, output_dir, api_keys, task_id):
    """
    并发生成图片，支持重试机制
    
    策略：
      - 并发生成（max_workers = min(6, len(prompts))）
      - 每张图失败后重试1次（换 API key）
      - 任何图片最终失败 → 清理所有图片 + 终止
    
    返回：
      [image_path_1, image_path_2, ...]（按顺序）
    """
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    results = {}  # {index: image_path}
    failed = []
    
    def generate_with_retry(index, prompt, api_key_idx):
        """生成单张图片，支持重试1次"""
        if index == 0:
            img_type = "cover"
            img_name = output_path / f"{task_id}_cover.png"
        else:
            img_type = f"detail_{index}"
            img_name = output_path / f"{task_id}_image_{index}.png"
        
        # 删除旧图片（如果存在）
        if img_name.exists():
            img_name.unlink()
        
        print(f"🎨 开始生成图片 {index+1}/{len(prompts)}...")
        start_time = time.time()
        
        # 第一次尝试
        api_key = api_keys[api_key_idx % len(api_keys)]
        result = call_nano_banana_pro(prompt, str(img_name), api_key)
        
        elapsed = time.time() - start_time
        
        if result["success"]:
            print(f"✓ 图片 {index+1} 生成成功 ({elapsed:.1f}s)")
            return {"index": index, "path": str(img_name), "retries": 0}
        
        # 重试1次（换 API key）
        print(f"⚠️  图片 {index+1} 首次失败: {result.get('error', '未知错误')}，重试中...")
        retry_key = api_keys[(api_key_idx + 1) % len(api_keys)]
        result = call_nano_banana_pro(prompt, str(img_name), retry_key)
        
        if result["success"]:
            elapsed = time.time() - start_time
            print(f"✓ 图片 {index+1} 重试后生成成功 ({elapsed:.1f}s)")
            return {"index": index, "path": str(img_name), "retries": 1}
        else:
            print(f"✗ 图片 {index+1} 最终失败: {result.get('error', '未知错误')}")
            return {"index": index, "error": result["error"], "failed": True}
    
    # 并发生成
    max_workers = min(6, len(prompts))
    print(f"\n🚀 开始并发生成 {len(prompts)} 张图片（并发数: {max_workers}）...")
    print(f"⏱️  预计时间: {len(prompts) * 60}-{len(prompts) * 120} 秒\n")
    
    start_total = time.time()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(generate_with_retry, i, prompt, i): i
            for i, prompt in enumerate(prompts)
        }
        
        for future in as_completed(futures):
            result = future.result()
            
            if result.get("failed"):
                failed.append(result)
                # 取消所有剩余任务
                executor.shutdown(wait=False, cancel_futures=True)
                break
            else:
                results[result["index"]] = result["path"]
    
    elapsed_total = time.time() - start_total
    
    if failed:
        print(f"\n❌ 图片生成失败（总耗时 {elapsed_total:.1f}s）", file=sys.stderr)
        # 清理已生成的图片
        for path in results.values():
            Path(path).unlink(missing_ok=True)
        
        for f in failed:
            print(f"   - 图片 {f['index']+1}: {f['error']}", file=sys.stderr)
        sys.exit(1)
    
    print(f"\n✅ 全部 {len(prompts)} 张图片生成成功（总耗时 {elapsed_total:.1f}s）")
    
    # 按顺序返回图片路径
    return [results[i] for i in sorted(results.keys())]


def call_nano_banana_pro(prompt, filename, api_key, timeout=120):
    """
    调用 nano-banana-pro 生成图片
    
    返回：
      {"success": True, "path": "..."}
      或
      {"success": False, "error": "..."}
    """
    cmd = [
        "uv", "run", NANO_SCRIPT,
        "--prompt", prompt,
        "--filename", filename,
        "--resolution", "2K",
        "--api-key", api_key
    ]
    
    try:
        import os as _os
        _env = _os.environ.copy()
        # 显式从 ~/.env 补充 GEMINI_PROXY，确保代理透传给 uv run 子进程
        if not _env.get("GEMINI_PROXY"):
            _dotenv = _os.path.expanduser("~/.env")
            if _os.path.exists(_dotenv):
                with open(_dotenv) as _f:
                    for _line in _f:
                        _line = _line.strip()
                        if _line.startswith("GEMINI_PROXY=") and not _line.startswith("#"):
                            _env["GEMINI_PROXY"] = _line.split("=", 1)[1].strip()
                            break
        # Map GEMINI_PROXY to standard env vars so httpx picks it up automatically
        _gp = _env.get("GEMINI_PROXY", "")
        if _gp:
            _env["HTTPS_PROXY"] = _gp
            _env["https_proxy"] = _gp
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=timeout,
            env=_env
        )
        
        if result.returncode == 0 and Path(filename).exists():
            size = Path(filename).stat().st_size
            if size > 10_000:  # 至少 10KB
                return {"success": True}
            else:
                return {"success": False, "error": "文件过小（<10KB）"}
        else:
            # 检测 Gemini 返回文本
            if "Model response:" in result.stdout:
                return {"success": False, "error": "Gemini 返回文本而非图片"}
            else:
                stderr = (result.stderr or "").strip()
                stdout = (result.stdout or "").strip()
                output = stderr or stdout
                output_lower = output.lower()

                if any(k in output_lower for k in ["connection", "timeout", "timed out", "proxy", "dns", "network"]):
                    error_msg = "网络/代理连接失败（可能与本机网络或 IP 限制有关）"
                elif any(k in output_lower for k in ["401", "403", "unauthorized", "permission denied", "quota", "rate limit"]):
                    error_msg = "Gemini API 认证/配额/权限失败（检查 key、配额与地区/IP策略）"
                elif output:
                    error_msg = output[:240]
                else:
                    error_msg = "未知错误（无 stderr/stdout 输出）"
                return {"success": False, "error": error_msg}
    
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"超时（>{timeout}s）"}
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


if __name__ == "__main__":
    main()
