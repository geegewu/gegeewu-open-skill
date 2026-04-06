#!/usr/bin/env python3
"""
digest_card_renderer.py - 本地渲染 digest 新闻卡片（无需 Gemini）

输出：2:3 竖图（小红书）， Economist 风格背景 + 文字卡片
"""

import os
import sys
import math
import re
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import unicodedata

def strip_emoji(text: str) -> str:
    """移除无法被 PIL 中文字体渲染的 emoji 字符，避免显示为方框。"""
    result = []
    for ch in text:
        cat = unicodedata.category(ch)
        cp = ord(ch)
        # 保留中英文、数字、标点、基本符号；剔除 Emoji/Symbol/Private-Use
        if (cat.startswith('L') or cat.startswith('N') or
                cat.startswith('P') or cat.startswith('Z') or
                cat in ('Sm', 'Sc', 'Sk', 'So') and cp < 0x2600 or
                cp < 0x2500):
            result.append(ch)
        elif cat.startswith('C') or (0x2600 <= cp <= 0x1FFFF):
            continue  # 剔除 emoji / 控制字符
        else:
            result.append(ch)
    return ''.join(result).strip()

# 配置
WIDTH, HEIGHT = 1080, 1620  # 2:3 竖图小红书
BG_COLOR = (245, 245, 245)  # off-white #F5F5F5 — 不能改！
DOT_COLOR = (160, 60, 70)    # accent red — blended at runtime via dot_opacity (same as podcast)

# 字体路径
_FONT_DIR = os.environ.get("FONT_DIR", str(Path.home() / "Library" / "Fonts"))
FONT_TITLE = os.path.join(_FONT_DIR, "AlibabaPuHuiTi-3-55-Regular.ttf")
FONT_BODY = os.path.join(_FONT_DIR, "AlibabaPuHuiTi-3-55-Regular.ttf")
FONT_SOURCE = os.path.join(_FONT_DIR, "AlibabaPuHuiTi-3-55-Regular.ttf")

# 卡片参数
CARD_MARGIN_X = 72   # 左右边距
CARD_MARGIN_Y = 100  # 顶部起始
CARD_GAP = 48        # 两卡间距
CARD_PAD_X = 40      # 卡内左边距
CARD_PAD_Y = 44      # 卡内上下留白（加大）
CARD_RADIUS = 16
CARD_BG = (255, 255, 255)
CARD_BORDER = (225, 220, 220)
LINE_SPACING_SOURCE  = 44
LINE_SPACING_TITLE   = 72   # 标题行间距
LINE_SPACING_SUMMARY = 40   # 正文行间距（配合 24px 字号）
BLOCK_GAP        = 18       # source→title 间距
TITLE_BODY_GAP   = 48       # 标题→正文 间距（翻倍：18×2=36，再加宽到48）
# MAX_CARD_HEIGHT 按画布计算：两卡 + CARD_GAP 居中，每卡上限
# (1620 - 48gap) / 2 = 786px 理论极限；留 60px 上下白边 → 756px
# 设计目标: source≤2行+title2行+body7行+间距 = 666px，留余量
MAX_CARD_HEIGHT = 760  # 最大卡片高度（两卡合计 ≤ 1568px，画布 1620px）


