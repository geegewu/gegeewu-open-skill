#!/usr/bin/env python3
"""
Note ID recovery layer for XHS publishing.

Responsibilities:
  - Extract note_id from MCP API response URLs
  - Recover note_id from MCP feeds APIs (title-aware matching)
  - Feed parsing, title normalization, timestamp extraction
  - Latest feed fallback validation (time window + title similarity)

This module does NOT handle:
  - Publishing (see publish_pipeline.py)
  - Content preparation (see content_prep.py)
  - MCP lock management (stays in publish_all_in_one)
  - Cookie checking (stays in publish_all_in_one)
"""

import re
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher


def _normalize_title_for_match(text: str) -> str:
    # Keep Chinese/English letters and digits only for robust fuzzy matching.
    if not text:
        return ""
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", text).lower()


def extract_note_id_from_url(url: str) -> str:
    if not url:
        return None
    m = re.search(r"/explore/([A-Za-z0-9]+)", url)
    if m:
        return m.group(1)
    # fallback: URL query style id
    m = re.search(r"[?&](?:note_id|id)=([A-Za-z0-9]+)", url)
    if m:
        return m.group(1)
    return None


def _extract_feeds_from_response(data: dict) -> list:
    """Extract feeds list from different MCP API response shapes."""
    candidates = []
    nodes = [
        data,
        data.get("data", {}) if isinstance(data, dict) else {},
        data.get("data", {}).get("data", {}) if isinstance(data, dict) and isinstance(data.get("data"), dict) else {},
        data.get("result", {}) if isinstance(data, dict) else {},
    ]
    for node in nodes:
        if isinstance(node, dict):
            feeds = node.get("feeds")
            if isinstance(feeds, list):
                candidates.extend([f for f in feeds if isinstance(f, dict)])
    return candidates


def _extract_note_id_and_url_from_feed(feed: dict) -> tuple[str, str]:
    note_id = (
        feed.get("id")
        or feed.get("note_id")
        or feed.get("post_id")
        or (feed.get("post", {}).get("id") if isinstance(feed.get("post"), dict) else None)
        or (feed.get("post", {}).get("note_id") if isinstance(feed.get("post"), dict) else None)
        or (feed.get("post", {}).get("post_id") if isinstance(feed.get("post"), dict) else None)
    )
    note_url = (
        feed.get("url")
        or feed.get("note_url")
        or feed.get("noteUrl")
        or feed.get("post_url")
        or feed.get("postUrl")
        or (feed.get("post", {}).get("url") if isinstance(feed.get("post"), dict) else None)
        or (feed.get("post", {}).get("note_url") if isinstance(feed.get("post"), dict) else None)
    )
    if note_id and not note_url:
        note_url = f"https://www.xiaohongshu.com/explore/{note_id}"
    return (str(note_id) if note_id else None), (str(note_url) if note_url else None)


def _extract_feed_title(feed: dict) -> str:
    note_card = feed.get("noteCard") if isinstance(feed.get("noteCard"), dict) else {}
    return str(
        feed.get("title")
        or feed.get("note_title")
        or feed.get("name")
        or feed.get("post_title")
        or note_card.get("displayTitle")
        or note_card.get("title")
        or ""
    ).strip()


def _title_similarity_score(expected_title: str, feed_title: str) -> float:
    expected_norm = _normalize_title_for_match(expected_title)
    feed_norm = _normalize_title_for_match(feed_title)
    if not expected_norm or not feed_norm:
        return 0.0
    return SequenceMatcher(a=expected_norm, b=feed_norm).ratio()


def _recover_note_id_from_feeds(feeds: list, expected_title: str) -> tuple[str, str, dict]:
    expected_norm = _normalize_title_for_match(expected_title)

    # Prefer title-matched feed to avoid syncing wrong note_id.
    for feed in feeds:
        feed_title = _extract_feed_title(feed)
        feed_norm = _normalize_title_for_match(feed_title)
        if expected_norm and feed_norm and (expected_norm in feed_norm or feed_norm in expected_norm):
            note_id, note_url = _extract_note_id_and_url_from_feed(feed)
            if note_id:
                print(f"  📝 按标题匹配恢复 note_id: {note_id}")
                return note_id, note_url, {
                    "source": "title_match",
                    "similarity": round(_title_similarity_score(expected_title, feed_title), 3),
                }

    # Title match failed: no reliable way to identify the published note.
    # Do NOT fall back to latest feed - it would return a stale/wrong note_id.
    # Returning None triggers uncertain_note_id pending_sync handling upstream.
    return None, None, None


