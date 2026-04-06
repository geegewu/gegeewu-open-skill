#!/usr/bin/env python3
"""
小红书笔记图片渲染脚本 - Gemini 版本
使用 nano-banana-pro (Gemini 3 Pro Image) 生成小红书风格的图片卡片

使用方法:
    python render_xhs_gemini.py <markdown_file> [options]

参数:
    --output-dir, -o    输出目录（默认：当前工作目录）
    --theme, -t         主题风格（默认：minimalist）
    --resolution        图片分辨率：1K/2K/4K（默认：2K）
    --api-key           Gemini API Key（可选，默认从环境变量读取）

示例:
    python render_xhs_gemini.py content.md
    python render_xhs_gemini.py content.md -o ./output -t gradient --resolution 4K
"""

import argparse
import os
import re
import sys
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

# 尝试导入 yaml 库（用于解析 YAML front matter）
try:
    import yaml
except ImportError:
    print("警告: 缺少 pyyaml 库，使用简化的 YAML 解析")
    yaml = None


def parse_yaml_front_matter(content: str) -> tuple[Dict, str]:
    """解析 YAML front matter"""
    if not content.startswith('---'):
        return {}, content
    
    parts = content.split('---', 2)
    if len(parts) < 3:
        return {}, content
    
    yaml_str = parts[1].strip()
    body = parts[2].strip()
    
    # 使用 yaml 库解析
    if yaml:
        try:
            metadata = yaml.safe_load(yaml_str)
            return metadata or {}, body
        except Exception as e:
            print(f"YAML 解析失败: {e}")
    
    # 简化解析（fallback）
    metadata = {}
    for line in yaml_str.split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            metadata[key.strip()] = value.strip().strip('"\'')
    
    return metadata, body


def split_content_by_separator(content: str) -> List[str]:
    """按 --- 分隔符切分内容"""
    # 移除 front matter 后的内容才进行分割
    segments = re.split(r'\n---+\n', content)
    return [seg.strip() for seg in segments if seg.strip()]


def generate_cover_prompt(metadata: Dict, theme: str = "minimalist") -> str:
    """生成封面图片的 Gemini prompt"""
    emoji = metadata.get('emoji', '✨')
    title = metadata.get('title', '小红书笔记')
    
    theme_styles = {
        "minimalist": "简约风格，浅色渐变背景（#f3f3f3 到 #f9f9f9），圆角白色卡片",
        "gradient": "活力渐变风格，彩色渐变背景，明亮配色",
        "professional": "专业商务风格，深色背景，金色点缀",
        "playful": "活泼几何风格，Memphis 设计，多彩几何图形",
        "botanical": "植物园自然风格，绿色植物元素，有机形态",
    }
    
    style_desc = theme_styles.get(theme, theme_styles["minimalist"])
    
    prompt = f"""Create a Xiaohongshu (Little Red Book) style cover image with the following elements:

Layout: Vertical 3:4 aspect ratio (1080x1440px or similar)
Style: {style_desc}

Content:
- Large emoji at the top: {emoji}
- Main title (centered, bold, large font): {title}

Design requirements:
- Clean layout with generous whitespace
- Modern typography
- High contrast text for readability
- Rounded corners on content card
- Subtle shadow or border effects
- Professional and attractive visual appeal

DO NOT include any other text, watermarks, or decorative elements.
Keep the design clean and focused on the emoji and title.
"""
    
    return prompt


def generate_card_prompt(content: str, card_number: int, theme: str = "minimalist") -> str:
    """生成正文卡片的 Gemini prompt"""
    theme_styles = {
        "minimalist": "简约风格，浅灰渐变背景，白色内容卡片，黑色文字",
        "gradient": "活力渐变风格，彩色渐变背景，白色卡片，深色文字",
        "professional": "专业商务风格，深色背景，浅色卡片，专业排版",
        "playful": "活泼几何风格，Memphis 几何元素背景，白色卡片",
        "botanical": "植物园风格，绿色植物元素背景，米白卡片",
    }
    
    style_desc = theme_styles.get(theme, theme_styles["minimalist"])
    
    # 简化 Markdown 内容（移除不必要的格式）
    simplified_content = content.replace('**', '').replace('*', '').strip()
    
    prompt = f"""Create a Xiaohongshu (Little Red Book) style content card image (card #{card_number}):

Layout: Vertical 3:4 aspect ratio (1080x1440px or similar)
Style: {style_desc}

Content to display (preserve the structure and formatting):
{simplified_content}

Design requirements:
- Content card with rounded corners centered in the image
- Generous padding inside the card (40-60px)
- Line height 1.6-1.8 for good readability
- Clear typography hierarchy (headings larger, bold)
- Support for bullet points and numbered lists
- Code blocks (if any) should have light gray background
- Blockquotes should have left border accent
- Bottom margin should allow space for "swipe for more" hint if needed

Typography:
- Headings: 28-32px, bold
- Body text: 20-24px, regular weight
- Lists: properly indented with bullets/numbers
- Consistent spacing between sections

DO NOT add page numbers, watermarks, or decorative text outside the content.
The background should match the theme but keep focus on the content card.
"""
    
    return prompt


