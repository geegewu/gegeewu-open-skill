#!/usr/bin/env python3
"""
Content preparation layer for XHS publishing.

Responsibilities:
  - Parse markdown front matter
  - Validate digest publish input
  - Clean markdown formatting, validate title, add signature
  - Smart content compression
  - Divider normalization
  - Tags extraction and enforcement
  - Content length enforcement

This module does NOT handle:
  - Image generation
  - Publishing
  - Post-publish sync
  - Locks or state
  - Network requests
"""

import re
import yaml
from pathlib import Path


def parse_markdown_frontmatter(md_file):
    """Parse YAML front matter from markdown file."""
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()

    if not content.startswith('---'):
        return {}, content

    parts = content.split('---', 2)
    if len(parts) < 3:
        return {}, content

    metadata = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()

    return metadata, body


def validate_digest_publish_input(md_file: Path, metadata: dict, skip_cover: bool) -> None:
    """
    Hard gate for digest publish path.
    When skip_cover=True (tweetsave/blog digest), front matter must be complete
    to avoid accidental fallback to tech/Gemini prompt branch.
    """
    if not skip_cover:
        return

    style = str(metadata.get("style") or "").strip().lower()
    title = str(metadata.get("title") or "").strip()
    tags = metadata.get("tags")

    if style != "digest":
        raise ValueError(
            f"❌ Digest 发布硬门禁失败：style 必须为 'digest'（当前: {style or '缺失'}）\n"
            f"   文件: {md_file}\n"
            f"   这会导致走 tech/Gemini 分支并生成错误图片。"
        )
    if not title:
        raise ValueError(
            f"❌ Digest 发布硬门禁失败：front matter 缺少 title\n"
            f"   文件: {md_file}"
        )
    if not tags:
        raise ValueError(
            f"❌ Digest 发布硬门禁失败：front matter 缺少 tags\n"
            f"   文件: {md_file}"
        )


def prepare_content(md_file, doc_style='tech'):
    """
    Prepare publish content (format cleanup only, no AI calls).

    Args:
        md_file: markdown file path
        doc_style: document style ('tech'|'interview'|'product'|'philosophy')

    Returns:
        (xhs_title, xhs_desc, doc_style)
    """
    print("\n📝 准备发布内容...\n")

    metadata, body = parse_markdown_frontmatter(md_file)
    # Strip ---CARDS--- section (used for image generation only, not XHS body)
    body = re.split(r'\n?---CARDS---\n?', body)[0].strip()

    title = metadata.get('title', '小红书笔记')
    emoji = metadata.get('emoji', '')

    # Override style from front matter if present
    doc_style = metadata.get('style', doc_style)

    # Title length validation (XHS platform hard limit: 20 chars)
    if len(title) > 20:
        raise ValueError(
            f"❌ 标题过长 ({len(title)}字 > 20字限制)\n"
            f"   标题: {title}\n\n"
            f"ORCHESTRATION ERROR: Sonnet should optimize title via AI before publish.\n"
            f"Correct flow:\n"
            f"  1. Kimi rewrites content → generates title\n"
            f"  2. Sonnet checks: if len(title) > 20\n"
            f"  3. Sonnet spawns Kimi: 'Optimize title to 12-20 chars: {{title}}'\n"
            f"  4. Sonnet updates front matter with optimized title\n"
            f"  5. Then calls this script\n"
        )

    xhs_title = f"{title} {emoji}".strip()

    # Remove emoji if combined title exceeds limit
    if len(xhs_title) > 20:
        xhs_title = title
        print(f"  ⚠️  标题+emoji超长，已移除emoji: {xhs_title}")

    # Clean markdown formatting
    clean_text = body
    clean_text = re.sub(r'```[\s\S]*?```', '', clean_text)
    clean_text = re.sub(r'^#+\s+', '', clean_text, flags=re.MULTILINE)
    clean_text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', clean_text)
    clean_text = re.sub(r'^[-━─]{3,}$', '', clean_text, flags=re.MULTILINE)
    clean_text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', clean_text)
    clean_text = re.sub(r'^>\s*', '', clean_text, flags=re.MULTILINE)
    clean_text = re.sub(r'^[🎯🐛💡🔧🏆🚀⚡✅💰📊🎉🤖🔍⚠️❌]+\s*', '', clean_text, flags=re.MULTILINE)
    clean_text = re.sub(r'\n{3,}', '\n\n', clean_text)

    # Remove trailing tag lines
    xhs_desc = re.sub(
        r'^(#[^\s#]+\s*)+$',
        '',
        clean_text,
        flags=re.MULTILINE
    ).strip()

    xhs_desc = re.sub(r'\n{3,}', '\n\n', xhs_desc)

    # Signature handling
    signature = "by gegeewu 🦉"
    xhs_desc = xhs_desc.rstrip()
    if xhs_desc.endswith('by gegeewu'):
        xhs_desc = xhs_desc[:-len('by gegeewu')] + signature
        print(f"  ✓ 旧格式署名已升级为: {signature}")
    elif signature not in xhs_desc:
        xhs_desc += f"\n\n{signature}"
        print(f"  ✓ 添加署名: {signature}")
    else:
        print(f"  ✓ 署名已是 canonical 格式")

    print(f"标题: {xhs_title}")
    print(f"正文长度: {len(xhs_desc)} 字")
    print(f"文档风格: {doc_style}")

    return xhs_title, xhs_desc, doc_style


