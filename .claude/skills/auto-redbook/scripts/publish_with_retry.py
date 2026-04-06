#!/usr/bin/env python3
"""
小红书发帖脚本 - 支持独立步骤重试
每个步骤独立运行，失败后可单独重试，不影响其他步骤

步骤：
1. 生成文案（可选，或使用已有）
2. 生成图片（可选，或使用已有）
3. 发布笔记（必须）

使用方式：
  # 完整流程
  python publish_with_retry.py --full --title "测试" --private

  # 只生成文案
  python publish_with_retry.py --content-only --title "测试"

  # 只生成图片（需要已有文案）
  python publish_with_retry.py --image-only --content-file content.txt

  # 只发布（需要已有文案和图片）
  python publish_with_retry.py --publish-only --content-file content.txt --images cover.png --private
"""
import argparse
import json
import os
import random
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# 路径配置
SKILL_DIR = Path(__file__).parent.parent
NANO_SCRIPT = str(Path(__file__).resolve().parent.parent.parent / "nano-banana-pro" / "scripts" / "generate_image.py")
PUBLISH_SCRIPT = SKILL_DIR / "scripts" / "publish_xhs.py"
STATE_FILE = Path.cwd() / ".xhs_state.json"

def _load_api_keys():
    """Load Gemini API keys from environment variables."""
    dotenv = Path.home() / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    keys_str = os.environ.get("GEMINI_API_KEYS", "")
    if keys_str:
        return [k.strip() for k in keys_str.split(",") if k.strip()]
    single = os.environ.get("GEMINI_API_KEY", "")
    if single:
        return [single]
    print("❌ 未找到 GEMINI_API_KEYS 或 GEMINI_API_KEY 环境变量")
    sys.exit(1)

API_KEYS = _load_api_keys()


def save_state(state):
    """保存状态到文件"""
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print(f"💾 状态已保存: {STATE_FILE}")


def load_state():
    """加载已保存的状态"""
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def generate_content(title=None):
    """生成小红书文案（参考原始格式）"""
    print("\n📝 生成小红书文案...\n")

    # 随机 emoji
    emojis = ["✨", "🎨", "💡", "🚀", "🔥", "⭐", "💫", "🌟"]
    emoji = random.choice(emojis)

    # 标题
    if not title:
        topics = ["AI 工具", "效率神器", "设计灵感", "技术分享", "创意想法"]
        title = random.choice(topics)

    # 副标题
    subtitles = [
        "分享一个超赞的发现",
        "让工作效率翻倍",
        "简单又实用",
        "强烈推荐收藏",
        "新手也能轻松上手"
    ]
    subtitle = random.choice(subtitles)

    # 正文模板（参考原始 example.md 格式）
    content_templates = [
        f"""# {emoji} {title}

**{subtitle}**

> 今天给大家分享一个超实用的工具，真的太好用了！

## ✨ 为什么推荐

- 操作简单，零门槛上手
- 功能强大，满足各种需求
- 设计精美，视觉体验一流

## 💡 使用场景

无论是日常工作还是学习提升，这个工具都能帮到你。特别适合追求效率的朋友们！

#AI工具 #效率提升 #小红书分享""",

        f"""# {emoji} {title}

**{subtitle}**

> 发现了一个宝藏工具，必须分享给大家！

## 🎯 核心亮点

- 界面清爽，操作流畅
- 功能丰富，持续更新
- 社区活跃，问题秒解决

## 🌈 我的体验

用了一段时间，真的爱不释手。强烈推荐给有同样需求的小伙伴！

#工具推荐 #生产力 #干货分享"""
    ]

    content = random.choice(content_templates)

    # 保存文案
    content_file = Path.cwd() / "xhs_content.txt"
    title_line = f"{title} {emoji}\n"
    with open(content_file, 'w', encoding='utf-8') as f:
        f.write(title_line)
        f.write(content)

    print(f"✓ 文案已生成并保存: {content_file}")
    print(f"  标题: {title} {emoji}")
    print(f"  正文: {len(content)} 字\n")

    return str(content_file), title_line.strip(), content


