#!/usr/bin/env python3
"""Step 3 Pipeline: deterministic helpers for transcript → cards.json

Two modes:
  --prepare:  transcript → batches.json + meta.json (batch splitting, no LLM)
  --finalize: narrative text → equalize paragraphs → cards.json + validate

LLM processing (batch summarization + narrative reconstruction) is done by the
agent/subagent using its native model, NOT by this script.

Usage:
    # Step 1: Prepare batches
    ~/myenv/bin/python3 step3_pipeline.py --prepare \
        --transcript transcripts/2026-03-19/屠龙之术.md \
        --output-dir output/屠龙之术/

    # Step 2: Agent processes batches → narrative (see SKILL.md)

    # Step 3: Finalize cards
    ~/myenv/bin/python3 step3_pipeline.py --finalize \
        --narrative-file output/屠龙之术/narrative.md \
        --output-dir output/屠龙之术/ \
        [--min-chars 2500] [--max-chars 3200]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from pathlib import Path

# Reuse existing batch splitter
from podcast_post_pipeline import split_transcript_into_batches

SKILL_DIR = Path(__file__).parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("step3_pipeline")

DEFAULT_BATCH_SIZE_LINES = 250
DEFAULT_OVERLAP_LINES = 25


def _load_env() -> None:
    dotenv = Path.home() / ".env"
    if not dotenv.exists():
        return
    for line in dotenv.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        k = key.strip().removeprefix("export").strip()
        os.environ.setdefault(k, value.strip().strip('"').strip("'"))


def parse_transcript_meta(transcript_text: str) -> dict[str, str]:
    """Extract metadata block from transcript header (between --- markers)."""
    meta: dict[str, str] = {}
    lines = transcript_text.split("\n")
    in_meta = False
    for line in lines:
        stripped = line.strip()
        if stripped == "---":
            if in_meta:
                break
            in_meta = True
            continue
        if in_meta and stripped.startswith("**") and "**：" in stripped:
            key_end = stripped.index("**：")
            key = stripped[2:key_end]
            value = stripped[key_end + 3:]
            meta[key] = value
    return meta


def equalize_paragraphs(text: str, target_chars: int = 350) -> str:
    """Rebalance paragraphs at sentence boundaries to roughly equal length."""
    raw_paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    all_sentences: list[str] = []
    for para in raw_paras:
        parts = re.split(r'(?<=[。！？；…])', para)
        for part in parts:
            s = part.strip()
            if s:
                all_sentences.append(s)

    if not all_sentences:
        return text

    paragraphs: list[str] = []
    current = ""
    for sent in all_sentences:
        if current and len(current) + len(sent) > target_chars:
            paragraphs.append(current)
            current = sent
        else:
            current += sent
    if current:
        paragraphs.append(current)

    logger.info(f"Paragraph equalization: {len(raw_paras)} → {len(paragraphs)} paragraphs "
                f"(target {target_chars} chars, actual range "
                f"{min(len(p) for p in paragraphs)}-{max(len(p) for p in paragraphs)})")
    return "\n\n".join(paragraphs)


def validate_cards(cards: list[dict[str, str]], min_chars: int = 2500, max_chars: int = 3200) -> None:
    """Validate total card text length. Raises ValueError if out of range."""
    total = sum(len(c.get("body", "")) for c in cards)
    if total < min_chars:
        raise ValueError(f"Card text too short: {total} chars (min {min_chars}). 可适当放宽 --min-chars 重跑 finalize。")
    if total > max_chars:
        raise ValueError(f"Card text too long: {total} chars (max {max_chars}). 必须重新生成 Round 2 narrative（缩减内容），禁止放宽 --max-chars。")
    logger.info(f"Card validation passed: {total} chars (range {min_chars}-{max_chars})")


def _rebalance_cards(parts: list[str], target_chars: int = 500, max_chars: int = 850) -> list[str]:
    """Dynamically merge LLM card parts to reach optimal card count.

    Calculates target card count from total text length, then iteratively
    merges the smallest adjacent pair. max_chars is the absolute ceiling
    per card — set to 850 to allow merging when LLM over-splits (e.g. 8
    cards at ~410 chars each → merge pair = ~820, must fit within ceiling).
    _limit_paragraphs_for_pixel_fit() handles the actual pixel budget later.

    Works for any narrative length (2500-3500+ chars).
    """
    if len(parts) <= 1:
        return parts

    total = sum(len(p) for p in parts)
    target_count = max(1, round(total / target_chars))
    target_count = min(target_count, len(parts), 9)

    logger.info(f"Rebalance: {len(parts)} parts, {total} chars → target {target_count} cards "
                f"({total // max(target_count, 1)} chars/card avg)")

    merged = list(parts)
    while len(merged) > target_count:
        # Find smallest adjacent pair within max_chars
        best_idx = -1
        best_combined = float('inf')
        for i in range(len(merged) - 1):
            combined = len(merged[i]) + len(merged[i + 1]) + 2
            if combined <= max_chars and combined < best_combined:
                best_combined = combined
                best_idx = i

        if best_idx < 0:
            # All pairs exceed max_chars — stop merging
            logger.warning(f"Cannot merge further without exceeding {max_chars} chars/card, "
                           f"stopped at {len(merged)} cards (target was {target_count})")
            break

        merged[best_idx] = merged[best_idx] + "\n\n" + merged[best_idx + 1]
        del merged[best_idx + 1]

    return merged


def _limit_paragraphs_for_pixel_fit(card_body: str) -> str:
    """Adaptively merge paragraphs to guarantee the card fits renderer pixel budget.

    Renderer pixel math (CARD_HEIGHT=2414, header≈416, LINE_SPACING=91, GAP=91):
      available ≈ 1998px
      N paragraphs → (N-1)*91px gaps + text_lines*91px
      text_lines ≈ total_chars / 31  (Chinese at 57px font)

    Strategy: start with max 4 paragraphs. If estimated pixel height still
    overflows, reduce to 3, then 2. This trades paragraph spacing for text room.
    """
    paras = [p.strip() for p in card_body.split("\n\n") if p.strip()]
    if len(paras) <= 1:
        return card_body.strip()

    AVAILABLE_PX = 1998  # CARD_HEIGHT(2414) - typical header(416)
    LINE_H = 91
    GAP = 91
    CHARS_PER_LINE = 31

    def _estimate_height(paragraphs: list[str]) -> int:
        total_chars = sum(len(p) for p in paragraphs)
        text_lines = max(len(paragraphs), (total_chars + CHARS_PER_LINE - 1) // CHARS_PER_LINE)
        gaps = (len(paragraphs) - 1) * GAP
        return text_lines * LINE_H + gaps

    # Try max_paras = 4, 3, 2 until it fits
    for max_paras in (4, 3, 2):
        candidate = list(paras)
        while len(candidate) > max_paras:
            # Merge shortest adjacent pair
            best_idx = 0
            best_len = float('inf')
            for i in range(len(candidate) - 1):
                combined = len(candidate[i]) + len(candidate[i + 1])
                if combined < best_len:
                    best_len = combined
                    best_idx = i
            candidate[best_idx] = candidate[best_idx] + candidate[best_idx + 1]
            del candidate[best_idx + 1]

        if _estimate_height(candidate) <= AVAILABLE_PX:
            return "\n\n".join(candidate)

    # Last resort: single paragraph
    return "".join(paras)


def _ensure_paragraphs(text: str, target_para_chars: int = 150, max_paras: int = 4) -> str:
    """If text has no paragraph breaks (\\n\\n), split at sentence boundaries.

    target_para_chars: aim for each paragraph to be roughly this many chars.
    max_paras: cap the number of resulting paragraphs (prevents over-splitting).
    The target is derived from text length so short cards get fewer, larger paragraphs.
    """
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paras) >= 2:
        return text  # Already has paragraph breaks, leave as-is

    # Single block — split at sentence boundaries
    sentences: list[str] = []
    for part in re.split(r'(?<=[。！？；…])', text):
        s = part.strip()
        if s:
            sentences.append(s)

    if not sentences:
        return text

    # Determine target paragraph size dynamically
    n_paras = max(2, min(max_paras, len(text) // target_para_chars))
    target = len(text) // n_paras

    result: list[str] = []
    current = ""
    for sent in sentences:
        if current and len(current) + len(sent) > target:
            result.append(current)
            current = sent
        else:
            current += sent
    if current:
        result.append(current)

    logger.info(
        f"_ensure_paragraphs: {len(text)} chars → {len(result)} paragraphs "
        f"(target {target} chars/para)"
    )
    return "\n\n".join(result)


def build_cards(narrative_text: str) -> list[dict[str, str]]:
    """Build cards.json structure from narrative text.

    Pipeline: LLM parts → ensure paragraph breaks per card →
              rebalance to target count → fit each card to pixel budget.
    Dynamically adapts to any narrative length (2500-3500+ chars).
    """
    seq_labels = ["一", "二", "三", "四", "五", "六", "七", "八", "九"]
    if "---CARD---" in narrative_text:
        parts = [p.strip() for p in narrative_text.split("---CARD---") if p.strip()]
        # Guarantee each card has \n\n paragraph breaks before pixel fitting.
        # _ensure_paragraphs is a no-op when breaks already exist; it only
        # kicks in when the LLM collapses the card into a single paragraph block.
        parts = [_ensure_paragraphs(p) for p in parts]
        parts = _rebalance_cards(parts, target_chars=500)
        parts = [_limit_paragraphs_for_pixel_fit(p) for p in parts]
        cards = [{"seq": seq_labels[i], "body": part} for i, part in enumerate(parts[:9])]
        sizes = [len(c["body"]) for c in cards]
        logger.info(f"Built {len(cards)} cards: {sizes} (avg {sum(sizes)//len(sizes)})")
        return cards
    # Fallback: single card (renderer DP will handle overflow)
    return [{"seq": "一", "body": narrative_text}]


def cmd_prepare(args: argparse.Namespace) -> int:
    """Prepare mode: transcript → batches.json + meta.json"""
    _load_env()

    transcript_path = Path(args.transcript)
    if not transcript_path.exists():
        logger.error(f"Transcript not found: {transcript_path}")
        return 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    transcript_text = transcript_path.read_text(encoding="utf-8")
    logger.info(f"Transcript loaded: {len(transcript_text)} chars, {len(transcript_text.splitlines())} lines")

    # Parse metadata from transcript header
    meta = parse_transcript_meta(transcript_text)
    logger.info(f"Metadata: {meta}")

    # Note: key_names extraction is done by the agent (Step 3b) using its own model,
    # not by this script. meta.json is saved as-is from the transcript header.

    # Truncate at "## 纯文本" section (transcribe.py appends a plain-text duplicate)
    plain_text_marker = "\n## 纯文本"
    if plain_text_marker in transcript_text:
        original_len = len(transcript_text)
        transcript_text = transcript_text[:transcript_text.index(plain_text_marker)]
        logger.info(f"Truncated '## 纯文本' section: {original_len} → {len(transcript_text)} chars")

    # Split into batches
    batches = split_transcript_into_batches(
        transcript_text,
        batch_size=args.batch_size_lines,
        overlap=args.overlap_lines,
    )
    logger.info(
        f"Split into {len(batches)} batches "
        f"(batch_size_lines={args.batch_size_lines}, overlap_lines={args.overlap_lines})"
    )

    # Save batches.json
    batches_path = output_dir / "batches.json"
    batches_path.write_text(
        json.dumps(batches, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(f"batches.json saved: {batches_path} ({len(batches)} batches)")

    # Save meta.json
    meta_path = output_dir / "meta.json"
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(f"meta.json saved: {meta_path}")

    # Print summary for agent
    print(f"\n✅ Prepare 完成：{len(batches)} 个 batch，元信息已保存")
    print(f"   batches.json: {batches_path}")
    print(f"   meta.json: {meta_path}")
    for i, batch in enumerate(batches, start=1):
        text = batch["text"] if isinstance(batch, dict) else str(batch)
        if isinstance(batch, dict):
            print(
                f"   Batch {i}: {len(text)} chars "
                f"(lines {batch['start_line']}-{batch['end_line']}, "
                f"core {batch['core_start_line']}-{batch['core_end_line']})"
            )
        else:
            print(f"   Batch {i}: {len(text)} chars")

    return 0


def cmd_finalize(args: argparse.Namespace) -> int:
    """Finalize mode: narrative text → equalize → cards.json + validate"""
    output_dir = Path(args.output_dir)

    narrative_path = Path(args.narrative_file)
    if not narrative_path.exists():
        logger.error(f"Narrative file not found: {narrative_path}")
        return 1

    narrative = narrative_path.read_text(encoding="utf-8").strip()
    logger.info(f"Narrative loaded: {len(narrative)} chars")

    # Build cards (if ---CARD--- separators present, split into multiple cards)
    cards = build_cards(narrative)

    # Validate
    try:
        validate_cards(cards, min_chars=args.min_chars, max_chars=args.max_chars)
    except ValueError as e:
        logger.error(f"Validation failed: {e}")
        cards_path = output_dir / "cards.json"
        cards_path.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"Cards saved (FAILED validation): {cards_path}")
        return 1

    # Per-card minimum character check
    MIN_CARD_CHARS = 450
    short_cards = [
        (i + 1, len(c["body"])) for i, c in enumerate(cards) if len(c["body"]) < MIN_CARD_CHARS
    ]
    if short_cards:
        cards_path = output_dir / "cards.json"
        cards_path.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
        for card_no, char_count in short_cards:
            logger.error(f"Card {card_no} 字符数不足：{char_count} < {MIN_CARD_CHARS}（填充率不达标）")
        print(f"\n❌ Finalize 失败：{len(short_cards)} 张卡片字符数不足 {MIN_CARD_CHARS}（详见上方日志）。请重跑 Round 3 分卡，确保每张卡 ≥{MIN_CARD_CHARS} 字符。")
        return 1

    # Save cards.json
    cards_path = output_dir / "cards.json"
    cards_path.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")

    total_chars = sum(len(c["body"]) for c in cards)
    logger.info(f"cards.json saved: {cards_path}")
    print(f"\n✅ Finalize 完成：{total_chars} chars, {len(cards)} card(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Step 3 Pipeline helpers")
    sub = parser.add_subparsers(dest="command")

    # --prepare
    p_prepare = sub.add_parser("prepare", help="Split transcript into batches + extract metadata")
    p_prepare.add_argument("--transcript", required=True, help="Path to transcript .md file")
    p_prepare.add_argument("--output-dir", required=True, help="Output directory")
    p_prepare.add_argument(
        "--batch-size-lines",
        type=int,
        default=DEFAULT_BATCH_SIZE_LINES,
        help=f"Approximate lines per batch before overlap (default: {DEFAULT_BATCH_SIZE_LINES})",
    )
    p_prepare.add_argument(
        "--overlap-lines",
        type=int,
        default=DEFAULT_OVERLAP_LINES,
        help=f"Context overlap lines between adjacent batches (default: {DEFAULT_OVERLAP_LINES})",
    )

    # --finalize
    p_finalize = sub.add_parser("finalize", help="Equalize paragraphs + build cards.json + validate")
    p_finalize.add_argument("--narrative-file", required=True, help="Path to narrative .md file")
    p_finalize.add_argument("--output-dir", required=True, help="Output directory")
    p_finalize.add_argument("--min-chars", type=int, default=2500, help="Min total chars")
    p_finalize.add_argument("--max-chars", type=int, default=3500, help="Max total chars")

    args = parser.parse_args()

    if args.command == "prepare":
        return cmd_prepare(args)
    elif args.command == "finalize":
        return cmd_finalize(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