def compress_content_smart(content, target_length):
    """
    Smart content compression preserving narrative structure.

    Strategy:
      1. Keep opening hook (first 2 paragraphs)
      2. Keep core paragraphs (with dividers, emoji, section headers)
      3. Remove secondary details
      4. Keep ending (last paragraph)
    """
    if len(content) <= target_length:
        return content

    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]

    if len(paragraphs) <= 3:
        return content[:target_length].rsplit('。', 1)[0] + "..."

    keep_start = paragraphs[:2]
    keep_end = paragraphs[-1:]
    middle = paragraphs[2:-1]

    def paragraph_priority(p):
        score = 0
        if '━━━' in p:
            score -= 20
        if any(emoji in p for emoji in ['🔹', '📐', '💡', '🚀', '⚡']):
            score += 8
        if re.search(r'\d+[倍次个张小时分钟秒%×xX]', p):
            score += 5
        if any(kw in p for kw in ['核心', '重要', '关键', '最', '第一', '第二', '第三']):
            score += 3
        if len(p) > 200:
            score -= 5
        return score

    middle_sorted = sorted(middle, key=paragraph_priority, reverse=True)

    kept_middle = []
    current_length = len('\n\n'.join(keep_start + keep_end))

    for p in middle_sorted:
        if current_length + len(p) + 4 < target_length:
            kept_middle.append(p)
            current_length += len(p) + 4
        else:
            break

    kept_middle_ordered = [p for p in middle if p in kept_middle]

    compressed = '\n\n'.join(keep_start + kept_middle_ordered + keep_end)

    # Post-process: clean orphaned dividers
    cleaned_paragraphs = []
    for i, p in enumerate(compressed.split('\n\n')):
        p = p.strip()
        if not p:
            continue
        is_divider = '━━━' in p
        if is_divider:
            prev_is_content = i > 0 and '━━━' not in cleaned_paragraphs[-1] if cleaned_paragraphs else False
            if not prev_is_content:
                continue
        cleaned_paragraphs.append(p)
    while cleaned_paragraphs and '━━━' in cleaned_paragraphs[-1]:
        cleaned_paragraphs.pop()
    compressed = '\n\n'.join(cleaned_paragraphs)

    if len(compressed) > target_length:
        compressed = compressed[:target_length].rsplit('。', 1)[0]
        if compressed:
            compressed += "..."

    return compressed


def fix_dividers(text):
    """
    Ensure section dividers exist between major sections.

    Handles:
    1. Normalize existing ━━━ variants
    2. Detect section headers and insert missing dividers
    3. Ensure proper spacing around dividers
    """
    DIVIDER = '━━━━━━━━━━━━━━━'

    text = re.sub(r'^[━─-]{3,}$', DIVIDER, text, flags=re.MULTILINE)

    divider_count = text.count(DIVIDER)

    section_emoji_pattern = re.compile(
        r'^(📐|💡|🔹|🚀|⚡|🔧|📊|💬|🎯|🛡️|🤖|━)\s+\S',
        re.MULTILINE
    )
    section_headers = list(section_emoji_pattern.finditer(text))

    if len(section_headers) > 0 and divider_count < len(section_headers):
        lines = text.split('\n')
        result_lines = []

        for i, line in enumerate(lines):
            stripped = line.strip()
            if section_emoji_pattern.match(stripped):
                lookback = '\n'.join(result_lines[-3:]) if result_lines else ''
                if DIVIDER not in lookback:
                    if result_lines and result_lines[-1].strip() != '':
                        result_lines.append('')
                    result_lines.append(DIVIDER)
                    result_lines.append('')
            result_lines.append(line)

        text = '\n'.join(result_lines)

    text = re.sub(r'([^\n])\n(━━━━━━━━━━━━━━━)', r'\1\n\n\2', text)
    text = re.sub(r'(━━━━━━━━━━━━━━━)\n([^\n])', r'\1\n\n\2', text)

    return text