def call_nano_banana_pro(prompt: str, filename: str, resolution: str = "2K", 
                         api_key: Optional[str] = None, input_image: Optional[str] = None) -> bool:
    """调用 nano-banana-pro 生成图片"""
    # 尝试多个可能的路径
    possible_paths = [
        Path(__file__).resolve().parent.parent.parent / "nano-banana-pro" / "scripts" / "generate_image.py",
        Path.home() / "gegeewu-skills/.claude/skills/nano-banana-pro/scripts/generate_image.py",
    ]
    
    nano_banana_script = None
    for path in possible_paths:
        if path.exists():
            nano_banana_script = str(path)
            break
    
    if not nano_banana_script:
        print(f"错误: nano-banana-pro 脚本未找到，尝试的路径：")
        for p in possible_paths:
            print(f"  - {p}")
        return False
    
    # 构建命令
    cmd = [
        "uv", "run", nano_banana_script,
        "--prompt", prompt,
        "--filename", filename,
        "--resolution", resolution
    ]
    
    if api_key:
        cmd.extend(["--api-key", api_key])
    
    if input_image:
        cmd.extend(["--input-image", input_image])
    
    # 执行命令
    try:
        print(f"生成图片: {filename}...")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"✓ 成功: {filename}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ 生成失败: {filename}")
        print(f"错误: {e.stderr}")
        return False


def main():
    parser = argparse.ArgumentParser(description="使用 Gemini 生成小红书风格图片")
    parser.add_argument("markdown_file", help="Markdown 文件路径")
    parser.add_argument("-o", "--output-dir", default=".", help="输出目录（默认：当前目录）")
    parser.add_argument("-t", "--theme", default="minimalist", 
                       choices=["minimalist", "gradient", "professional", "playful", "botanical"],
                       help="主题风格")
    parser.add_argument("--resolution", default="2K", choices=["1K", "2K", "4K"],
                       help="图片分辨率（默认：2K）")
    parser.add_argument("--api-key", help="Gemini API Key")
    
    args = parser.parse_args()
    
    # 检查输入文件
    md_file = Path(args.markdown_file)
    if not md_file.exists():
        print(f"错误: 文件不存在: {md_file}")
        sys.exit(1)
    
    # 创建输出目录
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 读取 Markdown 文件
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 解析 YAML front matter
    metadata, body = parse_yaml_front_matter(content)
    
    print(f"\n=== 小红书图片生成 ===")
    print(f"输入文件: {md_file}")
    print(f"输出目录: {output_dir}")
    print(f"主题风格: {args.theme}")
    print(f"分辨率: {args.resolution}")
    print()
    
    # 1. 生成封面
    print("1. 生成封面...")
    cover_prompt = generate_cover_prompt(metadata, args.theme)
    cover_file = output_dir / "cover.png"
    
    if not call_nano_banana_pro(cover_prompt, str(cover_file), args.resolution, args.api_key):
        print("封面生成失败，继续生成正文卡片...")
    
    # 2. 切分正文内容
    segments = split_content_by_separator(body)
    
    if not segments:
        print("警告: 正文内容为空")
        return
    
    print(f"\n2. 生成 {len(segments)} 张正文卡片...")
    
    # 3. 生成正文卡片
    success_count = 0
    for i, segment in enumerate(segments, 1):
        card_prompt = generate_card_prompt(segment, i, args.theme)
        card_file = output_dir / f"card_{i}.png"
        
        if call_nano_banana_pro(card_prompt, str(card_file), args.resolution, args.api_key):
            success_count += 1
    
    print(f"\n=== 完成 ===")
    print(f"成功生成: {success_count + 1}/{len(segments) + 1} 张图片")
    print(f"输出目录: {output_dir.absolute()}")
    

if __name__ == "__main__":
    main()
