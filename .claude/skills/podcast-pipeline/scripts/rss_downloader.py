#!/usr/bin/env python3
"""RSS 增量下载器 - 解析播客 RSS feed，增量下载新集，避免重复下载。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from pathlib import Path
from typing import Any

# ── 常量 ──────────────────────────────────────────────────────────
SKILL_DIR = Path(__file__).parent
AUDIO_DIR = SKILL_DIR / "audio"
TRANSCRIPT_ARCHIVE_DIR = SKILL_DIR / "transcripts"
TRANSCRIBE_SCRIPT = Path(__file__).resolve().parent.parent.parent / "funasr-asr" / "scripts" / "transcribe.py"
PYTHON_BIN = os.environ.get("PYTHON", str(Path.home() / "myenv" / "bin" / "python3"))
STATE_FILE = SKILL_DIR / "download_state.json"
LOG_DIR = SKILL_DIR / "logs"

FEEDS: list[dict[str, str]] = [
    # English feeds
    {"name": "Practical AI", "url": "https://changelog.com/practicalai/feed", "lang": "en", "hosts": "Chris Benson, Daniel Whitenack"},
    {"name": "Latent Space", "url": "https://rss.flightcast.com/vgnxzgiwwzwke85ym53fjnzu", "lang": "en", "hosts": "Alessio Fanelli, Swyx (shawn wang)"},
    {"name": "TWIML AI Podcast", "url": "https://twimlai.com/feed/", "lang": "en", "hosts": "Sam Charrington"},
    {"name": "Lex Fridman Podcast", "url": "https://lexfridman.com/feed/podcast/", "lang": "en", "hosts": "Lex Fridman"},
    {"name": "Dwarkesh Podcast", "url": "https://api.substack.com/feed/podcast/69345.rss", "lang": "en", "hosts": "Dwarkesh Patel"},
    {"name": "The Cognitive Revolution", "url": "https://feeds.megaphone.fm/RINTP3108857801", "lang": "en", "hosts": "Nathan Labenz"},
    # Chinese feeds
    {"name": "硅谷101", "url": "https://feeds.fireside.fm/sv101/rss", "lang": "zh", "hosts": "泓君"},
    {"name": "晚点聊LateTalk", "url": "https://feeds.fireside.fm/latetalk/rss", "lang": "zh", "hosts": "汉洋"},
    {"name": "张小珺Jun", "url": "https://feed.xyzfm.space/dk4yh3pkpjp3", "lang": "zh", "hosts": "张小珺"},
    {"name": "屠龙之术", "url": "https://feed.xyzfm.space/834hyx3v9k74", "lang": "zh", "hosts": "庄明浩"},
    # YouTube channels (subtitle-only, no audio download)
    {"name": "AI Explained", "type": "youtube",
     "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCNJ1Ymd5yFuUPtn21xtRbbw",
     "lang": "en", "hosts": "Philip (AI Explained)"},
    {"name": "Matthew Berman", "type": "youtube",
     "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCawZsQWqfGSbCI5yjkdVkTA",
     "lang": "en", "hosts": "Matthew Berman"},
]

# 需要关键词过滤的 feed（仅下载 AI/科技相关集）
TOPIC_FILTER_FEEDS: set[str] = {
    "Practical AI", "Latent Space", "TWIML AI Podcast",
    "Lex Fridman Podcast", "The Cognitive Revolution",
    "硅谷101", "晚点聊LateTalk", "张小珺Jun", "屠龙之术",
    "AI Explained", "Matthew Berman",
}

MIN_AUDIO_SIZE_BYTES = 5 * 1024 * 1024  # 5MB, skip trailers/promos
MIN_SUBTITLE_CHARS = 4000            # skip YouTube shorts/ads/trailers (<5min ~3000-4000 chars)

# AI/科技关键词白名单（标题包含任意一个即通过，不区分大小写）
AI_TECH_KEYWORDS: list[str] = [
    # AI core (EN)
    "ai", "artificial intelligence", "machine learning", "deep learning",
    "neural", "llm", "gpt", "model", "agent", "transformer",
    "language model", "foundation model", "scaling law",
    # AI companies/products (EN)
    "openai", "anthropic", "google deepmind", "meta ai", "mistral",
    "claude", "gemini", "chatgpt", "copilot", "cursor",
    # AI infra (EN)
    "compute", "chip", "gpu", "nvidia", "semiconductor", "tsmc",
    "inference", "training", "fine-tuning", "rag",
    # AI applications (EN)
    "robot", "robotics", "autonomous", "self-driving",
    "coding assistant", "ai coding", "ai for",
    # Tech industry (EN)
    "software engineer", "developer", "programming",
    "startup", "venture", "silicon valley",
    "tech company", "big tech",
    # AI core (ZH)
    "人工智能", "大模型", "大语言模型", "机器学习", "深度学习",
    "智能体", "agent", "算力", "芯片", "gpu", "英伟达",
    # AI companies (ZH)
    "openai", "谷歌", "微软", "meta", "苹果",
    "百度", "阿里", "腾讯", "字节", "月之暗面", "kimi",
    "deepseek", "智谱", "minimax", "商汤",
    # AI topics (ZH)
    "大模型", "生成式", "aigc", "copilot", "编程",
    "自动驾驶", "机器人", "具身智能",
    "创业", "融资", "vc", "风投",
    "科技", "技术", "算法", "数据",
    "半导体", "台积电", "tpu",
]

DOWNLOAD_CHUNK_SIZE = 256 * 1024   # 256KB per chunk
CHUNK_SLEEP_S = 0.05               # throttle: ~5MB/s effective
MAX_RETRIES = 1                    # 最多重试 1 次
MAX_DOWNLOAD_SECONDS = 900         # 15 分钟总下载超时（大文件需要更多时间）
YT_DLP_TIMEOUT = 60               # yt-dlp 单操作总超时（extract_info / download）
TOTAL_FEEDS_TIMEOUT = 1200         # 全部 feed 并发总超时（20 分钟，cron 30 分钟留余量）

# Retryable skip reasons: these will be retried on next run (up to MAX_SKIP_RETRIES)
RETRYABLE_REASONS: set[str] = {
    "subtitle_download_failed", "subtitle_download_timeout",
    "no_subtitles",  # retry within NO_SUBTITLES_RETRY_WINDOW_HOURS after first attempt
    "extract_info_timeout", "download_timeout",
}
MAX_SKIP_RETRIES = 3               # max retry count before permanent skip
NO_SUBTITLES_RETRY_WINDOW_HOURS = 72  # retry no_subtitles up to 3 days (cron runs daily, MAX_SKIP_RETRIES=3)
TMP_MAX_AGE_HOURS = 24             # clean up .tmp files older than this


def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"rss_downloader_{datetime.now().strftime('%Y-%m-%d')}.log"
    logger = logging.getLogger("rss_downloader")
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return logger
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler(sys.stdout)
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


def fetch_feed(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; podcast-monitor/1.0; +https://github.com/geegewu)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


PROMO_KEYWORDS = [
    # 中文
    "预告", "活动预告", "番外预告", "上线预告",
    # English
    "trailer", "preview", "teaser", "promo", "announcement", "coming soon",
]

MIN_DURATION_SECONDS = 5 * 60  # 5 分钟


def parse_duration(duration_str: str) -> int:
    """解析 itunes:duration 为秒数。支持 HH:MM:SS / MM:SS / 纯秒数格式。"""
    if not duration_str:
        return 0
    parts = duration_str.strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        else:
            return int(duration_str.strip())
    except (ValueError, IndexError):
        return 0


def is_promo_title(title: str) -> bool:
    """判断标题是否为预告/宣传集。"""
    title_lower = title.lower()
    return any(kw in title_lower for kw in PROMO_KEYWORDS)


def parse_episodes(feed_bytes: bytes) -> list[dict[str, str]]:
    import xml.etree.ElementTree as ET
    root = ET.fromstring(feed_bytes)
    channel = root.find("channel")
    if channel is None:
        return []
    itunes_ns = "http://www.itunes.com/dtds/podcast-1.0.dtd"
    episodes = []
    for item in channel.findall("item"):
        guid_el = item.find("guid")
        title_el = item.find("title")
        enclosure_el = item.find("enclosure")
        pub_date_el = item.find("pubDate")
        desc_el = item.find("description")
        duration_el = item.find(f"{{{itunes_ns}}}duration")
        guid = (guid_el.text or "").strip() if guid_el is not None else ""
        title = (title_el.text or "").strip() if title_el is not None else ""
        audio_url = enclosure_el.get("url", "").strip() if enclosure_el is not None else ""
        audio_size = int(enclosure_el.get("length", "0") or "0") if enclosure_el is not None else 0
        pub_date = (pub_date_el.text or "").strip() if pub_date_el is not None else ""
        description = (desc_el.text or "").strip() if desc_el is not None else ""
        duration_secs = parse_duration((duration_el.text or "") if duration_el is not None else "")
        # Strip HTML tags from description for plain text
        description = re.sub(r"<[^>]+>", " ", description)
        description = re.sub(r"\s+", " ", description).strip()[:1000]
        if not guid:
            guid = audio_url or title
        if not guid:
            continue
        episodes.append({
            "guid": guid, "title": title, "audio_url": audio_url,
            "audio_size": audio_size, "pub_date": pub_date,
            "description": description, "duration_secs": duration_secs,
        })
    return episodes


def is_ai_tech_episode(feed_name: str, title: str) -> bool:
    """判断 episode 是否与 AI/科技相关。仅对 TOPIC_FILTER_FEEDS 中的 feed 生效。"""
    if feed_name not in TOPIC_FILTER_FEEDS:
        return True  # 其他 feed 全部通过
    title_lower = title.lower()
    return any(kw in title_lower for kw in AI_TECH_KEYWORDS)



def parse_youtube_feed(feed_bytes: bytes) -> list[dict[str, Any]]:
    """Parse YouTube Atom feed (different schema from podcast RSS)."""
    import xml.etree.ElementTree as ET
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
        "media": "http://search.yahoo.com/mrss/",
    }
    root = ET.fromstring(feed_bytes)
    episodes = []
    for entry in root.findall("atom:entry", ns):
        video_id_el = entry.find("yt:videoId", ns)
        title_el = entry.find("atom:title", ns)
        published_el = entry.find("atom:published", ns)
        media_group = entry.find("media:group", ns)
        desc_el = media_group.find("media:description", ns) if media_group is not None else None

        video_id = (video_id_el.text or "").strip() if video_id_el is not None else ""
        title = (title_el.text or "").strip() if title_el is not None else ""
        pub_date = (published_el.text or "").strip() if published_el is not None else ""
        description = (desc_el.text or "").strip() if desc_el is not None else ""
        description = description[:1000]

        if not video_id:
            continue
        guid = f"yt:video:{video_id}"
        episodes.append({
            "guid": guid, "title": title, "audio_url": "",
            "audio_size": 0, "pub_date": pub_date,
            "description": description, "duration_secs": 0,
            "video_id": video_id,
        })
    return episodes


def _download_subtitles_baoyu(
    video_id: str,
    lang: str,
    transcript_path: Path,
    logger: logging.Logger,
) -> bool | str:
    """Download subtitles via baoyu-youtube-transcript (InnerTube API + cookie fallback).

    Uses baoyu's main.ts which:
    1. Calls YouTube InnerTube API directly (no API key needed)
    2. Rotates client identities on block
    3. Falls back to yt-dlp with browser cookies if still blocked

    Returns True on success, False on error, or a skip-reason string.
    """
    import subprocess

    bun = shutil.which("bun")
    if not bun:
        logger.error("bun not installed, cannot run baoyu-youtube-transcript")
        return False

    script = Path(__file__).parent / "vendor" / "baoyu-youtube-transcript" / "scripts" / "main.ts"
    if not script.exists():
        logger.error(f"baoyu script not found: {script}")
        return False

    video_url = f"https://www.youtube.com/watch?v={video_id}"
    if lang == "zh":
        languages = "zh-Hans,zh,zh-Hant,en"
    else:
        languages = "en,en-orig"

    # Output to a temp dir; baoyu auto-names the file
    tmpdir = Path(tempfile.mkdtemp())
    env = os.environ.copy()
    env["PATH"] = f"/opt/homebrew/bin:{env.get('PATH', '')}"

    # Use pre-exported cookies file to bypass IP/bot blocks (avoid Keychain deadlock)
    cookies_file = Path(__file__).parent / "vendor" / "yt_cookies.txt"
    if cookies_file.exists():
        env["YOUTUBE_TRANSCRIPT_COOKIES_FILE"] = str(cookies_file)

    cmd = [
        bun, str(script),
        video_url,
        "--languages", languages,
        "--no-timestamps",
        "--output-dir", str(tmpdir),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=90,
            env=env,
        )
    except subprocess.TimeoutExpired:
        logger.warning(f"baoyu-youtube-transcript timed out (90s): {video_id}")
        return "subtitle_download_timeout"
    except Exception as e:
        logger.error(f"baoyu-youtube-transcript subprocess error: {e}")
        return False

    if result.returncode != 0:
        stderr = result.stderr.strip()
        # Detect cookie expiry / auth failure
        _cookie_expired_signals = (
            "sign in to confirm",
            "sign in to access",
            "cookies-from-browser",
            "this video is only available",
            "ytdl_hook: failed",
            "has no supported formats",
        )
        if any(s in stderr.lower() for s in _cookie_expired_signals):
            logger.warning(
                f"[{video_id}] YouTube cookie 已失效或未授权。"
                f"请在终端重新导出：\n"
                f"  yt-dlp --cookies-from-browser chrome "
                f"--cookies ~/gegeewu-skills/.claude/skills/podcast-pipeline/vendor/yt_cookies.txt "
                f"--skip-download --print title 'https://youtu.be/dQw4w9WgXcQ'\n"
                f"（Safari 用户将 chrome 换成 safari）"
            )
        else:
            logger.warning(f"baoyu-youtube-transcript failed (rc={result.returncode}): {stderr[-300:]}")
        return False

    # Find the output .md file
    md_files = list(tmpdir.rglob("transcript.md"))
    if not md_files:
        # Check stderr/stdout for cookie expiry signals even when rc=0
        combined = (result.stderr + result.stdout).lower()
        _cookie_expired_signals = (
            "sign in to confirm",
            "sign in to access",
            "cookies-from-browser",
            "yt-dlp fallback failed",
        )
        if any(s in combined for s in _cookie_expired_signals):
            logger.warning(
                f"[{video_id}] YouTube cookie 已失效或未授权。"
                f"请在终端重新导出：\n"
                f"  yt-dlp --cookies-from-browser chrome "
                f"--cookies ~/gegeewu-skills/.claude/skills/podcast-pipeline/vendor/yt_cookies.txt "
                f"--skip-download --print title 'https://youtu.be/dQw4w9WgXcQ'\n"
                f"（Safari 用户将 chrome 换成 safari）"
            )
        else:
            logger.warning(f"baoyu-youtube-transcript: no transcript.md found for {video_id}")
        return False

    md_file = md_files[0]
    raw_text = md_file.read_text(encoding="utf-8")

    # Strip YAML frontmatter and heading, extract body text
    lines = raw_text.split("\n")
    body_lines: list[str] = []
    in_frontmatter = False
    frontmatter_done = False
    skip_heading = True
    for line in lines:
        if not frontmatter_done:
            if line.strip() == "---":
                in_frontmatter = not in_frontmatter
                if not in_frontmatter:
                    frontmatter_done = True
                continue
            if in_frontmatter:
                continue
        if skip_heading and line.startswith("#"):
            skip_heading = False
            continue
        body_lines.append(line)
    full_text = "\n".join(body_lines).strip()

    # Cleanup temp dir
    import shutil as _shutil
    _shutil.rmtree(tmpdir, ignore_errors=True)

    # Detect videos with no subtitle track: content is only description (very short or matches description)
    if len(full_text) < MIN_SUBTITLE_CHARS:
        # Distinguish: no subtitle track vs. genuinely short video
        # If baoyu returned content but it's tiny, it's likely just the video description (no captions)
        if len(full_text) < 500:
            logger.info(f"No subtitle track detected ({len(full_text)} chars, likely description only): {video_id}")
            return "no_subtitles"
        logger.info(f"Subtitle too short ({len(full_text)} chars), skipping: {video_id}")
        return "too_short_duration"

    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_content = f"# 转录结果\n\n{full_text}\n"
    transcript_path.write_text(transcript_content, encoding="utf-8")
    logger.info(f"YouTube subtitle transcript saved (baoyu): {transcript_path.name} ({len(full_text)} chars)")
    return True


def _download_subtitles_ytdlp(
    video_id: str,
    lang: str,
    transcript_path: Path,
    logger: logging.Logger,
) -> bool | str:
    """Download subtitles via yt-dlp (fallback, heavier but different endpoint).

    Returns True on success, False on error, or a skip-reason string.
    """
    try:
        import yt_dlp
    except ImportError:
        logger.error("yt-dlp not installed")
        return False

    # Ensure /opt/homebrew/bin in PATH (ffmpeg + node for yt-dlp JS runtime)
    _path = os.environ.get("PATH", "")
    if "/opt/homebrew/bin" not in _path:
        os.environ["PATH"] = f"/opt/homebrew/bin:{_path}"

    video_url = f"https://www.youtube.com/watch?v={video_id}"

    _ydl_common: dict[str, Any] = {"quiet": True, "skip_download": True, "socket_timeout": 30}
    if shutil.which("node"):
        _ydl_common["js_runtimes"] = {"node": {}}
        _ydl_common["remote_components"] = {"ejs:github": {}}

    # Pre-check duration
    try:
        with yt_dlp.YoutubeDL(_ydl_common) as ydl:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(ydl.extract_info, video_url, False)
                try:
                    info = future.result(timeout=YT_DLP_TIMEOUT)
                except FuturesTimeoutError:
                    logger.warning(f"yt-dlp extract_info timed out ({YT_DLP_TIMEOUT}s): {video_id}")
                    return "extract_info_timeout"
            duration = info.get("duration") or 0
            if duration > 0 and duration < MIN_DURATION_SECONDS:
                logger.info(f"Video too short ({duration}s < {MIN_DURATION_SECONDS}s), skipping")
                return "too_short_duration"
    except Exception as e:
        logger.warning(f"yt-dlp duration pre-check failed (proceeding anyway): {e}")

    tmpdir = tempfile.mkdtemp()
    if lang == "zh":
        sub_langs = ["zh-Hans", "zh", "zh-Hant", "en"]
    else:
        sub_langs = ["en-orig", "en"]

    ydl_opts = {
        **_ydl_common,
        "writeautomaticsub": True,
        "subtitleslangs": sub_langs,
        "subtitlesformat": "json3",
        "outtmpl": str(Path(tmpdir) / "%(id)s"),
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(ydl.download, [video_url])
                try:
                    future.result(timeout=YT_DLP_TIMEOUT)
                except FuturesTimeoutError:
                    logger.warning(f"yt-dlp subtitle download timed out ({YT_DLP_TIMEOUT}s): {video_id}")
                    return "subtitle_download_timeout"
    except Exception as e:
        logger.error(f"yt-dlp subtitle download failed: {e}")
        return False

    # Find the downloaded json3 file
    import json as json_mod
    sub_file = None
    for sl in sub_langs:
        candidate = Path(tmpdir) / f"{video_id}.{sl}.json3"
        if candidate.exists():
            sub_file = candidate
            break
    if sub_file is None:
        json3_files = list(Path(tmpdir).glob("*.json3"))
        if json3_files:
            sub_file = json3_files[0]

    if sub_file is None:
        logger.warning(f"No subtitle file found for {video_id}")
        return False

    # Parse json3 → plain text with paragraph breaks every ~60s
    try:
        data = json_mod.loads(sub_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse subtitle json3: {e}")
        return False

    events = data.get("events", [])
    paragraphs: list[str] = []
    current_lines: list[str] = []
    last_para_ts = 0.0

    for evt in events:
        segs = evt.get("segs", [])
        text = "".join(s.get("utf8", "") for s in segs).strip()
        if not text or text == "\n":
            continue
        ts = evt.get("tStartMs", 0) / 1000.0

        if current_lines and ts - last_para_ts >= 60:
            paragraphs.append(" ".join(current_lines))
            current_lines = []
            last_para_ts = ts

        if not current_lines:
            last_para_ts = ts
        current_lines.append(text)

    if current_lines:
        paragraphs.append(" ".join(current_lines))

    full_text = "\n\n".join(paragraphs)

    if len(full_text) < MIN_SUBTITLE_CHARS:
        logger.info(f"Subtitle too short ({len(full_text)} chars), skipping")
        return False

    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_content = f"# 转录结果\n\n{full_text}\n"
    transcript_path.write_text(transcript_content, encoding="utf-8")
    # Cache raw events for potential re-processing
    raw_cache = transcript_path.with_suffix(".raw.json")
    raw_cache.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
    logger.info(f"YouTube subtitle transcript saved (yt-dlp): {transcript_path.name} ({len(full_text)} chars)")

    # Cleanup temp files
    for tmp_f in Path(tmpdir).iterdir():
        tmp_f.unlink()
    Path(tmpdir).rmdir()

    return True


def _download_youtube_subtitles(
    video_id: str,
    lang: str,
    transcript_path: Path,
    logger: logging.Logger,
) -> bool | str:
    """Download YouTube subtitles: baoyu (InnerTube + cookie) first, yt-dlp fallback.

    Returns True on success, False on error, or a skip-reason string
    (e.g. 'too_short_duration') when the video should be skipped.
    """
    # Primary: baoyu InnerTube API (rotates client identities, cookie-aware)
    result = _download_subtitles_baoyu(video_id, lang, transcript_path, logger)
    if result is True:
        return True
    # Respect definitive skip reasons (too short etc.)
    # "no_subtitles" is NOT treated as definitive — baoyu may miss subtitles that yt-dlp can fetch
    if isinstance(result, str) and result not in ("subtitle_download_timeout", "no_subtitles"):
        return result

    # Last resort: yt-dlp
    logger.info(f"Fallback to yt-dlp for {video_id}")
    return _download_subtitles_ytdlp(video_id, lang, transcript_path, logger)


def _download_once(url: str, dest_path: Path, logger: logging.Logger) -> bool:
    """单次下载尝试，带限速。"""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_suffix(".tmp")
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; podcast-monitor/1.0)"},
        )
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_path, "wb") as f:
            downloaded = 0
            while True:
                if time.monotonic() - t0 > MAX_DOWNLOAD_SECONDS:
                    raise TimeoutError(f"下载超过 {MAX_DOWNLOAD_SECONDS}s ({downloaded / 1024 / 1024:.1f}MB)")
                chunk = resp.read(DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                time.sleep(CHUNK_SLEEP_S)
        tmp_path.rename(dest_path)
        logger.info(f"下载完成: {dest_path.name} ({downloaded / 1024 / 1024:.1f} MB)")
        return True
    except Exception as e:
        logger.warning(f"下载失败: {e}")
        if tmp_path.exists():
            tmp_path.unlink()
        return False


def download_audio(url: str, dest_path: Path, logger: logging.Logger) -> bool:
    """下载音频，支持重试 1 次。"""
    for attempt in range(1, MAX_RETRIES + 2):
        logger.info(f"开始下载（第 {attempt} 次）: {dest_path.name}")
        if _download_once(url, dest_path, logger):
            return True
        if attempt <= MAX_RETRIES:
            wait = 5 * attempt
            logger.warning(f"下载失败，{wait}s 后重试...")
            time.sleep(wait)
    logger.error(f"下载最终失败（重试 {MAX_RETRIES} 次后放弃）: {dest_path.name}")
    return False


def process_feed_sync(
    feed: dict[str, str],
    state: dict[str, Any],
    limit: int,
    logger: logging.Logger,
    *,
    auto_save: bool = True,
) -> list[dict[str, Any]]:
    """同步处理单个 feed，返回本次下载成功的 episode 列表。"""

    def _save() -> None:
        if auto_save:
            save_state(state)

    name = feed["name"]
    url = feed["url"]
    no_enclosure = feed.get("no_enclosure") == "true"

    logger.info(f"[{name}] 开始检查 RSS...")

    try:
        feed_bytes = fetch_feed(url)
    except Exception as e:
        logger.error(f"[{name}] 抓取 feed 失败: {e}")
        return []

    is_youtube = feed.get("type") == "youtube"
    episodes = parse_youtube_feed(feed_bytes) if is_youtube else parse_episodes(feed_bytes)
    if not episodes:
        logger.warning(f"[{name}] 无有效 episode")
        return []

    logger.info(f"[{name}] 共找到 {len(episodes)} 集")

    downloaded: list[dict[str, Any]] = []
    for ep in episodes[: limit * 3]:
        guid = ep["guid"]
        title = ep["title"]
        audio_url = ep["audio_url"]

        if guid in state:
            existing = state[guid]
            # Allow retry for retryable failures (up to MAX_SKIP_RETRIES)
            reason = existing.get("reason", "")
            retry_count = existing.get("retry_count", 0)
            if existing.get("skipped") and reason in RETRYABLE_REASONS and retry_count < MAX_SKIP_RETRIES:
                # no_subtitles: only retry within the time window
                if reason == "no_subtitles":
                    downloaded_at = existing.get("downloaded_at", "")
                    try:
                        age_hours = (datetime.now() - datetime.fromisoformat(downloaded_at)).total_seconds() / 3600
                    except Exception:
                        age_hours = 999
                    if age_hours > NO_SUBTITLES_RETRY_WINDOW_HOURS:
                        logger.debug(f"[{name}] no_subtitles 超过重试窗口({age_hours:.1f}h)，永久跳过: {title[:50]}")
                        continue
                logger.info(f"[{name}] 重试（第{retry_count+1}次）: {title[:50]}（上次: {reason}）")
                del state[guid]  # remove so it gets re-processed below
            else:
                logger.debug(f"[{name}] 已下载，跳过: {title[:50]}")
                continue

        if not is_youtube and (no_enclosure or not audio_url):
            logger.info(f"[{name}] 无 enclosure，标记跳过: {title[:50]}")
            state[guid] = {
                "podcast": name, "title": title, "audio_path": None,
                "downloaded_at": datetime.now().isoformat(), "skipped": True, "reason": "no_enclosure",
            }
            continue

        # 预告标题过滤：跳过含预告关键词的集
        if is_promo_title(title):
            logger.info(f"[{name}] 标题含预告关键词，跳过: {title[:60]}")
            state[guid] = {
                "podcast": name, "title": title, "audio_path": None,
                "downloaded_at": datetime.now().isoformat(), "skipped": True, "reason": "promo_title",
            }
            _save()
            continue

        # 时长过滤：跳过 < 5 分钟的集
        duration_secs = ep.get("duration_secs", 0)
        if duration_secs > 0 and duration_secs < MIN_DURATION_SECONDS:
            logger.info(f"[{name}] 时长过短（{duration_secs//60}m{duration_secs%60}s），跳过: {title[:50]}")
            state[guid] = {
                "podcast": name, "title": title, "audio_path": None,
                "downloaded_at": datetime.now().isoformat(), "skipped": True, "reason": "too_short_duration",
            }
            _save()
            continue

        # 短集过滤：跳过预告片/广告（<5MB），YouTube 无此检查
        audio_size = ep.get("audio_size", 0)
        if not is_youtube and audio_size > 0 and audio_size < MIN_AUDIO_SIZE_BYTES:
            logger.info(f"[{name}] 音频太短（{audio_size/1024/1024:.1f}MB），跳过: {title[:50]}")
            state[guid] = {
                "podcast": name, "title": title, "audio_path": None,
                "downloaded_at": datetime.now().isoformat(), "skipped": True, "reason": "too_short",
            }
            _save()
            continue

        # 关键词过滤：非 AI/科技相关的集跳过
        if not is_ai_tech_episode(name, title):
            logger.info(f"[{name}] 非 AI/科技相关，跳过: {title[:60]}")
            state[guid] = {
                "podcast": name, "title": title, "audio_path": None,
                "downloaded_at": datetime.now().isoformat(), "skipped": True, "reason": "off_topic",
            }
            _save()
            continue

        today = datetime.now().strftime("%Y-%m-%d")

        if is_youtube:
            # ── YouTube: download subtitles, skip audio ──
            video_id = ep.get("video_id", "")
            if not video_id:
                logger.warning(f"[{name}] No video_id, skipping: {title[:50]}")
                continue
            transcript_dir = SKILL_DIR / "transcripts" / today
            transcript_path = transcript_dir / f"{slugify(name)}.md"
            logger.info(f"[{name}] YouTube 新视频: {title[:60]}")

            # Track retry count from previous attempts
            prev_retry = state.get(guid, {}).get("retry_count", 0)

            result = _download_youtube_subtitles(video_id, feed.get("lang", "en"), transcript_path, logger)
            if result is True:
                state[guid] = {
                    "podcast": name, "title": title, "audio_path": None,
                    "transcript_path": str(transcript_path),
                    "pub_date": ep["pub_date"], "downloaded_at": datetime.now().isoformat(),
                    "description": ep.get("description", ""),
                    "hosts": feed.get("hosts", ""),
                    "lang": feed.get("lang", "en"),
                    "transcribed": True,
                    "source_type": "youtube_subtitle",
                }
                # Write metadata header to transcript (raw description, no LLM extraction)
                from transcribe_queue import _write_episode_meta as _write_meta_enriched, sync_to_obsidian as _sync_to_obsidian
                _write_meta_enriched(transcript_path, state[guid])
                _sync_to_obsidian(transcript_path, logger)
                _save()
                downloaded.append({"podcast": name, "title": title, "audio_path": None,
                                   "transcript_path": str(transcript_path), "guid": guid})
                _notify_episode(name, title, logger, success=True, size_info="📝字幕")
            elif isinstance(result, str):
                # Skip reason returned (e.g. 'too_short_duration')
                reason = result
                state[guid] = {
                    "podcast": name, "title": title, "audio_path": None,
                    "downloaded_at": datetime.now().isoformat(), "skipped": True,
                    "reason": reason,
                    "retry_count": prev_retry + 1 if reason in RETRYABLE_REASONS else 0,
                }
                _save()
                if reason in RETRYABLE_REASONS and prev_retry == 0:
                    _notify_episode(name, title, logger, success=False, error=f"{reason}（第1次失败，将重试）")
            else:
                state[guid] = {
                    "podcast": name, "title": title, "audio_path": None,
                    "downloaded_at": datetime.now().isoformat(), "skipped": True,
                    "reason": "subtitle_download_failed",
                    "retry_count": prev_retry + 1,
                }
                _save()
                if prev_retry == 0:
                    _notify_episode(name, title, logger, success=False, error=f"字幕下载失败（第1次失败，将重试）")
        else:
            # ── RSS podcast: download audio ──
            ext = Path(audio_url.split("?")[0]).suffix or ".mp3"
            filename = f"{slugify(title)}{ext}"
            audio_path = AUDIO_DIR / today / slugify(name) / filename

            if audio_path.exists():
                logger.info(f"[{name}] 文件已存在，跳过下载: {filename}")
                state[guid] = {"podcast": name, "title": title, "audio_path": str(audio_path),
                               "downloaded_at": datetime.now().isoformat()}
                _save()
                downloaded.append({"podcast": name, "title": title, "audio_path": str(audio_path), "guid": guid})
                if len(downloaded) >= limit:
                    break
                continue

            logger.info(f"[{name}] 新集: {title[:60]}")

            # Track retry count from previous attempts
            prev_retry = state.get(guid, {}).get("retry_count", 0)

            # Write downloading state BEFORE starting download (survives kill)
            state[guid] = {
                "podcast": name, "title": title, "audio_path": str(audio_path),
                "downloaded_at": datetime.now().isoformat(),
                "status": "downloading", "skipped": True,
                "reason": "download_timeout",
                "retry_count": prev_retry,
            }
            _save()

            success = download_audio(audio_url, audio_path, logger)

            if success:
                size_mb = audio_path.stat().st_size / 1024 / 1024 if audio_path.exists() else 0
                state[guid] = {
                    "podcast": name, "title": title, "audio_path": str(audio_path),
                    "pub_date": ep["pub_date"], "downloaded_at": datetime.now().isoformat(),
                    "description": ep.get("description", ""),
                    "hosts": feed.get("hosts", ""),
                    "lang": feed.get("lang", "en"),
                }
                _save()
                downloaded.append({"podcast": name, "title": title, "audio_path": str(audio_path), "guid": guid})
                _notify_episode(name, title, logger, success=True, size_info=f"{size_mb:.0f}MB")
            else:
                state[guid] = {
                    "podcast": name, "title": title, "audio_path": str(audio_path),
                    "downloaded_at": datetime.now().isoformat(), "skipped": True,
                    "reason": "download_timeout",
                    "retry_count": prev_retry + 1,
                }
                _save()
                if prev_retry == 0:
                    _notify_episode(name, title, logger, success=False, error=f"下载失败（第1次失败，将重试）")

        if len(downloaded) >= limit:
            break

    logger.info(f"[{name}] 完成，本次下载 {len(downloaded)} 集")
    return downloaded


async def process_feed_async(
    feed: dict[str, str],
    state: dict[str, Any],
    limit: int,
    logger: logging.Logger,
    state_lock: asyncio.Lock,
) -> list[dict[str, Any]]:
    """异步包装（在线程池中运行同步下载，避免阻塞事件循环）。"""
    loop = asyncio.get_event_loop()
    # 取一份 state 副本传给同步函数（写回时加锁）
    local_state: dict[str, Any] = {}
    async with state_lock:
        local_state = dict(state)

    result = await loop.run_in_executor(
        None,
        lambda: process_feed_sync(feed, local_state, limit, logger, auto_save=False),
    )

    # 合并 local_state 写回
    async with state_lock:
        state.update(local_state)
        save_state(state)

    return result


async def run_all_feeds_async(
    feeds: list[dict[str, str]],
    state: dict[str, Any],
    limit: int,
    logger: logging.Logger,
) -> list[dict[str, Any]]:
    """并发处理所有 feed（>=2 个时并发，1 个时直接同步）。"""
    if len(feeds) <= 1:
        results = []
        for feed in feeds:
            r = process_feed_sync(feed, state, limit, logger)
            results.extend(r)
        return results

    logger.info(f"并发处理 {len(feeds)} 个 feed...")
    state_lock = asyncio.Lock()
    tasks = [
        asyncio.create_task(process_feed_async(feed, state, limit, logger, state_lock))
        for feed in feeds
    ]

    try:
        results_list = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=TOTAL_FEEDS_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning(f"部分 feed 超时（>{TOTAL_FEEDS_TIMEOUT}s），继续处理已完成的结果")
        for task in tasks:
            if not task.done():
                task.cancel()
        # Wait briefly for cancellation to propagate
        await asyncio.gather(*tasks, return_exceptions=True)
        results_list = []
        for task in tasks:
            if task.done() and not task.cancelled():
                try:
                    results_list.append(task.result())
                except Exception as e:
                    results_list.append(e)
            else:
                results_list.append(asyncio.CancelledError())

    all_downloaded: list[dict[str, Any]] = []
    for feed, result in zip(feeds, results_list):
        if isinstance(result, Exception):
            logger.error(f"[{feed['name']}] 并发任务异常: {result}")
        else:
            all_downloaded.extend(result)
    return all_downloaded


def _send_telegram(text: str, logger: logging.Logger) -> None:
    """发送单条 Telegram 消息。"""
    dotenv = Path.home() / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
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


def _cleanup_stale_tmp(logger: logging.Logger) -> int:
    """Remove .tmp files older than TMP_MAX_AGE_HOURS. Returns count of removed files."""
    removed = 0
    if not AUDIO_DIR.exists():
        return 0
    now = time.time()
    for tmp_file in AUDIO_DIR.rglob("*.tmp"):
        age_hours = (now - tmp_file.stat().st_mtime) / 3600
        if age_hours > TMP_MAX_AGE_HOURS:
            size_mb = tmp_file.stat().st_size / 1024 / 1024
            logger.info(f"清理残留 .tmp: {tmp_file.name} ({size_mb:.0f}MB, {age_hours:.0f}h)")
            tmp_file.unlink()
            removed += 1
    return removed


def _notify_episode(
    podcast: str, title: str, logger: logging.Logger,
    *, success: bool, size_info: str = "", error: str = "",
) -> None:
    """Send immediate per-episode Telegram notification."""
    if success:
        msg = f"✅ [{podcast}] {title[:50]}"
        if size_info:
            msg += f" ({size_info})"
    else:
        msg = f"❌ [{podcast}] {title[:50]}"
        if error:
            msg += f"\n原因：{error}"
    _send_telegram(msg, logger)


def _write_episode_meta(transcript_path: Path, episode: dict[str, Any]) -> None:
    """在转录文件头部插入节目元信息（主持人、嘉宾、描述），供 Step 3 提炼时参考。"""
    if not transcript_path.exists():
        return
    content = transcript_path.read_text(encoding="utf-8")
    hosts = episode.get("hosts", "")
    desc = episode.get("description", "")
    lang = episode.get("lang", "en")
    meta_lines = [
        f"**节目**：{episode.get('podcast', '')}",
        f"**标题**：{episode.get('title', '')}",
    ]
    if hosts:
        meta_lines.append(f"**主持人**：{hosts}")
    if desc:
        meta_lines.append(f"**节目简介**：{desc[:500]}")
    if lang:
        meta_lines.append(f"**语言**：{lang}")
    meta_block = "\n".join(meta_lines) + "\n"
    # Insert after the first "# 转录结果" line
    if "# 转录结果" in content:
        content = content.replace("# 转录结果\n", "# 转录结果\n\n" + meta_block, 1)
    else:
        content = meta_block + "\n" + content
    transcript_path.write_text(content, encoding="utf-8")


def transcribe_audio(episode: dict[str, Any], logger: logging.Logger) -> bool:
    """对单个 episode 串行转录，完成后删除音频，失败发 Telegram 通知。不重试。"""
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
        "--engine",
        "mlx",
        "--output",
        str(transcript_path),
        "--delete-audio",
    ]

    # Ensure Homebrew bin is in PATH for ffmpeg
    env = os.environ.copy()
    env["PATH"] = "/opt/homebrew/bin:" + env.get("PATH", "")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, env=env)
        if result.returncode == 0:
            _write_episode_meta(transcript_path, episode)
            logger.info(f"[{podcast_name}] 转录完成: {transcript_path}")
            return True
        else:
            err = result.stderr[-500:] if result.stderr else "unknown error"
            logger.error(f"[{podcast_name}] 转录失败 (returncode={result.returncode}): {err}")
            _send_telegram(f"❌ 播客转录失败\n[{podcast_name}] {title[:50]}\n错误：{err}", logger)
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"[{podcast_name}] 转录超时（>1小时）")
        _send_telegram(f"❌ 播客转录超时\n[{podcast_name}] {title[:50]}", logger)
        return False
    except Exception as e:
        logger.error(f"[{podcast_name}] 转录异常: {e}")
        _send_telegram(f"❌ 播客转录异常\n[{podcast_name}] {title[:50]}\n{e}", logger)
        return False


def _collect_today_skipped(
    state: dict[str, Any],
    feed_names: list[str] | None = None,
) -> list[dict[str, str]]:
    """Collect episodes skipped during today's run from state.

    Args:
        feed_names: If provided, only collect skipped entries for these feeds.
                    This prevents cross-feed contamination when running --feed <single>.

    Rules:
    - Permanent skips (non-retryable, or retry_count >= MAX_SKIP_RETRIES): always show.
    - Transient failures (retryable, retry_count < MAX_SKIP_RETRIES): only show on first
      failure (retry_count == 1) to avoid repeated noise on every re-run.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    # Normalize feed names for case-insensitive matching
    feed_names_lower = {n.lower() for n in feed_names} if feed_names else None
    skipped = []
    reason_labels = {
        "off_topic": "非AI/科技",
        "too_short": "时长过短",
        "too_short_duration": "时长<5min",
        "no_subtitles": "无字幕轨道",
        "subtitle_download_failed": "字幕下载失败",
        "subtitle_download_timeout": "字幕超时",
        "extract_info_timeout": "元信息超时",
        "download_timeout": "下载超时",
        "promo_title": "预告/推广",
    }
    for v in state.values():
        if not v.get("skipped"):
            continue
        dl_at = v.get("downloaded_at", "")
        if not dl_at.startswith(today):
            continue
        # Filter by feed if specified (avoids cross-feed noise in --feed mode)
        if feed_names_lower:
            podcast = v.get("podcast", "").lower()
            if not any(fn in podcast or podcast in fn for fn in feed_names_lower):
                continue
        reason = v.get("reason", "unknown")
        retry_count = v.get("retry_count", 0)
        is_retryable = reason in RETRYABLE_REASONS
        # For retryable failures: only notify on first attempt (retry_count == 1)
        # or when permanently skipped (retry_count >= MAX_SKIP_RETRIES).
        # Skip the intermediate retry noise.
        if is_retryable and 1 < retry_count < MAX_SKIP_RETRIES:
            continue
        label = reason_labels.get(reason, reason)
        if is_retryable and retry_count >= MAX_SKIP_RETRIES:
            label += "（已放弃）"
        skipped.append({
            "podcast": v.get("podcast", "?"),
            "title": v.get("title", "?"),
            "reason_label": label,
        })
    return skipped