def create_background(w, h, dot_color=DOT_COLOR, dot_size=2, dot_gap=24, dot_opacity=0.28):
    """创建带点阵网格的 off-white 背景（对齐 podcast_card_renderer，无暗角）"""
    img = Image.new('RGB', (w, h), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # 点阵网格：opacity lerp 混色，与 podcast_card_renderer 一致
    blended = tuple(int(bg * (1 - dot_opacity) + dc * dot_opacity) for bg, dc in zip(BG_COLOR, dot_color))
    for x in range(0, w + dot_gap, dot_gap):
        for y in range(0, h + dot_gap, dot_gap):
            draw.ellipse(
                [x - dot_size, y - dot_size, x + dot_size, y + dot_size],
                fill=blended
            )

    return img


def load_font(font_path, size):
    """加载字体"""
    try:
        return ImageFont.truetype(font_path, size)
    except Exception as e:
        print(f"⚠️ 字体加载失败 {font_path}: {e}")
        return ImageFont.load_default()


def wrap_text(text, font, max_width, draw):
    """自动换行"""
    lines = []
    words = text.split('')
    current_line = ''
    
    for word in words:
        test_line = current_line + word
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    
    if current_line:
        lines.append(current_line)
    
    return lines if lines else [text[:10]]


def wrap_chinese(text, font, max_width, draw):
    """按像素宽度换行（兼容中文字符）"""
    lines = []
    current = ''
    for ch in text:
        test = current + ch
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines or [text[:15]]


def measure_card_height(card_data, fonts, card_w, draw):
    """计算卡片所需高度（不超过 MAX_CARD_HEIGHT）
    布局: CARD_PAD_Y + source(≤2行) + BLOCK_GAP + title(≤2行) + TITLE_BODY_GAP + body(≤7行) + CARD_PAD_Y
    设计极限: 88 + 106 + 192 + 280 = 666px < MAX_CARD_HEIGHT
    """
    inner_w = card_w - CARD_PAD_X * 2 - 20  # 20 = 强调条宽度偏移

    h = CARD_PAD_Y

    # source：最多 2 行（wrap，不截断）
    source_text = re.sub(r'^[•·]\s*', '', (card_data.get('source') or '').strip())
    if source_text:
        src_lines = wrap_chinese(source_text, fonts['source'], inner_w, draw)
        h += min(len(src_lines), 2) * LINE_SPACING_SOURCE
    else:
        h += LINE_SPACING_SOURCE
    h += BLOCK_GAP

    # title：最多 2 行
    title_lines = wrap_chinese(card_data.get('headline', ''), fonts['title'], inner_w, draw)
    h += min(len(title_lines), 2) * LINE_SPACING_TITLE + TITLE_BODY_GAP

    # body：最多 7 行
    summary = card_data.get('summary', '')
    summary = strip_emoji(summary)
    if summary:
        s_lines = wrap_chinese(summary, fonts['body'], inner_w, draw)
        h += min(len(s_lines), 7) * LINE_SPACING_SUMMARY

    h += CARD_PAD_Y
    return max(min(h, MAX_CARD_HEIGHT), 200)


def draw_card(draw, x, y, w, h, card_data, fonts):
    """绘制单个新闻卡片（动态内容布局）"""
    inner_w = w - CARD_PAD_X * 2 - 20  # 强调条偏移

    # 卡片背景
    draw.rounded_rectangle(
        [x, y, x + w, y + h], radius=CARD_RADIUS,
        fill=CARD_BG, outline=CARD_BORDER, width=1
    )

    # 左侧暗红色强调条（Economist 风格）
    accent_x = x + 2
    draw.rounded_rectangle(
        [accent_x, y + 16, accent_x + 8, y + h - 16],
        radius=2, fill=(160, 60, 70)
    )

    cx = x + CARD_PAD_X + 20  # 文字起始 x（给强调条留空间）
    cy = y + CARD_PAD_Y
    max_y = y + h - CARD_PAD_Y  # 内容区底部边界

    # Source line（域名/博主，最多 2 行 wrap，不截断）
    source_text = (card_data.get('source') or '').strip() or "unknown source"
    source_text = re.sub(r'^[•·]\s*', '', source_text)
    src_lines = wrap_chinese(source_text, fonts['source'], inner_w, draw)
    for src_line in src_lines[:2]:
        draw.text((cx, cy), src_line, font=fonts['source'], fill=(126, 116, 118))
        cy += LINE_SPACING_SOURCE
    cy += BLOCK_GAP

    # 标题（深灰）
    title_lines = wrap_chinese(card_data.get('headline', ''), fonts['title'], inner_w, draw)
    for line in title_lines[:2]:
        if cy + LINE_SPACING_TITLE > max_y:
            break
        draw.text((cx, cy), line, font=fonts['title'], fill=(28, 28, 28))
        cy += LINE_SPACING_TITLE
    cy += TITLE_BODY_GAP  # 标题→正文间距（翻倍）

    # 摘要（中灰，超出截断加 ····）
    summary = card_data.get('summary', '')
    summary = strip_emoji(summary)
    max_summary_lines = 7
    if summary and cy < max_y:
        s_lines = wrap_chinese(summary, fonts['body'], inner_w, draw)
        for idx, line in enumerate(s_lines):
            if idx >= max_summary_lines:
                break
            next_y = cy + LINE_SPACING_SUMMARY
            is_last_slot = (next_y + LINE_SPACING_SUMMARY > max_y) or (idx == max_summary_lines - 1)
            has_more = (idx < len(s_lines) - 1)

            if is_last_slot and has_more:
                # 末行截断：逐字符回退直到 truncated + '……' 宽度适配
                truncated = line
                while truncated and draw.textbbox((0, 0), truncated + '……', font=fonts['body'])[2] > inner_w:
                    truncated = truncated[:-1]
                draw.text((cx, cy), truncated + '……', font=fonts['body'], fill=(88, 88, 88))
                cy += LINE_SPACING_SUMMARY
                break
            else:
                draw.text((cx, cy), line, font=fonts['body'], fill=(88, 88, 88))
                cy += LINE_SPACING_SUMMARY
            if cy >= max_y:
                break


def render_digest_image(items, output_path):
    """渲染一张 digest 图片（2个卡片）"""
    bg = create_background(WIDTH, HEIGHT)
    draw = ImageDraw.Draw(bg)

    fonts = {
        'title':  load_font(FONT_TITLE, 46),
        'body':   load_font(FONT_BODY, 24),
        'source': load_font(FONT_SOURCE, 24),
    }

    card_w = WIDTH - CARD_MARGIN_X * 2

    # 计算两张卡片高度
    heights = [
        measure_card_height(item, fonts, card_w, draw)
        for item in items[:2]
    ]

    # 垂直居中：两卡 + gap 在画布中居中
    total_h = sum(heights) + CARD_GAP
    start_y = (HEIGHT - total_h) // 2

    # 卡片阴影层（先于卡片绘制，GaussianBlur 柔化）
    shadow_layer = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    for i, item in enumerate(items[:2]):
        card_y = start_y + sum(heights[:i]) + i * CARD_GAP
        sx, sy = CARD_MARGIN_X + 3, card_y + 5
        shadow_draw.rounded_rectangle(
            [sx, sy, sx + card_w, sy + heights[i]],
            radius=CARD_RADIUS, fill=(0, 0, 0, 40)
        )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(8))
    bg = Image.alpha_composite(bg.convert('RGBA'), shadow_layer).convert('RGB')
    draw = ImageDraw.Draw(bg)

    for i, item in enumerate(items[:2]):
        card_y = start_y + sum(heights[:i]) + i * CARD_GAP
        draw_card(draw, CARD_MARGIN_X, card_y, card_w, heights[i], item, fonts)

    bg.save(output_path, quality=92)
    print(f"✓ {output_path}")


