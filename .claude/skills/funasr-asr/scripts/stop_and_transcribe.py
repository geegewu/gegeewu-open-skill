#!/usr/bin/env python3
"""Atomic stop-recording + transcribe pipeline.

Single entry point for Kimi/Codex subagent to execute:
  1. Stop current recording (meeting_rec.py stop)
  2. Transcribe the WAV file (transcribe.py --engine funasr)
  3. Print transcript path for meeting-summary handoff

Usage:
  python3 stop_and_transcribe.py
  python3 stop_and_transcribe.py --engine whisper
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent


def run(cmd: list, label: str) -> subprocess.CompletedProcess:
    print(f"\n[{label}]")
    result = subprocess.run(cmd, capture_output=False, text=True)
    if result.returncode != 0:
        print(f"❌ {label} 失败 (exit {result.returncode})")
        sys.exit(result.returncode)
    return result


def main():
    parser = argparse.ArgumentParser(description="Stop recording and transcribe")
    parser.add_argument("--engine", choices=["funasr", "whisper"], default="funasr")
    args = parser.parse_args()

    # Step 1: Stop recording, capture output to extract WAV path
    print("[1/2] 停止录制...")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "meeting_rec.py"), "stop"],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        sys.exit(result.returncode)

    # Extract WAV path from output line: RECORDING_OUTPUT:/path/to/file.wav
    wav_path = None
    for line in result.stdout.splitlines():
        m = re.match(r"RECORDING_OUTPUT:(.+)", line.strip())
        if m:
            wav_path = Path(m.group(1).strip())
            break

    if not wav_path or not wav_path.exists():
        print(f"❌ 未能找到录制文件（输出中无 RECORDING_OUTPUT 行）")
        sys.exit(1)

    print(f"✅ 录制文件: {wav_path}")

    # Step 2: Transcribe
    print(f"\n[2/2] 开始转录（引擎: {args.engine}）...")
    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "transcribe.py"),
            str(wav_path),
            "--engine", args.engine,
        ],
        check=True,
    )

    # Derive transcript path
    transcript_path = wav_path.parent / f"{wav_path.stem}_transcript.md"
    if not transcript_path.exists():
        print(f"❌ 转录文件未生成: {transcript_path}")
        sys.exit(1)

    print(f"\n✅ 转录完成")
    print(f"TRANSCRIPT_PATH:{transcript_path}")
    print(f"\n💡 下一步: meeting-summary {transcript_path}")


if __name__ == "__main__":
    main()
