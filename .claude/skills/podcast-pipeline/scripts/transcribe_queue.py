#!/usr/bin/env python3
"""播客转录队列 — 独立后台进程，处理所有已下载未转录的集，完成后发 Telegram 通知。

由 rss_downloader.py 在下载完成后 detach 启动，也可手动运行：
    python3 transcribe_queue.py
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).parent
STATE_FILE = SKILL_DIR / "download_state.json"
LOG_DIR = SKILL_DIR / "logs"
TRANSCRIPT_ARCHIVE_DIR = SKILL_DIR / "transcripts"
TRANSCRIBE_SCRIPT = Path(__file__).resolve().parent.parent.parent / "funasr-asr" / "scripts" / "transcribe.py"
PYTHON_BIN = os.environ.get("PYTHON", str(Path.home() / "myenv" / "bin" / "python3"))
OBSIDIAN_VAULT_DIR = Path(os.environ.get("OBSIDIAN_VAULT_PATH", ""))
OBSIDIAN_PODCASTS_DIR = OBSIDIAN_VAULT_DIR / "Podcasts"


def sync_to_obsidian(transcript_path: Path, logger: logging.Logger) -> Path | None:
    """Copy transcript to Obsidian Podcasts/YYYY-MM-DD/ using the original filename."""
    if not transcript_path.exists():
        return None
    date_dir = transcript_path.parent.name
    dest_dir = OBSIDIAN_PODCASTS_DIR / date_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / transcript_path.name
    dest_path.write_text(transcript_path.read_text(encoding="utf-8"), encoding="utf-8")
    logger.info(f"Obsidian synced: {dest_path}")
    return dest_path


def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"transcribe_queue_{datetime.now().strftime('%Y-%m-%d')}.log"
    logger = logging.getLogger("transcribe_queue")
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def load_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_-]+", "-", text).strip("-")[:80]


def _send_telegram(text: str, logger: logging.Logger) -> None:
    dotenv = Path.home() / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN 未设置，跳过通知")
        return
    data = json.dumps({"chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""), "text": text}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        logger.warning(f"Telegram 发送失败: {e}")


def _write_episode_meta(transcript_path: Path, episode: dict[str, Any]) -> None:
    if not transcript_path.exists():
        return
    text = transcript_path.read_text(encoding="utf-8")
    meta = episode.get("extracted_meta", {})

    meta_lines = ["---"]
    if episode.get("podcast"):
        meta_lines.append(f"**节目**：{episode['podcast']}")
    if episode.get("title"):
        meta_lines.append(f"**标题**：{episode['title']}")

    # Host: prefer extracted_meta, fallback to static hosts
    host = meta.get("host", "")
    host_title = meta.get("host_title", "")
    if host:
        host_str = f"{host}（{host_title}）" if host_title else host
        meta_lines.append(f"**主持人**：{host_str}")
    elif episode.get("hosts"):
        meta_lines.append(f"**主持人**：{episode['hosts']}")

    # Guests from extracted_meta
    guests = meta.get("guests", [])
    if guests:
        guest_strs = []
        for g in guests:
            name = g.get("name", "")
            title = g.get("title", "")
            guest_strs.append(f"{name}（{title}）" if title else name)
        meta_lines.append(f"**嘉宾**：{'、'.join(guest_strs)}")

    # Summary: prefer extracted, fallback to description[:300]
    summary = meta.get("summary", "")
    if summary:
        meta_lines.append(f"**简介**：{summary}")
    elif episode.get("description"):
        meta_lines.append(f"**简介**：{episode['description'][:300]}")

    # Key names for Whisper correction
    key_names = meta.get("key_names", [])
    if key_names:
        meta_lines.append(f"**关键人名**：{'、'.join(key_names)}")

    lang = episode.get("lang", "")
    if lang:
        meta_lines.append(f"**语言**：{lang}")
    meta_lines.append("---")
    meta_block = "\n".join(meta_lines) + "\n"
    if "# 转录结果" in text:
        text = text.replace("# 转录结果\n", "# 转录结果\n\n" + meta_block, 1)
    else:
        text = meta_block + "\n" + text
    transcript_path.write_text(text, encoding="utf-8")


def transcribe_one(episode: dict[str, Any], logger: logging.Logger) -> bool:
    audio_path = Path(episode["audio_path"])
    podcast_name = episode["podcast"]
    title = episode["title"]

    today = datetime.now().strftime("%Y-%m-%d")
    transcript_dir = SKILL_DIR / "transcripts" / today
    transcript_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(podcast_name)
    transcript_path = transcript_dir / f"{slug}.md"

    logger.info(f"[{podcast_name}] 开始转录: {audio_path.name}")

    cmd = [
        PYTHON_BIN,
        str(TRANSCRIBE_SCRIPT),
        str(audio_path),
        "--engine", "mlx",
        "--output", str(transcript_path),
        "--delete-audio",
    ]
    env = os.environ.copy()
    env["PATH"] = "/opt/homebrew/bin:" + env.get("PATH", "")

    t0 = time.monotonic()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, env=env)
        elapsed = time.monotonic() - t0
        if result.returncode == 0:
            _write_episode_meta(transcript_path, episode)
            obsidian_path = sync_to_obsidian(transcript_path, logger)
            size_kb = transcript_path.stat().st_size // 1024 if transcript_path.exists() else 0
            logger.info(f"[{podcast_name}] 转录完成 ({elapsed/60:.1f}min, {size_kb}KB): {transcript_path}")
            sync_suffix = f"\n🪶 Obsidian → Podcasts/{today}/{transcript_path.name}" if obsidian_path else ""
            _send_telegram(
                f"✅ 转录完成 ({elapsed/60:.1f}min)\n"
                f"[{podcast_name}] {title[:50]}\n"
                f"📄 {size_kb}KB → transcripts/{today}/{slug}.md"
                f"{sync_suffix}",
                logger,
            )
            return True
        else:
            err = result.stderr[-500:] if result.stderr else "unknown error"
            logger.error(f"[{podcast_name}] 转录失败 (rc={result.returncode}): {err}")
            _send_telegram(f"❌ 转录失败\n[{podcast_name}] {title[:50]}\n{err}", logger)
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"[{podcast_name}] 转录超时（>1小时）")
        _send_telegram(f"❌ 转录超时（>1h）\n[{podcast_name}] {title[:50]}", logger)
        return False
    except Exception as e:
        logger.error(f"[{podcast_name}] 转录异常: {e}")
        _send_telegram(f"❌ 转录异常\n[{podcast_name}] {title[:50]}\n{e}", logger)
        return False


def main() -> int:
    logger = setup_logging()
    logger.info("=== transcribe_queue 启动 ===")

    state = load_state()
    queue: list[dict[str, Any]] = []
    for guid, info in state.items():
        if info.get("skipped") or info.get("transcribed") is not None:
            continue
        audio_path = info.get("audio_path")
        if audio_path and Path(audio_path).exists():
            queue.append({
                "guid": guid,
                "podcast": info["podcast"],
                "title": info["title"],
                "audio_path": audio_path,
                "hosts": info.get("hosts", ""),
                "description": info.get("description", ""),
                "lang": info.get("lang", ""),
                "extracted_meta": info.get("extracted_meta", {}),
            })

    if not queue:
        logger.info("没有待转录的集，退出")
        return 0

    logger.info(f"待转录 {len(queue)} 集")
    _send_telegram(
        f"🎙️ 开始转录 {len(queue)} 集播客\n"
        + "\n".join(f"• [{r['podcast']}] {r['title'][:45]}" for r in queue),
        logger,
    )

    transcribed = 0
    results: list[dict[str, Any]] = []  # track per-episode outcome
    t_start = time.monotonic()
    for episode in queue:
        guid = episode["guid"]
        state = load_state()
        if state.get(guid, {}).get("transcribed") is True:
            logger.info(f"已转录，跳过: {episode['title'][:50]}")
            continue
        t0 = time.monotonic()
        success = transcribe_one(episode, logger)
        elapsed_ep = time.monotonic() - t0
        state = load_state()
        if guid in state:
            state[guid]["transcribed"] = success
            if not success:
                state[guid]["transcribe_error"] = "failed"
        save_state(state)
        results.append({"podcast": episode["podcast"], "title": episode["title"],
                         "success": success, "elapsed": elapsed_ep})
        if success:
            transcribed += 1

    total_elapsed = time.monotonic() - t_start
    logger.info(f"=== 转录完成：{transcribed}/{len(queue)} 成功 ===")

    # Collect today's YouTube subtitle episodes (already transcribed, skipped by queue)
    today = datetime.now().strftime("%Y-%m-%d")
    state = load_state()
    yt_subtitles = [
        v for v in state.values()
        if isinstance(v, dict)
        and v.get("source_type") == "youtube_subtitle"
        and v.get("transcribed") is True
        and (v.get("downloaded_at", "") or "").startswith(today)
    ]

    # Always send summary (even for single episode or all failures)
    elapsed_str = f"{int(total_elapsed // 60)}m{int(total_elapsed % 60)}s"
    header = f"🎙️ 转录汇总：{transcribed}/{len(results)} 成功  ⏱ {elapsed_str}"
    lines = [header]
    for r in results:
        icon = "✅" if r["success"] else "❌"
        ep_min = f"转录{r['elapsed']/60:.1f}min"
        lines.append(f"{icon} [{r['podcast']}] {r['title'][:45]} ({ep_min})")
    if yt_subtitles:
        lines.append("")
        lines.append(f"📝 YouTube 字幕：{len(yt_subtitles)} 集")
        for v in yt_subtitles:
            transcript_path = v.get("transcript_path", "")
            chars = ""
            if transcript_path and Path(transcript_path).exists():
                chars = f" ({len(Path(transcript_path).read_text(encoding='utf-8'))}字)"
            lines.append(f"  ✅ [{v['podcast']}] {v['title'][:45]}{chars}")
    _send_telegram("\n".join(lines), logger)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