def _parse_timestamp_value(value) -> float:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        ts = float(value)
    else:
        raw = str(value).strip()
        if not raw:
            return None
        if re.fullmatch(r"\d+", raw):
            ts = float(raw)
        else:
            # ISO 8601
            iso_raw = raw.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(iso_raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.timestamp()
            except ValueError:
                pass

            # Common gateway format: 2026-02-16 02:43:00
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                    return dt.timestamp()
                except ValueError:
                    continue
            return None

    # Normalize epoch in ms to seconds
    if ts > 1_000_000_000_000:
        ts = ts / 1000.0
    return ts


def _extract_feed_publish_ts(feed: dict) -> float:
    keys = (
        "publish_time",
        "published_at",
        "publishTime",
        "publishedAt",
        "create_time",
        "created_at",
        "createTime",
        "post_time",
        "postTime",
        "timestamp",
        "time",
    )
    for key in keys:
        if key in feed:
            ts = _parse_timestamp_value(feed.get(key))
            if ts is not None:
                return ts

    nested = feed.get("post")
    if isinstance(nested, dict):
        for key in keys:
            if key in nested:
                ts = _parse_timestamp_value(nested.get(key))
                if ts is not None:
                    return ts
    return None


def _validate_latest_feed_fallback(
    feed: dict,
    expected_title: str,
    now_ts: float = None,
    *,
    min_similarity_bps: int,
    time_window_seconds: int,
) -> dict:
    """Guard latest-feed fallback with both time window and title similarity."""
    if now_ts is None:
        now_ts = time.time()

    min_similarity = min_similarity_bps / 100.0
    feed_title = _extract_feed_title(feed)
    similarity = _title_similarity_score(expected_title, feed_title)
    title_ok = similarity >= min_similarity

    feed_ts = _extract_feed_publish_ts(feed)
    if feed_ts is None:
        return {
            "ok": False,
            "reason": "missing_publish_time",
            "similarity": round(similarity, 3),
            "min_similarity": round(min_similarity, 3),
            "feed_age_seconds": None,
            "time_window_seconds": time_window_seconds,
        }

    age_seconds = now_ts - feed_ts
    # allow small clock skew in the future
    time_ok = (-120.0 <= age_seconds <= float(time_window_seconds))

    if title_ok and time_ok:
        return {
            "ok": True,
            "reason": "ok",
            "similarity": round(similarity, 3),
            "min_similarity": round(min_similarity, 3),
            "feed_age_seconds": int(age_seconds),
            "time_window_seconds": time_window_seconds,
        }

    return {
        "ok": False,
        "reason": "title_or_time_guard_failed",
        "similarity": round(similarity, 3),
        "min_similarity": round(min_similarity, 3),
        "feed_age_seconds": int(age_seconds),
        "time_window_seconds": time_window_seconds,
    }


def recover_note_id_from_mcp(
    mcp_base: str,
    expected_title: str,
    *,
    max_wait: int,
    interval: int,
    request_timeout: int,
) -> tuple[str, str, dict]:
    """Recover note_id from MCP feeds APIs with title-aware matching.

    Returns (note_id, xhs_url, meta) — same contract as the original
    publish_all_in_one.recover_note_id_from_mcp.
    """
    import requests

    deadline = time.time() + max_wait
    attempt = 0
    last_uncertain_meta = None
    # Prefer list endpoint first (lighter and usually more stable), then user/me fallback.
    candidate_paths = ["/api/v1/feeds/list", "/api/v1/user/me"]

    while True:
        if time.time() >= deadline:
            break
        attempt += 1
        for path in candidate_paths:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            timeout = max(1.0, min(float(request_timeout), remaining))
            try:
                resp = requests.get(f"{mcp_base}{path}", timeout=timeout)
                if resp.status_code != 200:
                    continue
                feeds = _extract_feeds_from_response(resp.json())
                if not feeds:
                    continue
                note_id, xhs_url, meta = _recover_note_id_from_feeds(feeds, expected_title)
                if note_id:
                    return note_id, xhs_url, meta
                if meta and meta.get("source") == "latest_feed_guard_reject":
                    last_uncertain_meta = meta
            except Exception as e:
                if attempt == 1:
                    print(f"  ⚠️ note_id 恢复请求异常（{path}，将重试）: {e}")

        if time.time() >= deadline:
            break
        time.sleep(interval)

    return None, None, last_uncertain_meta