def send_telegram_notification(
    results: list[dict[str, Any]],
    logger: logging.Logger,
    elapsed_seconds: float = 0,
    error_count: int = 0,
    skipped: list[dict[str, str]] | None = None,
    total_feeds: int = 0,
) -> None:
    elapsed_str = f"{int(elapsed_seconds // 60)}m{int(elapsed_seconds % 60)}s"

    # No new episodes and no skipped: send a brief "all clear" message
    if not results and not skipped:
        _send_telegram(
            f"🎙️ podcast-monitor：今日无新集\n"
            f"⏱ 耗时 {elapsed_str}  |  📡 {total_feeds} feeds 已检查",
            logger,
        )
        logger.info("Telegram 汇总已发送（无新集）")
        return

    total_mb = sum(
        Path(r["audio_path"]).stat().st_size / 1024 / 1024
        for r in results if r.get("audio_path") and Path(r["audio_path"]).exists()
    )
    yt_count = sum(1 for r in results if r.get("transcript_path"))
    header = f"🎙️ podcast-monitor：下载 {len(results)} 个新集完成"
    if total_mb > 0 and yt_count > 0:
        stats = f"⏱ 耗时 {elapsed_str}  |  💾 {total_mb:.0f} MB + 📝 {yt_count} 字幕"
    elif yt_count > 0:
        stats = f"⏱ 耗时 {elapsed_str}  |  📝 {yt_count} 个字幕"
    else:
        stats = f"⏱ 耗时 {elapsed_str}  |  💾 共 {total_mb:.0f} MB"
    if error_count:
        stats += f"  |  ⚠️ {error_count} 次重试"
    lines = [header, stats, ""]
    for r in results:
        audio_path = r.get("audio_path")
        transcript_path = r.get("transcript_path")
        size_str = ""
        if audio_path and Path(audio_path).exists():
            size_mb = Path(audio_path).stat().st_size / 1024 / 1024
            size_str = f" ({size_mb:.0f}MB)"
        elif transcript_path and Path(transcript_path).exists():
            chars = len(Path(transcript_path).read_text(encoding="utf-8"))
            size_str = f" (📝{chars}字)"
        lines.append(f"✅ [{r['podcast']}] {r['title'][:45]}{size_str}")
    # Append skipped episodes summary
    if skipped:
        lines.append("")
        lines.append(f"⏭ 跳过 {len(skipped)} 集：")
        for s in skipped:
            lines.append(f"  • [{s['podcast']}] {s['title'][:40]}（{s['reason_label']}）")
    _send_telegram("\n".join(lines), logger)
    logger.info("Telegram 通知已发送")


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="播客 RSS 增量下载器")
    parser.add_argument("--limit", type=int, default=1, help="每个 feed 最多下载几集（默认 1）")
    parser.add_argument("--dry-run", action="store_true", help="仅检查，不下载")
    parser.add_argument("--feed", help="仅处理指定 feed（按名称匹配，支持部分匹配）")
    args = parser.parse_args()

    logger = setup_logging()
    logger.info(f"=== podcast-monitor RSS 下载器启动 ===")
    logger.info(f"音频目录: {AUDIO_DIR}")
    logger.info(f"状态文件: {STATE_FILE}")

    state = load_state()
    logger.info(f"已记录 {len(state)} 个 episode（历史状态）")

    # Cleanup stale .tmp files from previous killed processes
    removed = _cleanup_stale_tmp(logger)
    if removed:
        logger.info(f"清理了 {removed} 个残留 .tmp 文件")

    feeds_to_check = FEEDS
    if args.feed:
        feeds_to_check = [f for f in FEEDS if args.feed.lower() in f["name"].lower()]
        if not feeds_to_check:
            logger.error(f"未找到匹配的 feed: {args.feed}")
            return 1

    if args.dry_run:
        logger.info("dry-run 模式，仅检查不下载")
        for feed in feeds_to_check:
            try:
                fb = fetch_feed(feed["url"])
                is_yt = feed.get("type") == "youtube"
                eps = parse_youtube_feed(fb) if is_yt else parse_episodes(fb)
                if is_yt:
                    new = [e for e in eps if e["guid"] not in state]
                else:
                    new = [e for e in eps if e["guid"] not in state and e.get("audio_url")]
                logger.info(f"[{feed['name']}] 共 {len(eps)} 集，{len(new)} 集未处理")
            except Exception as e:
                logger.error(f"[{feed['name']}] {e}")
        return 0

    t_start = time.monotonic()
    try:
        all_downloaded = asyncio.run(run_all_feeds_async(feeds_to_check, state, args.limit, logger))
    except Exception as e:
        logger.error(f"run_all_feeds_async 异常: {e}")
        all_downloaded = []
    elapsed = time.monotonic() - t_start

    logger.info(f"=== 完成！本次新下载 {len(all_downloaded)} 集，耗时 {elapsed:.0f}s ===")
    for r in all_downloaded:
        logger.info(f"  • [{r['podcast']}] {r['title'][:60]}")

    # 统计重试次数（日志里 WARNING "下载失败" 行数作为近似）
    log_file = LOG_DIR / f"rss_downloader_{datetime.now().strftime('%Y-%m-%d')}.log"
    error_count = 0
    if log_file.exists():
        error_count = log_file.read_text().count("下载失败:")

    # Reload state to capture all skip entries from concurrent feeds
    state = load_state()
    today_skipped = _collect_today_skipped(state, feed_names=[f["name"] for f in feeds_to_check])

    # Always send summary (even when no new episodes, to confirm cron ran)
    send_telegram_notification(
        all_downloaded, logger,
        elapsed_seconds=elapsed, error_count=error_count,
        skipped=today_skipped,
        total_feeds=len(feeds_to_check),
    )

    # ── detach 转录队列进程（不阻塞 rss_downloader）──
    transcribe_script = SKILL_DIR / "transcribe_queue.py"
    if transcribe_script.exists():
        log_path = LOG_DIR / f"transcribe_queue_{datetime.now().strftime('%Y-%m-%d')}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["PATH"] = "/opt/homebrew/bin:" + env.get("PATH", "")
        with open(log_path, "a") as log_fh:
            proc = subprocess.Popen(
                [PYTHON_BIN, str(transcribe_script)],
                stdout=log_fh, stderr=log_fh,
                start_new_session=True,  # detach from parent process group
                env=env,
            )
        logger.info(f"=== 转录队列已后台启动 (pid={proc.pid})，日志: {log_path} ===")
    else:
        logger.warning("transcribe_queue.py 不存在，跳过转录")

    logger.info("=== RSS 下载器退出 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
