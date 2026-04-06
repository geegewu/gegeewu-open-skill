#!/usr/bin/env python3
"""Meeting/call recording tool - start, stop, status.

Two modes:
  meeting  - Mac Mini + BlackHole Aggregate Device (video conference)
  phone    - Built-in microphone (phone call on speaker)
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PID_FILE = Path("/tmp/meeting_rec.pid")
RECORDINGS_DIR = Path.home() / "recordings"
FFMPEG_LOG = Path("/tmp/meeting_rec_ffmpeg.log")


def list_audio_devices() -> str:
    """Return ffmpeg avfoundation device list (from stderr)."""
    result = subprocess.run(
        ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        capture_output=True,
        text=True,
    )
    return result.stderr


def find_audio_device(keyword: str) -> str | None:
    """Find audio input device index by keyword in name."""
    output = list_audio_devices()
    for line in output.splitlines():
        if keyword.lower() in line.lower():
            m = re.search(r'\[(\d+)\]', line)
            if m:
                return m.group(1)
    return None


def get_recording_info() -> dict | None:
    """Load current recording info from PID file."""
    if not PID_FILE.exists():
        return None
    try:
        with open(PID_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def save_recording_info(pid: int, output_path: Path, mode: str) -> None:
    info = {
        "pid": pid,
        "output": str(output_path),
        "mode": mode,
        "started_at": datetime.now().isoformat(),
    }
    with open(PID_FILE, "w") as f:
        json.dump(info, f)


def is_process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def cmd_start(mode: str) -> None:
    """Start recording."""
    info = get_recording_info()
    if info and is_process_running(info["pid"]):
        print(f"❌ 已有录制进行中（{info['mode']}）: {info['output']}")
        print("   发送 `停止录制` 先停止当前录制")
        sys.exit(1)
    elif info:
        PID_FILE.unlink(missing_ok=True)

    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if mode == "meeting":
        output_path = RECORDINGS_DIR / f"meeting_{ts}.wav"
        device_idx = find_audio_device("Aggregate")
        if device_idx is None:
            print("❌ 未找到 Aggregate Device，请先在 Audio MIDI Setup 创建")
            print("\n需要的设备：")
            print("  Multi-Output Device: AirPods + BlackHole 2ch")
            print("  Aggregate Device: BlackHole 2ch + AirPods Mic")
            print("\nffmpeg 设备列表：")
            print(list_audio_devices())
            sys.exit(1)
        input_spec = f":{device_idx}"
        sample_rate = "48000"
        print(f"🎙️ 使用设备: Aggregate Device (索引 {device_idx})")
    else:  # phone
        output_path = RECORDINGS_DIR / f"phone_{ts}.wav"
        # Try common built-in mic names, fall back to index 0
        device_idx = (
            find_audio_device("MacBook Pro Microphone")
            or find_audio_device("MacBook Pro麦克风")
            or find_audio_device("Built-in Microphone")
            or "0"
        )
        input_spec = f":{device_idx}"
        sample_rate = "44100"
        print(f"🎙️ 使用设备: 内置麦克风 (索引 {device_idx})")

    cmd = [
        "ffmpeg",
        "-f", "avfoundation",
        "-thread_queue_size", "1024",
        "-i", input_spec,
        "-ar", sample_rate,
        "-c:a", "pcm_s16le",
        str(output_path),
    ]

    print(f"📹 开始录制: {output_path.name}")
    with open(FFMPEG_LOG, "w") as log:
        proc = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
        )

    # Brief pause to catch immediate launch failures
    time.sleep(1)
    if not is_process_running(proc.pid):
        with open(FFMPEG_LOG) as f:
            log_tail = f.read()[-1000:]
        print(f"❌ ffmpeg 启动失败，日志:\n{log_tail}")
        sys.exit(1)

    save_recording_info(proc.pid, output_path, mode)
    print(f"✅ 录制已启动 (PID: {proc.pid})")
    print(f"   输出: {output_path}")
    print(f"\n💡 发送 `停止录制` 结束并自动开始转录")


def cmd_stop() -> str:
    """Stop recording and return output file path."""
    info = get_recording_info()
    if not info:
        print("❌ 没有进行中的录制")
        sys.exit(1)

    pid = info["pid"]
    output_path = Path(info["output"])

    if is_process_running(pid):
        os.kill(pid, signal.SIGTERM)
        print("⏹️ 正在停止录制...")
        # Wait for ffmpeg to flush and close the file
        for _ in range(10):
            time.sleep(0.5)
            if not is_process_running(pid):
                break
    else:
        print("⚠️ 进程已不存在，可能已自动停止")

    PID_FILE.unlink(missing_ok=True)

    if not output_path.exists() or output_path.stat().st_size == 0:
        print(f"❌ 录制文件为空或不存在: {output_path}")
        sys.exit(1)

    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"✅ 录制完成")
    print(f"   文件: {output_path}")
    print(f"   大小: {size_mb:.1f} MB")
    # Print machine-readable path for skill pipeline
    print(f"RECORDING_OUTPUT:{output_path}")
    return str(output_path)


def cmd_status() -> None:
    """Show current recording status."""
    info = get_recording_info()
    if not info:
        print("💤 当前无录制")
        return

    pid = info["pid"]
    if not is_process_running(pid):
        print("⚠️ 录制进程已退出（异常停止）")
        PID_FILE.unlink(missing_ok=True)
        return

    output_path = Path(info["output"])
    size_mb = output_path.stat().st_size / 1024 / 1024 if output_path.exists() else 0
    started = datetime.fromisoformat(info["started_at"])
    elapsed = datetime.now() - started
    mins = int(elapsed.total_seconds() // 60)
    secs = int(elapsed.total_seconds() % 60)

    mode_label = "会议录制" if info["mode"] == "meeting" else "通话录音"
    print(f"🔴 录制中 - {mode_label}")
    print(f"   已录制: {mins:02d}:{secs:02d}")
    print(f"   文件大小: {size_mb:.1f} MB")
    print(f"   输出: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="会议/通话录制工具")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("start-meeting", help="开始会议录制（Mac Mini + BlackHole Aggregate Device）")
    subparsers.add_parser("start-phone", help="开始通话录制（内置麦克风，手机外放）")
    subparsers.add_parser("stop", help="停止录制")
    subparsers.add_parser("status", help="查询录制状态")

    args = parser.parse_args()

    if args.command == "start-meeting":
        cmd_start("meeting")
    elif args.command == "start-phone":
        cmd_start("phone")
    elif args.command == "stop":
        cmd_stop()
    elif args.command == "status":
        cmd_status()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