def test():
    """测试（使用接近实际的完整正文，验证 6-7 行 body 渲染效果）"""
    items = [
        {
            "source": "@wwwgoubuli (李继刚)",
            "category": "AI Agent",
            "headline": "AI Agent 部署实践",
            "summary": "🤖 李继刚分享了 4 周实测报告：单人工作流借助 AI 编程助手实现 94 commits/天，7 个 PR 在 30 分钟内完成 review 与合并，从 commit 到上线 MRR 的完整闭环首次被一人跑通。他认为，真正的瓶颈不在于代码生成速度，而在于需求拆解和验收能力——这正是高级工程师的核心价值所在。一人公司时代的技术基础设施已经就位，剩下的是思维模式的转变。"
        },
        {
            "source": "simonwillison.net",
            "category": "开发方法论",
            "headline": "规范驱动开发的深层反思",
            "summary": "📝 Simon Willison 在这篇长文中探讨了 Spec-Driven Development 的局限性：你唯一能百分百信任的文档就是代码本身。规格书在编写时就开始过时，而 AI 生成的代码又加速了这一衰减。他提出「测试即规格」的替代思路——用可执行的测试用例取代散文式文档，既能验证行为又能追踪变化。这对于大量依赖 LLM 生成 PRD 的团队是一个重要警示。"
        }
    ]
    
    output = str(Path(__file__).resolve().parent.parent / "test-output" / "digest_card_test.jpg")
    render_digest_image(items, output)


if __name__ == '__main__':
    test()
