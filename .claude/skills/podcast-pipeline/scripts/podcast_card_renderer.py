#!/usr/bin/env python3
"""Render adaptive podcast cards in the same visual style as digest cards."""

from __future__ import annotations

import math
import os
import re
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

WIDTH = 2160
HEIGHT = 3240
BG_COLOR = (245, 245, 245)
DOT_COLOR = (160, 60, 70)

_FONT_DIR = os.environ.get("FONT_DIR", str(Path.home() / "Library" / "Fonts"))
FONT_TITLE = os.path.join(_FONT_DIR, "AlibabaPuHuiTi-3-85-Bold.ttf")
FONT_BODY = os.path.join(_FONT_DIR, "AlibabaPuHuiTi-3-55-Regular.ttf")
FONT_SOURCE = os.path.join(_FONT_DIR, "AlibabaPuHuiTi-3-55-Regular.ttf")

CARD_MARGIN_X = 84
CARD_MARGIN_Y = 200
CARD_HEIGHT = int((HEIGHT - CARD_MARGIN_Y * 2) * 0.85)  # 85% of card area = 2414px
CARD_PAD_X = 70
CARD_PAD_X_BODY = CARD_PAD_X        # body left padding = same as source/title
CARD_PAD_X_BODY_RIGHT = 110  # body right padding
CARD_PAD_Y = 88
CARD_RADIUS = 48
CARD_BG = (255, 255, 255)
CARD_BORDER = (225, 220, 220)
LINE_SPACING_SOURCE = 54   # source 46px × 1.17
LINE_SPACING_TITLE = 86    # title 72px × 1.19，给多行标题留足空间
LINE_SPACING_BODY = 91     # body 57px × 1.6（中文最佳可读性）
PARAGRAPH_GAP = 91         # 一个空行间距 = LINE_SPACING_BODY(91) × 1
BLOCK_GAP = 36
TITLE_BODY_GAP = 64        # 标题与正文间距，标题可能换行故加大
ACCENT_BAR_WIDTH = 12
ACCENT_TEXT_GAP = 20


def strip_emoji(text: str) -> str:
    result: list[str] = []
    for ch in text:
        cat = unicodedata.category(ch)
        cp = ord(ch)
        if (
            cat.startswith("L")
            or cat.startswith("N")
            or cat.startswith("P")
            or cat.startswith("Z")
            or cat in ("Sm", "Sc", "Sk", "So") and cp < 0x2600
            or cp < 0x2500
        ):
            result.append(ch)
        elif cat.startswith("C") or (0x2600 <= cp <= 0x1FFFF):
            continue
        else:
            result.append(ch)
    return "".join(result).strip()