def extract_tags(metadata, md_file):
    """
    Extract and validate tags from front matter or fallback sources.

    Returns:
        list of tag strings (5-10 items, brand tags enforced)
    """
    topics = []
    if 'tags' in metadata and metadata['tags']:
        if isinstance(metadata['tags'], list):
            topics = metadata['tags'][:10]
        elif isinstance(metadata['tags'], str):
            topics = [t.strip() for t in metadata['tags'].split(',')][:10]

        # Enforce brand tags
        brand_tags = ['gegeewu', 'Gegeewu', '嗝嗝巫']
        forced_tags = brand_tags

        existing_lower = [t.lower().lstrip('#') for t in topics]
        for ft in reversed(forced_tags):
            if ft.lower() not in existing_lower:
                topics.insert(0, ft)
                existing_lower.insert(0, ft.lower())
        topics = topics[:10]

        print(f"  从 front matter 提取 tags: {topics}")

        if len(topics) < 5:
            raise ValueError(
                f"❌ Tags 数量不足 ({len(topics)}个 < 5个)\n"
                f"   Tags: {topics}\n\n"
                f"ORCHESTRATION ERROR: Kimi should generate 5-10 tags during rewrite.\n"
                f"Prompt templates already specify 'CRITICAL - Tag生成要求（MANDATORY 5-10个）'\n"
                f"Check prompts_storytelling.py templates."
            )
    else:
        # Fallback: extract #tags from last line of markdown
        with open(md_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            last_line = lines[-1].strip() if lines else ""
            tags = re.findall(r'#([^\s#]+)', last_line)
            if tags and len(tags) >= 3:
                topics = tags[:10]
                print(f"  从最后一行提取 tags: {topics}")
            else:
                topics = ['gegeewu', 'Gegeewu', '嗝嗝巫', '技术分享', '人工智能']
                print(f"  ⚠️  未找到 tags，自动使用默认 tags: {topics}")

    return topics


def enforce_content_limit(title, desc, tag_text, content_limit, doc_style):
    """
    Check total content length and compress if needed.

    Args:
        title: XHS title
        desc: XHS description body
        tag_text: formatted tag string (e.g. "#tag1 #tag2")
        content_limit: max allowed total length
        doc_style: document style (affects divider handling)

    Returns:
        (desc, full_text) - possibly compressed desc and final full_text
    """
    full_text = f"{title}\n\n{desc}\n\n{tag_text}"

    if len(full_text) > content_limit:
        print(f"\n⚠️  内容超限检测（{len(full_text)}字 > {content_limit}字限制）")
        print(f"   标题: {len(title)}字")
        print(f"   正文: {len(desc)}字")
        print(f"   Tags: {len(tag_text)}字")

        overflow = len(full_text) - content_limit
        target_desc_length = max(120, len(desc) - overflow - 50)

        print(f"   需要从正文删除: {overflow + 50}字")

        desc = compress_content_smart(desc, target_desc_length)
        # fix_dividers only for non-digest styles
        if doc_style != 'digest':
            desc = fix_dividers(desc)

        full_text = f"{title}\n\n{desc}\n\n{tag_text}"
        print(f"  ✓ 压缩完成（最终长度: {len(full_text)}字）")

        if len(full_text) > content_limit:
            print(f"  ⚠️  仍然超限，强制截断")
            desc = desc[:max(100, target_desc_length - 100)]
            full_text = f"{title}\n\n{desc}\n\n{tag_text}"
            print(f"  ✓ 强制截断完成（{len(full_text)}字）")
    else:
        print(f"\n✓ 长度检查通过（{len(full_text)}字 / {content_limit}字限制）")

    return desc, full_text