def generate_image(api_key=None):
    """生成小红书配图"""
    print("\n🎨 生成小红书配图...\n")

    # 随机选择 API Key
    if not api_key:
        api_key = random.choice(API_KEYS)

    # 简单物体提示词（Apple tech 风格）
    objects = [
        "A simple blue sphere with soft shadows on white background, Apple minimalist style, clean and premium",
        "A geometric cube with subtle gradient, Apple design aesthetic, ultra-clean composition",
        "A smooth rounded rectangle with depth, Apple product photography style, professional lighting",
        "Abstract flowing curves in blue and purple gradient, Apple wallpaper style, minimal and elegant",
        "A simple coffee cup on white surface, Apple product photo style, soft shadows and clean background"
    ]

    prompt = random.choice(objects)
    image_file = Path.cwd() / f"xhs_cover_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

    print(f"提示词: {prompt[:60]}...")
    print(f"输出: {image_file.name}\n")

    try:
        cmd = [
            "uv", "run", NANO_SCRIPT,
            "--prompt", prompt,
            "--filename", str(image_file),
            "--resolution", "2K",
            "--api-key", api_key
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)

        if result.returncode == 0 and image_file.exists():
            size_mb = image_file.stat().st_size / 1024 / 1024
            print(f"✓ 图片生成成功: {image_file.name} ({size_mb:.1f}MB)\n")
            return str(image_file)
        else:
            print(f"✗ 图片生成失败")
            print(f"错误: {result.stderr[:200]}\n")
            return None

    except subprocess.TimeoutExpired:
        print("✗ 图片生成超时\n")
        return None
    except Exception as e:
        print(f"✗ 图片生成异常: {e}\n")
        return None


def publish_note(title, content, images, private=False):
    """发布小红书笔记"""
    print("\n🚀 发布小红书笔记...\n")

    if private:
        print("🔒 私密模式：仅自己可见\n")

    cmd = [
        sys.executable,
        str(PUBLISH_SCRIPT),
        "--title", title,
        "--desc", content,
        "--images", *images
    ]

    if private:
        cmd.append("--private")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print("✓ 发布成功！\n")
        print(result.stdout)
        return True
    else:
        print("✗ 发布失败\n")
        print(result.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="小红书发帖 - 支持独立步骤重试")

    # 运行模式
    parser.add_argument("--full", action="store_true", help="完整流程（文案→图片→发布）")
    parser.add_argument("--content-only", action="store_true", help="只生成文案")
    parser.add_argument("--image-only", action="store_true", help="只生成图片")
    parser.add_argument("--publish-only", action="store_true", help="只发布（需要已有文案和图片）")

    # 参数
    parser.add_argument("--title", help="笔记标题")
    parser.add_argument("--content-file", help="已有的文案文件路径")
    parser.add_argument("--images", nargs="+", help="已有的图片路径")
    parser.add_argument("--private", action="store_true", help="发布为私密笔记")
    parser.add_argument("--api-key", help="指定 Gemini API Key")

    args = parser.parse_args()

    # 加载已保存的状态
    state = load_state()

    print("=== 小红书发帖工具（独立步骤重试）===\n")

    # 步骤 1：生成文案
    if args.full or args.content_only:
        content_file, title, content = generate_content(args.title)
        state['content_file'] = content_file
        state['title'] = title
        state['content'] = content
        save_state(state)

        if args.content_only:
            print("✅ 文案生成完成！")
            return

    # 步骤 2：生成图片
    if args.full or args.image_only:
        image_path = generate_image(args.api_key)

        if image_path:
            if 'images' not in state:
                state['images'] = []
            state['images'].append(image_path)
            save_state(state)
        else:
            print("❌ 图片生成失败")
            print("💡 提示：稍后可以单独重试图片生成")
            print(f"   命令: python {Path(__file__).name} --image-only\n")
            if not args.full:
                sys.exit(1)

        if args.image_only:
            print("✅ 图片生成完成！")
            return

    # 步骤 3：发布笔记
    if args.full or args.publish_only:
        # 获取文案
        if args.content_file:
            with open(args.content_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                title = lines[0].strip()
                content = ''.join(lines[1:])
        elif 'title' in state and 'content' in state:
            title = state['title']
            content = state['content']
        else:
            print("❌ 未找到文案，请先生成文案或指定 --content-file")
            sys.exit(1)

        # 获取图片
        if args.images:
            images = args.images
        elif 'images' in state and state['images']:
            images = state['images']
        else:
            print("❌ 未找到图片，请先生成图片或指定 --images")
            sys.exit(1)

        # 发布
        success = publish_note(title, content, images, args.private)

        if success:
            print("✅ 发布完成！")
            # 清理状态文件
            if STATE_FILE.exists():
                STATE_FILE.unlink()
        else:
            print("❌ 发布失败")
            print("💡 提示：稍后可以单独重试发布")
            print(f"   命令: python {Path(__file__).name} --publish-only --content-file {state.get('content_file', 'content.txt')} --images {' '.join(images)}\n")
            sys.exit(1)


if __name__ == "__main__":
    main()
