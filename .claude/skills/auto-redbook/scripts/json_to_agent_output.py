#!/usr/bin/env python3
"""Convert structured JSON output to agent output format (PART B/C) for digest pipeline.

JSON schema expected:
{
  "title_suffix": "...",    // ≤15 chars, semantic title suffix
  "items": [
    {
      "source": "...",      // 信息来源标签（tweetsave: @handle 或 twitter.com；blog: 博客域名）
      "headline": "...",    // ≤20 chars, card headline (first line of PART B segment)
      "summary": "...",     // ≤80 chars, brief summary (validation only, not in PART B)
      "body": "..."         // full body text for PART B segment (after headline)
    }
  ],
  "tags": ["..."]           // ≤5 content tags (no base tags needed)
}

Sidecar output (--sources-output):
  JSON array of per-item source labels, passed to build_digest_payload.py --sources-file
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PREFIX_MAP = {"tweetsave": "AI日报", "blog": "gegeewu日报", "gegeewu": "gegeewu日报"}
DIVIDER = "━━━━━━━━━━━━━━━"


def validate(data: dict, source_type: str) -> list[str]:
    """Validate JSON output. Returns list of warning strings."""
    warns: list[str] = []
    suffix = data.get("title_suffix", "")
    items = data.get("items", [])
    tags = data.get("tags", [])

    # title_suffix length <= 15 chars (unified for all source types)
    if len(suffix) > 15:
        warns.append(f"title_suffix 超长: '{suffix}' ({len(suffix)}字 > 15字)")

    # items count 6-8（xhs_body ≤ 850字约束，8条时每条≤85字）
    if not (6 <= len(items) <= 8):
        warns.append(f"items 数量不对: {len(items)} (应为 6-8)")

    # tags count <= 5
    if len(tags) > 5:
        warns.append(f"tags 过多: {len(tags)} (应 ≤5)")

    template_phrases = ["反映模型能力与工作流正在快速演进", "这篇文章围绕"]

    for i, item in enumerate(items):
        source = item.get("source", "")
        headline = item.get("headline", "")
        summary = item.get("summary", "")
        body = item.get("body", "")

        if not source:
            warns.append(f"item[{i}] 缺少 source")

        if not headline:
            warns.append(f"item[{i}] 缺少 headline")
        elif len(headline) > 20:
            warns.append(f"item[{i}] headline 超长: '{headline}' ({len(headline)}字 > 20字)")

        if len(summary) > 80:
            warns.append(f"item[{i}] summary 超长: {len(summary)}字 > 80字")

        if not body:
            warns.append(f"item[{i}] 缺少 body")
        else:
            # Dynamic per-item body budget based on N: ⌊(863-19×(N-1))÷N⌋
            n = len(items)
            per_item_budget = max(60, (863 - 19 * (n - 1)) // n)
            if len(body) > per_item_budget:
                warns.append(
                    f"item[{i}] body 超预算: {len(body)}字 > {per_item_budget}字"
                    f"（N={n}条时每条≤{per_item_budget}字）"
                )
            if len(body) < 60:
                warns.append(f"item[{i}] body 过短: {len(body)}字 < 60字（信息可能不足）")
            if headline and (body.startswith(headline) or headline in body):
                warns.append(f"item[{i}] body 包含 headline 内容（标题与正文必须互补，不得重叠）")
            for phrase in template_phrases:
                if phrase in body:
                    warns.append(f"item[{i}] body 命中模板句风险：{phrase}")

    # Total xhs_body length check (body content + dividers)
    DIVIDER_LEN = 19  # "\n\n━━━━━━━━━━━━━━━\n\n" = 19 chars
    total_body = sum(len(it.get("body", "")) + len(it.get("headline", "")) + 1
                     for it in items)  # +1 for \n between headline and body
    total_with_dividers = total_body + DIVIDER_LEN * (len(items) - 1)
    if total_with_dividers > 850:
        warns.append(
            f"xhs_body 总长超限: 预估 {total_with_dividers}字 > 850字"
            f"（{len(items)}条×正文 + {len(items)-1}个分隔符）"
        )

    return warns


def build_output(data: dict, source_type: str) -> str:
    """Build PART B/C text from JSON data."""
    prefix = PREFIX_MAP.get(source_type, "AI日报")

    # Build PART B: each segment = headline + newline + body, joined by dividers
    segments: list[str] = []
    for item in data.get("items", []):
        headline = item.get("headline", "").strip()
        body = item.get("body", "").strip()
        # 去重：如果 body 以 headline 开头，则去掉重复部分
        if headline and body:
            if body.startswith(headline):
                body = body[len(headline):].strip()
            if body:
                segments.append(f"{headline}\n{body}")
            else:
                segments.append(headline)
        elif headline:
            segments.append(headline)

    part_b = f"\n\n{DIVIDER}\n\n".join(segments)

    # Build PART C: TITLE + TAGS
    suffix = data.get("title_suffix", "")
    title = f"{prefix}｜{suffix}"
    tags = data.get("tags", [])
    tags_str = ", ".join(tags)
    part_c = f"TITLE: {title}\nTAGS: {tags_str}"

    return f"===PART B===\n{part_b}\n\n===PART C===\n{part_c}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert JSON to agent output (PART B/C)")
    parser.add_argument("--input", required=True, help="JSON input file")
    parser.add_argument("--output", required=True, help="Agent output txt file")
    parser.add_argument("--source-type", required=True, choices=["tweetsave", "blog", "gegeewu"])
    parser.add_argument("--sources-output", help="Optional: write per-item sources as JSON array")
    parser.add_argument("--strict", action="store_true", help="Exit with error on any warning")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))

    warns = validate(data, args.source_type)
    for w in warns:
        print(f"⚠️  {w}", file=sys.stderr)

    output = build_output(data, args.source_type)
    Path(args.output).write_text(output, encoding="utf-8")

    # Write per-item sources sidecar (used by build_digest_payload.py)
    sources_path = args.sources_output or (args.output + ".sources.json")
    sources = [item.get("source", "") for item in data.get("items", [])]
    Path(sources_path).write_text(
        json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    suffix = data.get("title_suffix", "")
    prefix = PREFIX_MAP.get(args.source_type, "AI日报")
    n_items = len(data.get("items", []))
    print(f"✅ Done: {n_items} items → title: {prefix}｜{suffix}")
    print(f"   sources: {', '.join(s for s in sources if s)}")

    if args.strict and warns:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
