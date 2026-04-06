#!/usr/bin/env python3
"""Build unified digest payload + rewritten artifacts from source markdown and agent output."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from digest_pipeline import build_payload, validate_source_markdown_path, write_payload_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Build digest payload for XHS publishing")
    parser.add_argument("--source-type", choices=["tweetsave", "blog", "gegeewu"], required=True)
    parser.add_argument("--source-markdown", required=True, help="Input digest markdown path")
    parser.add_argument("--agent-output", required=True, help="Text file containing PART B/C or PART A/B/C")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument(
        "--unified-source-label",
        default="",
        help="Force all card source labels to this value for cross-input consistency",
    )
    parser.add_argument(
        "--work-dir",
        default=str(Path(__file__).parent.parent),
        help="Output directory (default: auto-redbook skill dir)",
    )
    args = parser.parse_args()

    source_md = Path(args.source_markdown)
    output_txt = Path(args.agent_output)
    work_dir = Path(args.work_dir)

    if not source_md.exists():
        raise SystemExit(f"source markdown not found: {source_md}")
    if not output_txt.exists():
        raise SystemExit(f"agent output not found: {output_txt}")

    # Hard gate: source_type must match source markdown path/filename convention.
    try:
        validate_source_markdown_path(args.source_type, source_md)
    except ValueError as e:
        print(f"❌ digest source hard gate failed: {e}")
        return 2

    source_markdown = source_md.read_text(encoding="utf-8")
    agent_output = output_txt.read_text(encoding="utf-8")

    # Auto-detect per-item sources sidecar written by json_to_agent_output.py
    per_item_sources = None
    sidecar = Path(args.agent_output + ".sources.json")
    if sidecar.exists():
        import json as _json
        raw = _json.loads(sidecar.read_text(encoding="utf-8"))
        if isinstance(raw, list) and any(raw):
            per_item_sources = [s for s in raw if s]

    payload = build_payload(
        source_type=args.source_type,
        date_str=args.date,
        source_markdown=source_markdown,
        agent_output=agent_output,
        unified_source_label=args.unified_source_label.strip() or None,
        per_item_sources=per_item_sources,
    )
    write_payload_files(payload, work_dir)

    # Write per-item sources sidecar alongside rewritten.md for generate_xhs_images.py auto-detect
    if per_item_sources:
        import json as _json
        sidecar_out = work_dir / "rewritten.sources.json"
        sidecar_out.write_text(_json.dumps(per_item_sources, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  sources sidecar: {sidecar_out} ({len(per_item_sources)} items)")

    print("✅ Digest payload built")
    print(f"  run_id: {payload.run_id}")
    print(f"  title: {payload.title}")
    print(f"  cards: {payload.cards_text.count('🔹')}")
    print(f"  num_images: {payload.num_images}")
    print(f"  rewritten: {work_dir / 'rewritten.md'}")
    print(f"  payload: {work_dir / 'digest_payload.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
