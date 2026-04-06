#!/usr/bin/env python3
"""
scrape-batch-opencli.py
Batch scraper using opencli twitter search (replaces scrape-batch.js Playwright approach).
Output: JSON to stdout (compatible with scrape-batch.js schema). Logs to stderr.

Uses pipelined parallelism: multiple workers overlap API wait time while maintaining
a global rate limit (minimum delay between consecutive opencli calls).

Requires: opencli installed globally (`npm i -g @jackwener/opencli`), Chrome running + extension.
"""
from __future__ import annotations


import json
import os
import subprocess
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

WATCHLIST_PATH = Path(__file__).resolve().parent.parent / "reference" / "watchlist.md"
CACHE_DIR = Path(os.environ.get("X_SCRAPE_CACHE_DIR", Path(__file__).resolve().parent.parent / "cache" / "x-scrape"))
CACHE_TTL_HOURS = int(os.environ.get("X_SCRAPE_CACHE_TTL_HOURS", "20"))
REQUEST_DELAY = float(os.environ.get("X_OPENCLI_DELAY", "5.0"))
MAX_TWEETS = int(os.environ.get("X_OPENCLI_LIMIT", "20"))
MAX_WORKERS = int(os.environ.get("X_OPENCLI_WORKERS", "1"))
OPENCLI_BIN = os.environ.get("OPENCLI_BIN", "/opt/homebrew/bin/opencli")

# Ensure homebrew binaries are in PATH (needed for non-interactive shells / cron)
_homebrew = '/opt/homebrew/bin'
if _homebrew not in os.environ.get('PATH', ''):
    os.environ['PATH'] = _homebrew + ':' + os.environ.get('PATH', '/usr/bin:/bin')

CST = timezone(timedelta(hours=8))

# Global rate limiter: ensures minimum delay between any two opencli calls
_rate_lock = threading.Lock()
_last_call_time = 0.0


def rate_limited_wait():
    """Block until REQUEST_DELAY seconds have passed since the last API call."""
    global _last_call_time
    with _rate_lock:
        now = time.monotonic()
        wait = REQUEST_DELAY - (now - _last_call_time)
        if wait > 0:
            time.sleep(wait)
        _last_call_time = time.monotonic()


def log(msg: str):
    print(f"[scrape-opencli] {msg}", file=sys.stderr, flush=True)


def get_date_key(dt: datetime) -> str:
    return dt.astimezone(CST).strftime("%Y-%m-%d")


def parse_watchlist(path: Path) -> list[str]:
    """Extract @handles from watchlist.md"""
    import re
    text = path.read_text()
    return re.findall(r"^### @([A-Za-z0-9_]+)", text, re.MULTILINE)


def check_cache(handle: str, date_key: str) -> str | None:
    cache_path = CACHE_DIR / handle / f"{date_key}.txt"
    try:
        if cache_path.exists():
            age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
            if age_hours <= CACHE_TTL_HOURS:
                content = cache_path.read_text().strip()
                if content:
                    return content
    except Exception:
        pass
    return None


def write_cache(handle: str, date_key: str, content: str):
    cache_path = CACHE_DIR / handle / f"{date_key}.txt"
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if content:
            cache_path.write_text(content)
    except Exception:
        pass


def format_tweet_content(tweets: list[dict]) -> str:
    """Format structured tweets into readable text content."""
    parts = []
    for t in tweets:
        lines = []
        lines.append(f"@{t.get('author', 'unknown')}")
        lines.append(t.get("text", ""))
        likes = t.get("likes", 0)
        views = t.get("views", "0")
        url = t.get("url", "")
        lines.append(f"Likes: {likes} | Views: {views}")
        if url:
            lines.append(f"URL: {url}")
        parts.append("\n".join(lines))
    return "\n\n---\n\n".join(parts)


def scrape_account(handle: str, since: str, until: str) -> dict:
    """Scrape a single account using opencli twitter search with global rate limiting."""
    rate_limited_wait()

    query = f"from:{handle} since:{since} until:{until}"
    try:
        result = subprocess.run(
            [OPENCLI_BIN, "twitter", "search", query, "--limit", str(MAX_TWEETS), "-f", "json"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            if "No ct0 cookie" in error_msg:
                return {"status": "error", "content": "", "exitCode": 1, "error": "not logged in"}
            return {"status": "error", "content": "", "exitCode": result.returncode, "error": error_msg[:200]}

        tweets = json.loads(result.stdout)
        if not tweets:
            return {"status": "empty", "content": "", "exitCode": 0}

        content = format_tweet_content(tweets)
        return {
            "status": "ok",
            "content": content,
            "exitCode": 0,
            "tweet_count": len(tweets),
            "tweets_raw": tweets,
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "content": "", "exitCode": 1, "error": "timeout (60s)"}
    except json.JSONDecodeError as e:
        return {"status": "error", "content": "", "exitCode": 1, "error": f"JSON parse error: {e}"}
    except Exception as e:
        return {"status": "error", "content": "", "exitCode": 1, "error": str(e)[:200]}


def process_account(handle: str, date_key: str, since: str, until: str, idx: int, total: int) -> tuple[str, dict]:
    """Process one account: check cache, then scrape if needed."""
    cached = check_cache(handle, date_key)
    if cached is not None:
        log(f"@{handle}: cache hit ({idx}/{total})")
        return handle, {"status": "ok" if cached else "empty", "content": cached, "exitCode": 0}

    log(f"@{handle}: searching ({idx}/{total})")
    r = scrape_account(handle, since, until)
    clean = {k: v for k, v in r.items() if k != "tweets_raw"}

    if r["status"] == "ok":
        write_cache(handle, date_key, r["content"])

    return handle, clean


def main():
    handles = parse_watchlist(WATCHLIST_PATH)
    if not handles:
        log("No accounts found in watchlist")
        sys.exit(1)

    now = datetime.now(CST)
    yesterday = now - timedelta(days=1)
    since_date = get_date_key(yesterday)
    until_date = get_date_key(now)
    today_key = get_date_key(now)

    log(f"Starting: {len(handles)} accounts, delay={REQUEST_DELAY}s, workers={MAX_WORKERS}, date={since_date}")

    results = {}
    total = len(handles)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_account, h, today_key, since_date, until_date, i + 1, total): h
            for i, h in enumerate(handles)
        }
        for future in as_completed(futures):
            handle, result = future.result()
            results[handle] = result

    # Build summary
    statuses = [v["status"] for v in results.values()]
    summary = {
        "total": len(statuses),
        "ok": statuses.count("ok"),
        "empty": statuses.count("empty"),
        "error": statuses.count("error"),
    }

    log(f"Done: {summary['ok']} ok, {summary['empty']} empty, {summary['error']} error")
    print(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
