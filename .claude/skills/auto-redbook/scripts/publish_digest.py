#!/usr/bin/env python3
"""Publish digest via unified payload file."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish digest from digest_payload.json")
    parser.add_argument(
        "--payload",
        default=str(Path(__file__).parent.parent / "digest_payload.json"),
        help="Path to digest_payload.json",
    )
    parser.add_argument("--private", action="store_true", help="Publish as private note")
    args = parser.parse_args()

    payload_path = Path(args.payload)
    if not payload_path.exists():
        raise SystemExit(f"payload not found: {payload_path}")

    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    work_dir = Path(__file__).parent.parent
    rewritten_path = work_dir / "rewritten.md"
    if not rewritten_path.exists():
        raise SystemExit(f"rewritten.md not found: {rewritten_path}")

    num_images = int(payload.get("num_images", 1))
    cmd = [
        sys.executable,
        str(Path(__file__).parent / "publish_all_in_one.py"),
        str(rewritten_path),
        "--num-images",
        str(num_images),
        "--skip-cover",
    ]
    if args.private:
        cmd.append("--private")

    env = os.environ.copy()
    env.setdefault("USE_XHS_MCP", "1")

    print("🚀 Publishing digest with unified pipeline...")
    print(f"  payload: {payload_path}")
    print(f"  rewritten: {rewritten_path}")
    print(f"  num_images: {num_images}")
    print(f"  backend USE_XHS_MCP: {env.get('USE_XHS_MCP')}")

    result = subprocess.run(cmd, env=env)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())