def create_background(dot_color=DOT_COLOR, dot_size: int = 4, dot_gap: int = 48, dot_opacity: float = 0.28) -> Image.Image:
    """Draw dot grid with opacity blending at final resolution (WIDTH × HEIGHT)."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)

    # Pre-compute blended dot color: lerp(BG_COLOR, dot_color, dot_opacity)
    blended = tuple(int(bg * (1 - dot_opacity) + dc * dot_opacity) for bg, dc in zip(BG_COLOR, dot_color))
    draw = ImageDraw.Draw(img)

    for x in range(0, WIDTH + dot_gap, dot_gap):
        for y in range(0, HEIGHT + dot_gap, dot_gap):
            draw.ellipse([x - dot_size, y - dot_size, x + dot_size, y + dot_size], fill=blended)

    return img


def load_font(font_path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(font_path, size)
    except Exception:
        return ImageFont.load_default()


def _pangu_spacing(text: str) -> str:
    """Insert space between CJK and Latin/digit characters."""
    # CJK followed by Latin/digit (but not punctuation)
    text = re.sub(r'([\u4e00-\u9fff\u3400-\u4dbf])([A-Za-z0-9])', r'\1 \2', text)
    # Latin/digit followed by CJK
    text = re.sub(r'([A-Za-z0-9])([\u4e00-\u9fff\u3400-\u4dbf])', r'\1 \2', text)
    # Collapse double spaces that may result from repeated application
    text = re.sub(r'  +', ' ', text)
    return text


def _tokenize_cjk_latin(text: str) -> list[str]:
    """Split text into tokens: each CJK char is one token, consecutive Latin/digits are one token."""
    tokens: list[str] = []
    buf = ""
    for ch in text:
        if ch.isascii() and (ch.isalnum() or ch in "-_'."):
            buf += ch
        else:
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(ch)
    if buf:
        tokens.append(buf)
    return tokens


def wrap_chinese(text: str, font, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """Chinese text wrapping with kinsoku shori (W3C CLReq line-break rules).

    Token-based: Latin words/numbers are atomic (never split mid-word).
    CJK characters are individual tokens (can break between any two).
    """
    # Characters that must not appear at the start of a line (closing punctuation)
    NO_LINE_START = set(
        "\uff0c\u3002\u3001\uff1b\uff1a\uff01\uff1f"  # ，。、；：！？
        "\u300b\uff09\u3011\u300d\u300f"                # 》）】」』
        "\u2026\u2014\u00b7~"                           # …—·~
        "\u201d\u2019"                                  # " '  (closing quotes)
    )
    # Characters that must not appear at the end of a line (opening punctuation)
    NO_LINE_END = set(
        "\uff08\u3010\u300c\u300e"   # （【「『
        "\u201c\u2018\u300a"         # " ' 《  (opening quotes)
    )

    text = _pangu_spacing(text.strip())
    if not text:
        return []

    lines: list[str] = []
    for raw_part in text.splitlines():
        part = raw_part.strip()
        if not part:
            continue
        tokens = _tokenize_cjk_latin(part)
        n = len(tokens)
        i = 0
        while i < n:
            # Greedy: pack as many tokens as fit in max_width
            current = ""
            end = i
            while end < n:
                test = current + tokens[end]
                bbox = draw.textbbox((0, 0), test, font=font)
                if bbox[2] - bbox[0] > max_width and current:
                    break
                current = test
                end += 1

            if end >= n:
                lines.append(current)
                i = end
                break

            # end is the first token that doesn't fit.
            # Find a legal break point by backtracking from end.
            break_at = end

            # Kinsoku: don't start next line with NO_LINE_START char
            while break_at > i and len(tokens[break_at]) == 1 and tokens[break_at] in NO_LINE_START:
                break_at -= 1

            # Kinsoku: don't end current line with NO_LINE_END char
            while break_at > i and len(tokens[break_at - 1]) == 1 and tokens[break_at - 1] in NO_LINE_END:
                break_at -= 1

            # Safety: if backtracking collapsed to start, force break at end
            if break_at <= i:
                break_at = end

            line = "".join(tokens[i:break_at])
            lines.append(line)
            i = break_at

    return lines


def build_card_payload(card: dict, podcast_name: str, title_cn: str) -> dict:
    headline = title_cn
    return {
        "source": re.sub(r"^[•·]\s*", "", (podcast_name or "").strip()) + " - Podcast",
        "headline": headline,
        "body": strip_emoji((card.get("body") or "").strip()),
    }


def measure_card_height(card_data: dict, fonts: dict, card_w: int, draw: ImageDraw.ImageDraw) -> tuple[int, dict[str, list[str]]]:
    header_inner_w = card_w - CARD_PAD_X * 2 - ACCENT_TEXT_GAP
    body_inner_w = card_w - CARD_PAD_X_BODY - CARD_PAD_X_BODY_RIGHT - ACCENT_TEXT_GAP

    source_lines = wrap_chinese(card_data["source"], fonts["source"], header_inner_w, draw) or [card_data["source"]]
    headline_lines = wrap_chinese(card_data["headline"], fonts["title"], header_inner_w, draw) or [card_data["headline"]]

    # 按段落分割 body，计算每段行数及段落间距
    body_paragraphs = [p.strip() for p in card_data["body"].split("\n\n") if p.strip()]
    if not body_paragraphs:
        body_paragraphs = [card_data["body"]]
    all_body_lines = []
    para_line_counts = []
    for para in body_paragraphs:
        lines = wrap_chinese(para, fonts["body"], body_inner_w, draw) or [para]
        all_body_lines.extend(lines)
        para_line_counts.append(len(lines))

    body_height = sum(para_line_counts) * LINE_SPACING_BODY + (len(body_paragraphs) - 1) * PARAGRAPH_GAP

    card_height = (
        CARD_PAD_Y
        + len(source_lines) * LINE_SPACING_SOURCE
        + BLOCK_GAP
        + len(headline_lines) * LINE_SPACING_TITLE
        + TITLE_BODY_GAP
        + body_height
        + CARD_PAD_Y
    )
    return card_height, {
        "source": source_lines,
        "headline": headline_lines,
        "body": all_body_lines,
        "para_line_counts": para_line_counts,
    }


def draw_card(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, lines: dict[str, list[str]], fonts: dict) -> None:
    draw.rounded_rectangle([x, y, x + w, y + h], radius=CARD_RADIUS, fill=CARD_BG, outline=CARD_BORDER, width=1)

    accent_x = x + 2
    draw.rounded_rectangle([accent_x, y + 16, accent_x + ACCENT_BAR_WIDTH, y + h - 16], radius=2, fill=(160, 60, 70))

    cx = x + CARD_PAD_X + ACCENT_TEXT_GAP
    cx_body = x + CARD_PAD_X_BODY + ACCENT_TEXT_GAP
    cy = y + CARD_PAD_Y
    max_y = y + h - CARD_PAD_Y

    for line in lines["source"]:
        draw.text((cx, cy), line, font=fonts["source"], fill=(160, 60, 70))
        cy += LINE_SPACING_SOURCE

    cy += BLOCK_GAP

    for line in lines["headline"]:
        draw.text((cx, cy), line, font=fonts["title"], fill=(160, 60, 70))
        cy += LINE_SPACING_TITLE

    cy += TITLE_BODY_GAP

    para_line_counts = lines.get("para_line_counts", [len(lines["body"])])
    body_lines_iter = iter(lines["body"])
    stop_rendering = False
    for p_idx, line_count in enumerate(para_line_counts):
        for _ in range(line_count):
            line = next(body_lines_iter, None)
            if line is None or cy + LINE_SPACING_BODY > max_y:
                stop_rendering = True
                break
            draw.text((cx_body, cy), line, font=fonts["body"], fill=(70, 70, 70))
            cy += LINE_SPACING_BODY
        if stop_rendering:
            break
        # 段落间距（最后一段不加）
        if p_idx < len(para_line_counts) - 1:
            cy += PARAGRAPH_GAP
        if cy >= max_y:
            break


def _draw_card_scaled(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, lines: dict[str, list[str]], fonts: dict, S: int) -> None:
    """draw_card 的 2× 缩放版本，所有坐标和间距都乘以 S。"""
    draw.rounded_rectangle([x, y, x + w, y + h], radius=CARD_RADIUS * S, fill=CARD_BG, outline=CARD_BORDER, width=S)

    accent_x = x + 2 * S
    draw.rounded_rectangle([accent_x, y + 16 * S, accent_x + ACCENT_BAR_WIDTH * S, y + h - 16 * S], radius=2 * S, fill=(160, 60, 70))

    cx = x + CARD_PAD_X * S + ACCENT_TEXT_GAP * S
    cx_body = x + CARD_PAD_X_BODY * S + ACCENT_TEXT_GAP * S
    cy = y + CARD_PAD_Y * S
    max_y = y + h - CARD_PAD_Y * S

    for line in lines["source"]:
        draw.text((cx, cy), line, font=fonts["source"], fill=(160, 60, 70))
        cy += LINE_SPACING_SOURCE * S

    cy += BLOCK_GAP * S

    for line in lines["headline"]:
        draw.text((cx, cy), line, font=fonts["title"], fill=(160, 60, 70))
        cy += LINE_SPACING_TITLE * S

    cy += TITLE_BODY_GAP * S

    para_line_counts = lines.get("para_line_counts", [len(lines["body"])])
    body_lines_iter = iter(lines["body"])
    stop_rendering = False
    for p_idx, line_count in enumerate(para_line_counts):
        for _ in range(line_count):
            line = next(body_lines_iter, None)
            if line is None or cy + LINE_SPACING_BODY * S > max_y:
                stop_rendering = True
                break
            draw.text((cx_body, cy), line, font=fonts["body"], fill=(70, 70, 70))
            cy += LINE_SPACING_BODY * S
        if stop_rendering:
            break
        if p_idx < len(para_line_counts) - 1:
            cy += PARAGRAPH_GAP * S
        if cy >= max_y:
            break


def render_single_card(card_data: dict, output_path: Path) -> str:
    # 2× 超采样：以目标尺寸 2 倍渲染，最后缩小到目标尺寸，文字边缘更锐利
    S = 2
    fonts = {
        "title": load_font(FONT_TITLE, 72 * S),
        "body": load_font(FONT_BODY, 57 * S),
        "source": load_font(FONT_SOURCE, 46 * S),
    }

    # layout 计算仍用原始尺寸（与 split_card_if_overflow 保持一致）
    card_w_orig = WIDTH - CARD_MARGIN_X * 2
    probe = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    probe_draw_orig = ImageDraw.Draw(probe)
    # 用原始字体 probe 计算 lines（split 逻辑已用原始字体，这里保持一致）
    fonts_orig = {
        "title": load_font(FONT_TITLE, 72),
        "body": load_font(FONT_BODY, 57),
        "source": load_font(FONT_SOURCE, 46),
    }
    _, lines = measure_card_height(card_data, fonts_orig, card_w_orig, probe_draw_orig)
    card_h = CARD_HEIGHT
    card_y = (HEIGHT - card_h) // 2

    # 以 2× 尺寸绘制
    rW, rH = WIDTH * S, HEIGHT * S
    rCARD_MARGIN_X = CARD_MARGIN_X * S
    rcard_w = card_w_orig * S
    rcard_h = card_h * S
    rcard_y = card_y * S

    # Step 1: 背景（含点阵）在最终尺寸绘制，保持 RGB
    bg = create_background()

    # Step 2: 卡片内容在 2× RGB 画布上绘制（纯 RGB，不含 alpha，避免透明区插值污染）
    card_canvas = Image.new("RGB", (rW, rH), BG_COLOR)
    draw = ImageDraw.Draw(card_canvas)
    _draw_card_scaled(draw, rCARD_MARGIN_X, rcard_y, rcard_w, rcard_h, lines, fonts, S)

    # Step 3: 卡片画布整体 resize 到最终尺寸（LANCZOS 只对非透明 RGB 内容插值）
    card_final = card_canvas.resize((WIDTH, HEIGHT), Image.LANCZOS)

    # Step 4: 精确圆角矩形 mask，外扩 1px 覆盖完整描边（outline 居中绘制，外半部分需要 mask 包含）
    card_w_final = WIDTH - CARD_MARGIN_X * 2
    border_expand = 1
    exact_mask = Image.new("L", (WIDTH, HEIGHT), 0)
    ImageDraw.Draw(exact_mask).rounded_rectangle(
        [CARD_MARGIN_X - border_expand, card_y - border_expand,
         CARD_MARGIN_X + card_w_final + border_expand, card_y + card_h + border_expand],
        radius=CARD_RADIUS,
        fill=255,
    )

    # Step 5: 卡片阴影 — 在背景上绘制偏移模糊的圆角矩形
    shadow_offset = 6
    shadow_blur = 16
    shadow_color = (0, 0, 0)
    shadow_opacity = 55  # 0-255, higher = darker
    shadow_layer = Image.new("L", (WIDTH, HEIGHT), 0)
    ImageDraw.Draw(shadow_layer).rounded_rectangle(
        [CARD_MARGIN_X + shadow_offset, card_y + shadow_offset,
         CARD_MARGIN_X + card_w_final + shadow_offset, card_y + card_h + shadow_offset],
        radius=CARD_RADIUS,
        fill=shadow_opacity,
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=shadow_blur))
    shadow_img = Image.new("RGB", (WIDTH, HEIGHT), shadow_color)
    bg.paste(Image.composite(shadow_img, bg, shadow_layer), (0, 0))

    # Step 6: 将卡片贴到背景，mask 精确限定卡片区域，背景点阵在卡片外完整保留
    bg.paste(card_final, (0, 0), exact_mask)

    png_path = output_path.with_suffix(".png")
    bg.save(png_path, format="PNG")
    return str(png_path)


def _measure_body_fit(
    body_paragraphs: list[str],
    fonts: dict,
    inner_w: int,
    available_height: int,
    draw: ImageDraw.ImageDraw,
) -> int:
    """
    计算在给定高度内能放下多少段落（返回可容纳的段落数）。
    """
    cy = 0
    for p_idx, para in enumerate(body_paragraphs):
        lines = wrap_chinese(para, fonts["body"], inner_w, draw) or [para]
        para_height = len(lines) * LINE_SPACING_BODY
        gap = PARAGRAPH_GAP if p_idx < len(body_paragraphs) - 1 else 0
        if cy + para_height + gap > available_height:
            return p_idx  # 第 p_idx 段放不下，返回能放的段落数
        cy += para_height + gap
    return len(body_paragraphs)  # 全部能放下



def _split_sentences_quote_aware(text: str) -> list[str]:
    """Split Chinese text into sentences, respecting quoted blocks.

    Uses a quote-depth stack so sentence-ending punctuation inside quotes
    (e.g. 。 inside "...") does NOT trigger a split.  The closing quote
    and any trailing punctuation are kept with the preceding sentence.
    """
    OPEN_QUOTES = set('\u201c\u300c\u300e\u00ab')   # " 「 『 《
    CLOSE_QUOTES = set('\u201d\u300d\u300f\u00bb')   # " 」 』 》
    SENTENCE_END = set('。！？')

    sentences: list[str] = []
    current: list[str] = []
    quote_depth = 0

    i = 0
    chars = list(text)
    n = len(chars)
    while i < n:
        ch = chars[i]
        current.append(ch)

        if ch in OPEN_QUOTES:
            quote_depth += 1
        elif ch in CLOSE_QUOTES:
            quote_depth = max(0, quote_depth - 1)
        elif ch in SENTENCE_END and quote_depth == 0:
            # Absorb any immediately following closing quotes
            while i + 1 < n and chars[i + 1] in CLOSE_QUOTES:
                i += 1
                current.append(chars[i])
                quote_depth = max(0, quote_depth - 1)
            sentences.append(''.join(current))
            current = []
        i += 1

    if current:
        tail = ''.join(current).strip()
        if tail:
            sentences.append(tail)
    return sentences


def split_long_paragraphs(paragraphs: list[str], max_chars: int = 150) -> list[str]:
    """Split paragraphs longer than max_chars using quote-aware sentence splitting.

    Groups sentences back into chunks of ~max_chars to give the DP splitter
    fine-grained but not excessively fragmented input.
    """
    result: list[str] = []
    for para in paragraphs:
        if len(para) <= max_chars:
            result.append(para)
            continue
        sentences = _split_sentences_quote_aware(para)
        current = ""
        for sent in sentences:
            if not sent:
                continue
            if current and len(current) + len(sent) > max_chars:
                result.append(current.strip())
                current = sent
            else:
                current += sent
        if current.strip():
            result.append(current.strip())
    return result


def _dp_balanced_split(para_heights: list[int], max_height: int, max_cards: int = 9) -> tuple[int, list[int]]:
    """DP: find optimal split points minimizing card height variance.

    Tries K=1,2,3... until all cards fit within max_height.
    For each K, finds globally optimal cut points via DP.
    Returns (n_cards, [cut_indices]).
    """
    n = len(para_heights)
    if n == 0:
        return 1, []

    # Prefix sums for O(1) range queries
    prefix = [0] * (n + 1)
    for i in range(n):
        prefix[i + 1] = prefix[i] + para_heights[i]
    total = prefix[n]

    # Single card fits
    if total <= max_height:
        return 1, []

    for K in range(2, max_cards + 1):
        ideal = total / K
        # Minimum fill: last card should be at least 40% of ideal height
        min_last_card = ideal * 0.4
        INF = float('inf')
        # dp[i][j] = min cost to place first i paragraphs into j cards
        dp = [[INF] * (K + 1) for _ in range(n + 1)]
        parent = [[0] * (K + 1) for _ in range(n + 1)]
        dp[0][0] = 0

        for j in range(1, K + 1):
            for i in range(j, n + 1):
                for m in range(j - 1, i):
                    card_h = prefix[i] - prefix[m]
                    if card_h > max_height:
                        continue
                    cost = dp[m][j - 1] + (card_h - ideal) ** 2
                    # Extra penalty for the last card being too empty
                    if j == K and card_h < min_last_card:
                        cost += (min_last_card - card_h) ** 2
                    if cost < dp[i][j]:
                        dp[i][j] = cost
                        parent[i][j] = m

        if dp[n][K] < INF:
            # Backtrack to find cut points
            cuts = []
            pos = n
            for j in range(K, 1, -1):
                pos = parent[pos][j]
                cuts.append(pos)
            cuts.reverse()
            return K, cuts

    # Fallback: couldn't fit in max_cards
    return max_cards, []


def split_card_if_overflow(
    card_data: dict,
    fonts: dict,
    card_w: int,
    probe_draw: ImageDraw.ImageDraw,
) -> list[dict]:
    """Split card into multiple cards using DP balanced pagination.

    1. Split long paragraphs at sentence boundaries
    2. Measure each paragraph's rendered height
    3. Use DP to find optimal split points (minimize height variance)
    4. Auto-determine card count (minimum that fits within CARD_HEIGHT)
    """
    header_inner_w = card_w - CARD_PAD_X * 2 - ACCENT_TEXT_GAP
    body_inner_w = card_w - CARD_PAD_X_BODY - CARD_PAD_X_BODY_RIGHT - ACCENT_TEXT_GAP

    source_lines = wrap_chinese(card_data["source"], fonts["source"], header_inner_w, probe_draw) or [card_data["source"]]
    headline_lines = wrap_chinese(card_data["headline"], fonts["title"], header_inner_w, probe_draw) or [card_data["headline"]]
    header_height = (
        CARD_PAD_Y
        + len(source_lines) * LINE_SPACING_SOURCE
        + BLOCK_GAP
        + len(headline_lines) * LINE_SPACING_TITLE
        + TITLE_BODY_GAP
        + CARD_PAD_Y
    )
    available_body_height = CARD_HEIGHT - header_height

    body_text = card_data.get("body", "")
    # Normalize: split on \n\n (paragraph break), then collapse \n within
    # paragraphs to spaces (prevents orphaned quotes from LLM line breaks)
    body_paragraphs = [
        re.sub(r'\n', ' ', p).strip()
        for p in body_text.split("\n\n") if p.strip()
    ]
    if not body_paragraphs:
        return [card_data]

    # Split long paragraphs at sentence boundaries (fine granularity for DP balance)
    body_paragraphs = split_long_paragraphs(body_paragraphs, max_chars=400)

    # Measure each paragraph's rendered height (including inter-paragraph gap)
    para_heights: list[int] = []
    for i, para in enumerate(body_paragraphs):
        lines = wrap_chinese(para, fonts["body"], body_inner_w, probe_draw) or [para]
        h = len(lines) * LINE_SPACING_BODY
        if i > 0:
            h += PARAGRAPH_GAP
        para_heights.append(h)

    total_height = sum(para_heights)
    if total_height <= available_body_height:
        return [card_data]

    # DP balanced split
    n_cards, cuts = _dp_balanced_split(para_heights, available_body_height)

    if not cuts:
        # Fallback: single card or couldn't split
        return [card_data]

    # Build card slices from cut points
    slices: list[str] = []
    prev = 0
    for cut in cuts:
        slices.append("\n\n".join(body_paragraphs[prev:cut]))
        prev = cut
    slices.append("\n\n".join(body_paragraphs[prev:]))

    return [{**card_data, "body": s} for s in slices if s]


def render_podcast_cards(cards: list[dict], podcast_name: str, title_cn: str, output_dir: str) -> list[str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 渲染前清空旧卡片文件，避免重复发送
    for old_file in output_path.glob("podcast_card_*.png"):
        old_file.unlink()
    for old_file in output_path.glob("podcast_card_*.jpg"):
        old_file.unlink()

    # 预处理：将 card 转换为 payload，检测溢出并自动拆卡
    fonts = {
        "title": load_font(FONT_TITLE, 72),
        "body": load_font(FONT_BODY, 57),
        "source": load_font(FONT_SOURCE, 46),
    }
    card_w = WIDTH - CARD_MARGIN_X * 2
    probe = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    probe_draw = ImageDraw.Draw(probe)

    expanded: list[dict] = []
    for card in cards:
        payload = build_card_payload(card, podcast_name=podcast_name, title_cn=title_cn)
        split_cards = split_card_if_overflow(payload, fonts, card_w, probe_draw)
        expanded.extend(split_cards)

    total = len(expanded)
    results: list[str] = []
    for idx, card_payload in enumerate(expanded, start=1):
        # 标题追加序号，如「RAG 之后如何检索 - 1」
        card_payload = {**card_payload, "headline": f"{card_payload['headline']} - {idx}"}
        file_path = output_path / f"podcast_card_{idx:02d}.jpg"
        results.append(render_single_card(card_payload, file_path))
    return results


__all__ = ["render_podcast_cards"]
