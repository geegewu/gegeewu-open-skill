#!/usr/bin/env python3
"""Unified digest pipeline for tweetsave/blog-digest -> XHS digest payload."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
import json
import math
import re
import warnings as _warnings
from typing import List, Tuple


BASE_TAGS = ["gegeewu", "Gegeewu", "嗝嗝巫"]
SOURCE_TAGS = {
    "tweetsave": "AI日报",
    "blog": "gegeewu日报",
    "gegeewu": "gegeewu日报",
}
SOURCE_TITLE_PREFIX = {
    "tweetsave": "AI日报",
    "blog": "gegeewu日报",
    "gegeewu": "gegeewu日报",
}
SOURCE_FILE_RULES = {
    "tweetsave": {
        "required_dir": "ai-digests",
        "filename_re": re.compile(r"^ai-digest-\d{4}-\d{2}-\d{2}\.md$"),
    },
    "blog": {
        "required_dir": "blog-digests",
        "filename_re": re.compile(r"^\d{4}-\d{2}-\d{2}\.md$"),
    },
    "gegeewu": {
        "required_dir": None,
        "filename_re": re.compile(r"^.*\.md$"),
    },
}
DIVIDER_RE = re.compile(r"\n\s*━{5,}\s*\n")


@dataclass
class DigestPayload:
    schema_version: str
    source_type: str
    date: str
    title: str
    tags: List[str]
    xhs_body: str
    cards_text: str
    num_images: int
    rewritten: str
    run_id: str


def _extract_part(text: str, part_name: str, next_part: str | None) -> str:
    if next_part:
        pattern = rf"===PART {part_name}===(.+?)===PART {next_part}==="
    else:
        pattern = rf"===PART {part_name}===(.+)"
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else ""


def parse_agent_output(result_text: str) -> Tuple[str, str, str]:
    """Parse PART B/C from agent output. PART A is intentionally ignored for consistency."""
    part_b = _extract_part(result_text, "B", "C")
    part_c = _extract_part(result_text, "C", None)
    part_a = _extract_part(result_text, "A", "B")
    return part_a, part_b, part_c


def _strip_title_prefix(title: str) -> str:
    """Drop known digest prefixes and keep only semantic suffix."""
    m = re.match(r"^(?:AI日报|推特日报|博文日报|gegeewu日报)\s*[｜|:：-]\s*(.+)$", title)
    if m:
        return m.group(1).strip()
    return title.strip()


def _normalize_digest_title(raw_title: str, source_type: str, date_str: str) -> str:
    prefix = SOURCE_TITLE_PREFIX.get(source_type)
    if not prefix:
        raise ValueError(f"unsupported source_type: {source_type}")

    clean = (raw_title or "").strip()
    if not clean:
        return f"{prefix}｜{date_str}"

    suffix = _strip_title_prefix(clean)
    if not suffix:
        suffix = date_str
    if len(suffix) > 15:
        _warnings.warn(
            f"title_suffix 超长: '{suffix}' ({len(suffix)}字 > 15字)",
            stacklevel=3,
        )
    return f"{prefix}｜{suffix}"


def _normalized_path_parts(path_str: str) -> tuple[str, ...]:
    normalized = path_str.replace("\\", "/")
    return tuple(part for part in normalized.split("/") if part)


def validate_source_markdown_path(source_type: str, source_markdown_path: str | Path) -> None:
    """Hard gate: source markdown path must match source_type conventions."""
    rule = SOURCE_FILE_RULES.get(source_type)
    if not rule:
        raise ValueError(f"unsupported source_type: {source_type}")

    raw_path = str(source_markdown_path)
    parts = _normalized_path_parts(raw_path)
    filename = parts[-1] if parts else ""
    required_dir = rule["required_dir"]
    filename_re = rule["filename_re"]

    if required_dir and required_dir not in parts:
        raise ValueError(
            f"{source_type} source markdown must be under `{required_dir}/`, got: {raw_path}"
        )
    if not filename_re.match(filename):
        raise ValueError(
            f"{source_type} source markdown filename mismatch: {filename} "
            f"(expected pattern: {filename_re.pattern})"
        )


def parse_title_tags(meta_text: str, date_str: str, source_type: str) -> Tuple[str, List[str]]:
    title_m = re.search(r"TITLE:\s*(.+)", meta_text)
    tags_m = re.search(r"TAGS:\s*(.+)", meta_text)
    raw_title = title_m.group(1).strip() if title_m else ""
    title = _normalize_digest_title(raw_title, source_type=source_type, date_str=date_str)
    raw_tags = []
    if tags_m:
        raw_tags = [t.strip() for t in tags_m.group(1).split(",") if t.strip()]
    # Keep first 5 content tags and de-duplicate with base tags preserving order.
    source_tag = SOURCE_TAGS.get(source_type, "")
    tags = []
    for t in BASE_TAGS + ([source_tag] if source_tag else []) + raw_tags[:5]:
        if t not in tags:
            tags.append(t)
    return title, tags


def _extract_sources_from_markdown(source_markdown: str, source_type: str) -> List[str]:
    if source_type == "tweetsave":
        return ["twitter.com"]

    urls = re.findall(r"https?://([A-Za-z0-9\.\-]+\.[A-Za-z]{2,})(?:[/?#)\s]|$)", source_markdown)
    sources = []
    for u in urls:
        if u not in sources:
            sources.append(u.lower())
    return sources or ["blog.com"]


def cards_from_body(
    xhs_body: str,
    source_markdown: str,
    source_type: str,
    unified_source_label: str | None = None,
    per_item_sources: List[str] | None = None,
) -> str:
    segments = [s.strip() for s in DIVIDER_RE.split(xhs_body) if s.strip()]
    if not segments:
        return ""
    if per_item_sources:
        sources = per_item_sources
        rotate = False
    elif unified_source_label:
        sources = [unified_source_label]
        rotate = True
    else:
        sources = _extract_sources_from_markdown(source_markdown, source_type)
        rotate = True
    cards = []
    for i, seg in enumerate(segments):
        lines = [l.strip() for l in seg.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        headline = lines[0]
        # 改用完整 body（不是 80 字截断），让卡片有更多内容可展示
        body_text = " ".join(lines[1:]) if len(lines) > 1 else ""
        body_text = (body_text[:300] + "……") if len(body_text) > 300 else body_text
        source = sources[i % len(sources)] if rotate else (sources[i] if i < len(sources) else sources[-1])
        cards.append(f"🔹 {source}\n**{headline}**\n{body_text}")
    return "\n\n".join(cards)


def compute_num_images(cards_text: str) -> int:
    card_count = len(re.findall(r"^🔹\s+", cards_text, flags=re.MULTILINE))
    return max(1, min(9, math.ceil(max(card_count, 1) / 2)))


def build_rewritten(title: str, tags: List[str], xhs_body: str, cards_text: str) -> str:
    tags_str = ", ".join(tags)
    return (
        f"---\n"
        f"title: {title}\n"
        f"emoji: 📰\n"
        f"tags: [{tags_str}]\n"
        f"style: digest\n"
        f"---\n\n"
        f"{xhs_body}\n\n"
        f"---CARDS---\n"
        f"{cards_text}"
    )


def _make_run_id(source_type: str, date_str: str, title: str) -> str:
    # Stable, readable, and deterministic per daily digest title/source.
    norm_title = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "-", title).strip("-")[:40]
    return f"{source_type}-{date_str}-{norm_title or 'digest'}"


def build_payload(
    source_type: str,
    date_str: str,
    source_markdown: str,
    agent_output: str,
    unified_source_label: str | None = None,
    per_item_sources: List[str] | None = None,
) -> DigestPayload:
    _, part_b, part_c = parse_agent_output(agent_output)
    if not part_b:
        raise ValueError("Missing PART B in agent output")
    title, tags = parse_title_tags(part_c, date_str, source_type=source_type)
    cards_text = cards_from_body(
        part_b, source_markdown, source_type,
        unified_source_label=unified_source_label,
        per_item_sources=per_item_sources,
    )
    rewritten = build_rewritten(title, tags, part_b, cards_text)
    run_id = _make_run_id(source_type, date_str, title)
    return DigestPayload(
        schema_version="digest_payload.v1",
        source_type=source_type,
        date=date_str,
        title=title,
        tags=tags,
        xhs_body=part_b,
        cards_text=cards_text,
        num_images=compute_num_images(cards_text),
        rewritten=rewritten,
        run_id=run_id,
    )


def write_payload_files(payload: DigestPayload, work_dir: Path) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "rewritten.md").write_text(payload.rewritten, encoding="utf-8")
    (work_dir / "digest_cards.md").write_text(payload.cards_text, encoding="utf-8")
    (work_dir / "digest_payload.json").write_text(
        json.dumps(asdict(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")
