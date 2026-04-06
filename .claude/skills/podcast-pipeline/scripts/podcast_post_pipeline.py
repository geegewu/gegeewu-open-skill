#!/usr/bin/env python3
"""Podcast transcript batching + card rendering + Telegram delivery utilities."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path
from typing import Any

import requests

from podcast_card_renderer import render_podcast_cards

CHINESE_NUMERALS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十"]


def load_env() -> None:
    dotenv_path = Path.home() / ".env"
    if not dotenv_path.exists():
        return
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def split_transcript_into_batches(transcript_text: str, batch_size: int = 250, overlap: int = 25) -> list[dict[str, Any]]:
    """按行数动态分批，输出带 overlap 元信息的批次清单。"""
    lines = transcript_text.split("\n")
    content_lines = [l for l in lines if l.strip() and not l.startswith("#")]
    if not content_lines:
        return []
    n_batches = max(2, math.ceil(len(content_lines) / batch_size))
    batch_line_count = math.ceil(len(content_lines) / n_batches)
    batches: list[dict[str, Any]] = []
    for i in range(n_batches):
        core_start = i * batch_line_count
        core_end = min(len(content_lines), (i + 1) * batch_line_count)
        if core_start >= core_end:
            continue
        start = max(0, core_start - overlap)
        end = min(len(content_lines), core_end + overlap)
        chunk = content_lines[start:end]
        if chunk:
            batches.append({
                "batch": i + 1,
                "start_line": start + 1,
                "end_line": end,
                "core_start_line": core_start + 1,
                "core_end_line": core_end,
                "overlap_lines": overlap,
                "text": "\n".join(chunk),
            })
    print(f"[info] 转录文本 {len(content_lines)} 行 → {n_batches} 批，每批约 {batch_line_count}+{overlap*2} 行（含重叠）")
    return batches


def strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\\s*", "", text)
        text = re.sub(r"\\s*```$", "", text)
    return text.strip()


def parse_card_paragraphs(raw_text: str) -> list[dict[str, str]]:
    cleaned = strip_code_fence(raw_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start == -1 or end == -1 or end <= start:
            raise
        data = json.loads(cleaned[start : end + 1])

    if not isinstance(data, list):
        raise ValueError("Card paragraph response is not a JSON list")

    cards: list[dict[str, str]] = []
    for idx, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            continue
        body = str(item.get("body", "")).strip()
        if not body:
            continue
        seq = item.get("seq")
        if not seq:
            seq = to_chinese_numeral(idx)
        cards.append({"seq": str(seq), "body": body})
    if not cards:
        raise ValueError("No valid card paragraphs parsed from input")
    return cards


def validate_cards(cards: list[dict[str, str]], min_chars: int = 2500, max_chars: int = 3000) -> None:
    """Validate total card text length. Raises ValueError if out of range."""
    total = sum(len(c.get("body", "")) for c in cards)
    if total < min_chars:
        raise ValueError(f"Card text too short: {total} chars (min {min_chars})")
    if total > max_chars:
        raise ValueError(f"Card text too long: {total} chars (max {max_chars})")


def to_chinese_numeral(index: int) -> str:
    if 1 <= index <= len(CHINESE_NUMERALS):
        return CHINESE_NUMERALS[index - 1]
    tens, ones = divmod(index, 10)
    if tens == 0:
        return str(index)
    if tens == 1:
        return "十" if ones == 0 else f"十{CHINESE_NUMERALS[ones - 1]}"
    prefix = CHINESE_NUMERALS[tens - 1] if tens <= len(CHINESE_NUMERALS) else str(tens)
    return prefix + "十" + (CHINESE_NUMERALS[ones - 1] if ones else "")


def send_telegram_photo(token: str, chat_id: str, photo_path: str, caption: str = "") -> None:
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    with open(photo_path, "rb") as photo_file:
        response = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption},
            files={"photo": photo_file},
            timeout=120,
        )
    response.raise_for_status()


def send_telegram_text(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=60)
    response.raise_for_status()


import re

# Patterns that mean "podcast/show" in any language — stripped and replaced with "播客"
_PODCAST_SUFFIXES = re.compile(
    r"\s*(?:podcast|pod|show|播客|電台|电台)\s*$", re.IGNORECASE
)


def _format_source_name(name: str, source_type: str = "") -> str:
    """Format display name: YouTube → bare name; RSS → ensure '播客' suffix without duplication."""
    if source_type == "youtube_subtitle":
        return name
    # Strip existing podcast-like suffix, then append unified "播客"
    clean = _PODCAST_SUFFIXES.sub("", name).strip()
    if clean:
        return f"{clean} 播客"
    return f"{name} 播客"


BANNED_PHRASES = [
    "听完最大的感受是",
    "这期让我印象最深的是",
    "我听完最大的感受",
    "我认同", "我记下来了",
    "一边听一边想到自己",
    "综上所述", "值得关注的是", "不得不说",
    "未来属于那些",
    "核心判断很直接",
]


def check_banned_phrases(text: str) -> list[str]:
    """Return list of banned phrases found in text."""
    return [p for p in BANNED_PHRASES if p in text]


def normalize_paragraphs(text: str) -> str:
    """Normalize paragraph spacing: exactly one blank line between paragraphs.

    - Collapses 3+ consecutive newlines into 2 (one blank line)
    - Converts single newlines within a paragraph into spaces (unless it's a list/bullet)
    - Strips leading/trailing whitespace from each paragraph
    """
    import re
    # First collapse 3+ newlines into exactly 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Split into paragraphs by double newline
    paragraphs = text.split('\n\n')
    normalized = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # Within a paragraph, collapse single newlines into spaces
        # (preserves intentional structure like bullet lists starting with - or •)
        lines = para.split('\n')
        if len(lines) > 1 and not any(l.strip().startswith(('-', '•', '·')) for l in lines[1:]):
            para = ' '.join(l.strip() for l in lines if l.strip())
        normalized.append(para)
    return '\n\n'.join(normalized)


def send_cards_and_text(
    output_dir: str,
    podcast_name: str,
    title_cn: str,
    chat_id: str,
    token: str,
    source_type: str = "",
) -> None:
    """统一发送卡片图片 + 文案 + tags，发送路径唯一，避免重复。"""
    output_path = Path(output_dir)

    display_name = _format_source_name(podcast_name, source_type)
    title_msg = f"{title_cn} - {display_name}"
    send_telegram_text(token, chat_id, title_msg)

    card_files = sorted(output_path.glob("podcast_card_*.png"))
    if not card_files:
        raise FileNotFoundError(f"No podcast_card_*.png found in {output_dir}")

    # Sanity check: compare png count with cards.json to prevent sending stale images
    cards_json_path = output_path / "cards.json"
    if cards_json_path.exists():
        import json as _json
        _cards = _json.loads(cards_json_path.read_text(encoding="utf-8"))
        if len(card_files) > len(_cards) * 3:
            raise RuntimeError(
                f"PNG count ({len(card_files)}) far exceeds cards.json count ({len(_cards)}). "
                f"Stale images likely present — re-run render_podcast_cards() first."
            )

    for card_path in card_files:
        send_telegram_photo(token, chat_id, str(card_path))

    social_path = output_path / "social.txt"
    tags_path = output_path / "tags.txt"
    social_text = social_path.read_text(encoding="utf-8").strip() if social_path.exists() else ""
    tags_text = tags_path.read_text(encoding="utf-8").strip() if tags_path.exists() else ""

    if social_text or tags_text:
        # 去掉 social_text 末尾可能已有的 "by gegeewu 🦉"，统一重组格式
        body = social_text.rstrip()
        if body.endswith("by gegeewu 🦉"):
            body = body[: -len("by gegeewu 🦉")].rstrip()

        # 段落归一化：确保段落间恰好一个空行（\n\n），去除多余空行和段内换行
        body = normalize_paragraphs(body)

        # Banned phrase check: raise so agent must rewrite
        violations = check_banned_phrases(body)
        if violations:
            raise ValueError(
                f"社交文案包含禁止短语，必须重写：{violations}。"
                f"参考 reference/writing-guide.md「社交文案写作原则」。"
            )

        parts = [body, "by gegeewu 🦉"]
        if tags_text:
            parts.append(tags_text)
        combined = "\n\n".join(parts)
        send_telegram_text(token, chat_id, combined)


def ensure_signature(social_text: str) -> str:
    """Strip trailing signature if already present; signature is added at send time."""
    text = social_text.rstrip()
    if text.endswith("by gegeewu 🦉"):
        text = text[: -len("by gegeewu 🦉")].rstrip()
    return text


def generate_outputs(
    transcript_text: str,
    podcast_name: str,
    title_cn: str,
    output_dir: str,
    *,
    cards: list[dict[str, str]] | None = None,
    card_json_text: str | None = None,
    social_text: str = "",
    tags: str = "",
) -> dict[str, Any]:
    batches = split_transcript_into_batches(transcript_text)

    if cards is None:
        if not card_json_text:
            raise ValueError("cards or card_json_text is required")
        cards = parse_card_paragraphs(card_json_text)

    image_paths = render_podcast_cards(cards=cards, podcast_name=podcast_name, title_cn=title_cn, output_dir=output_dir)
    social_text = ensure_signature(social_text)

    return {
        "batches": batches,
        "cards": cards,
        "image_paths": image_paths,
        "social_text": social_text,
        "tags": tags.strip(),
        "batch_count": len(batches),
        "social_text_len": len(social_text),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Podcast transcript batching + card rendering pipeline")
    parser.add_argument("--transcript", help="Path to transcript markdown/text file")
    parser.add_argument("--podcast-name", help="Podcast name shown on the card")
    parser.add_argument("--title-cn", help="Chinese title shown on the cards")
    parser.add_argument("--output-dir", help="Directory for rendered card images")
    parser.add_argument("--cards-json", help="Path to JSON file containing card paragraphs")
    parser.add_argument("--social-text-file", help="Path to text file containing pre-generated social text")
    parser.add_argument("--tags-file", help="Path to text file containing pre-generated tags")
    parser.add_argument("--telegram-token", default=os.environ.get("TELEGRAM_BOT_TOKEN"), help="Telegram bot token")
    parser.add_argument("--chat-id", default=os.environ.get("TELEGRAM_CHAT_ID"), help="Telegram chat id")
    parser.add_argument("--send", action="store_true", help="Only send existing cards and text (skip generation)")
    parser.add_argument("--output-dir-send", default=None, help="Output dir to send from (used with --send)")
    parser.add_argument("--podcast-name-send", default=None, help="Podcast name for title (used with --send)")
    parser.add_argument("--title-cn-send", default=None, help="Chinese title (used with --send)")
    parser.add_argument("--dry-run", action="store_true", help="Skip Telegram sending and only print outputs")
    return parser.parse_args()


def main() -> int:
    load_env()
    args = parse_args()

    if args.send:
        load_env()
        token = args.telegram_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = args.chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN required for --send mode")
        send_cards_and_text(
            output_dir=args.output_dir_send or args.output_dir or ".",
            podcast_name=args.podcast_name_send or args.podcast_name or "",
            title_cn=args.title_cn_send or args.title_cn or "",
            chat_id=chat_id,
            token=token,
        )
        return 0

    required_args = {
        "--transcript": args.transcript,
        "--podcast-name": args.podcast_name,
        "--title-cn": args.title_cn,
        "--output-dir": args.output_dir,
    }
    missing_args = [name for name, value in required_args.items() if not value]
    if missing_args:
        raise RuntimeError(f"Missing required arguments: {', '.join(missing_args)}")

    transcript_path = Path(args.transcript)
    transcript_text = transcript_path.read_text(encoding="utf-8")

    card_json_text = Path(args.cards_json).read_text(encoding="utf-8") if args.cards_json else None
    social_text = Path(args.social_text_file).read_text(encoding="utf-8") if args.social_text_file else ""
    tags = Path(args.tags_file).read_text(encoding="utf-8") if args.tags_file else ""

    result = generate_outputs(
        transcript_text=transcript_text,
        podcast_name=args.podcast_name,
        title_cn=args.title_cn,
        output_dir=args.output_dir,
        card_json_text=card_json_text,
        social_text=social_text,
        tags=tags,
    )

    print(f"Generated {len(result['image_paths'])} card images")
    print(f"Batch count: {result['batch_count']}")
    print(f"Social text length: {result['social_text_len']}")
    print("Image paths:")
    for path in result["image_paths"]:
        print(path)
    print("\n=== Social Text ===\n")
    print(result["social_text"])
    print("\n=== Tags ===\n")
    print(result["tags"])

    output_path = Path(args.output_dir)
    if result["social_text"]:
        (output_path / "social.txt").write_text(result["social_text"], encoding="utf-8")
    if result["tags"]:
        (output_path / "tags.txt").write_text(result["tags"], encoding="utf-8")

    if args.dry_run:
        return 0

    if not args.telegram_token or not args.chat_id:
        raise RuntimeError("telegram-token and chat-id are required unless --dry-run is used")

    send_cards_and_text(
        output_dir=args.output_dir,
        podcast_name=args.podcast_name,
        title_cn=args.title_cn,
        chat_id=str(args.chat_id),
        token=args.telegram_token,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
