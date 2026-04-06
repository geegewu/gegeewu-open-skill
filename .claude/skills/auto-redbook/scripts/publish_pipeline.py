#!/usr/bin/env python3
"""
Publish execution layer for XHS publishing.

Responsibilities:
  - MCP HTTP API publishing (auto-start, cookie check, retry, note_id extraction)
  - Local SDK publishing (fallback)
  - Unified publish entry point with MCP/local routing
  - Payload digest for idempotency

This module does NOT handle:
  - Content preparation
  - Image generation
  - Post-publish sync / archive
  - note_id recovery from feeds (stays in publish_all_in_one for now)
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _publish_via_mcp(
    title, desc, images, topics, private=False,
    *,
    mcp_constants,
    check_cookie_expiry_fn,
    acquire_mcp_lock_fn,
    release_mcp_lock_fn,
    recover_note_id_from_mcp_fn,
    extract_note_id_from_url_fn,
):
    """Publish via xiaohongshu-mcp HTTP API (USE_XHS_MCP=1)."""
    import requests
    import socket as _socket

    c = mcp_constants
    MCP_BASE = os.environ.get("XHS_MCP_URL", "http://localhost:18060")

    # --- Auto-start MCP server ---
    _mcp_bin = Path(__file__).parent.parent / "tools" / "start-xhs-mcp-gegeewu-post.sh"
    _mcp_port = int(MCP_BASE.rstrip("/").split(":")[-1]) if ":" in MCP_BASE else 18060

    def _is_mcp_port_open():
        try:
            with _socket.create_connection(("127.0.0.1", _mcp_port), timeout=c["connect_timeout"]):
                return True
        except Exception:
            return False

    def _kill_mcp():
        subprocess.run(["pkill", "-f", "xiaohongshu-mcp"], check=False)
        time.sleep(2)

    def _start_mcp():
        if _mcp_bin.exists():
            subprocess.Popen(
                [str(_mcp_bin)],
                cwd=str(_mcp_bin.parent),
                stdout=open("/tmp/xhs-mcp.log", "a"),
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            print(f"  🚀 MCP Server 启动中，等待 {c['start_wait']}s...")
            time.sleep(c["start_wait"])
        else:
            print(f"  ⚠️  MCP 启动脚本未找到: {_mcp_bin}")

    print(
        "  ⚙️ MCP参数: "
        f"lock_wait={c['lock_max_wait']}s, "
        f"lock_poll={c['lock_poll_interval']}s, "
        f"start_wait={c['start_wait']}s, "
        f"http_timeout={c['http_timeout']}s, "
        f"attempts={c['max_attempts']}, "
        f"retry_wait={c['retry_wait']}s, "
        f"note_id_recover_wait={c['note_id_recovery_max_wait']}s, "
        f"note_id_req_timeout={c['note_id_recovery_request_timeout']}s, "
        f"latest_feed_window={c['latest_feed_time_window']}s, "
        f"latest_title_min_sim={c['latest_feed_min_title_similarity']}%"
    )

    if not _is_mcp_port_open():
        print("  🔄 MCP 端口未开放，自动启动...")
        _start_mcp()

    # Cookie check
    cookie_ok, cookie_msg = check_cookie_expiry_fn()
    if not cookie_ok:
        print(f"  ❌ {cookie_msg}")
        print("  💡 请从Chrome重新导出cookie到 tools/cookies.json")
        return False, None
    print(f"  ✅ {cookie_msg}")

    # MCP lock
    if not acquire_mcp_lock_fn(
        "publish_note",
        max_wait=c["lock_max_wait"],
        poll_interval=c["lock_poll_interval"],
        stale_lock_minutes=c["stale_lock_minutes"],
    ):
        return False, None

    print(f"  📡 使用 XHS MCP 发布（{MCP_BASE}）...")

    tag_list = [t.strip().lstrip('#') for t in (topics or []) if t.strip()]

    payload = {
        "title": title,
        "content": desc,
        "images": [str(Path(img).resolve()) if not Path(img).is_absolute() else str(img) for img in images],
        "tags": tag_list,
    }

    for attempt in range(1, c["max_attempts"] + 1):
        try:
            print(f"  📡 MCP发布尝试 {attempt}/{c['max_attempts']}...")
            resp = requests.post(
                f"{MCP_BASE}/api/v1/publish",
                json=payload,
                timeout=c["http_timeout"],
            )
            resp.raise_for_status()
            result = resp.json()
            print(f"  ✅ MCP 发布成功: {result.get('message', 'OK')}")

            data = result.get("data", {}) if isinstance(result, dict) else {}
            if not isinstance(data, dict):
                data = {}

            note_id = (
                data.get("post_id")
                or data.get("note_id")
                or data.get("id")
                or data.get("postId")
                or data.get("noteId")
                or (result.get("note_id") if isinstance(result, dict) else None)
                or (result.get("post_id") if isinstance(result, dict) else None)
                or (result.get("id") if isinstance(result, dict) else None)
            )
            note_url = (
                data.get("url")
                or data.get("note_url")
                or data.get("noteUrl")
                or data.get("post_url")
                or data.get("postUrl")
                or (result.get("url") if isinstance(result, dict) else None)
                or (result.get("note_url") if isinstance(result, dict) else None)
            )
            if not note_id and isinstance(data.get("post"), dict):
                post = data.get("post", {})
                note_id = post.get("id") or post.get("note_id") or post.get("post_id")
                note_url = note_url or post.get("url") or post.get("note_url")
            if not note_id and note_url:
                parsed_id = extract_note_id_from_url_fn(str(note_url))
                if parsed_id:
                    note_id = parsed_id
                    print(f"  📝 从返回URL解析 note_id: {note_id}")

            if not note_id:
                note_id, recovered_url, recovery_meta = recover_note_id_from_mcp_fn(
                    MCP_BASE,
                    expected_title=title,
                    max_wait=c["note_id_recovery_max_wait"],
                    interval=c["note_id_recovery_interval"],
                    request_timeout=c["note_id_recovery_request_timeout"],
                )
                if recovered_url:
                    print(f"  🔗 恢复到笔记链接: {recovered_url}")
                elif recovery_meta and recovery_meta.get("source") == "latest_feed_guard_reject":
                    print(f"  ⚠️ latest feed 回退被双重校验拒绝: {recovery_meta}")

            release_mcp_lock_fn()
            return True, note_id

        except Exception as e:
            print(f"  ❌ 尝试 {attempt}/{c['max_attempts']} 失败: {e}")
            if attempt < c["max_attempts"]:
                print(f"  ⏳ 等待{c['retry_wait']}s后重试...")
                time.sleep(c["retry_wait"])
            else:
                print("  🔍 所有尝试均失败，检查帖子是否已实际发出...")
                note_id, recovered_url, recovery_meta = recover_note_id_from_mcp_fn(
                    MCP_BASE,
                    expected_title=title,
                    max_wait=c["note_id_recovery_max_wait"],
                    interval=c["note_id_recovery_interval"],
                    request_timeout=c["note_id_recovery_request_timeout"],
                )
                release_mcp_lock_fn()
                if note_id:
                    print(f"  ✅ 帖子已实际发出（MCP 返回错误为误报），note_id: {note_id}")
                    if recovered_url:
                        print(f"  🔗 笔记链接: {recovered_url}")
                    return True, note_id
                print(f"  ❌ 确认发布失败: MCP 服务器返回错误（尝试 {c['max_attempts']}/{c['max_attempts']} 次均失败）")
                return False, None


def publish_payload_digest(title, desc, images, topics) -> str:
    """Compute SHA256 digest of publish payload for idempotency."""
    payload = {
        "title": str(title),
        "desc": str(desc),
        "images": [str(Path(img).resolve()) for img in images],
        "topics": [str(t).strip() for t in (topics or [])],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _publish_via_local(
    title,
    desc,
    images,
    topics,
    private=False,
    payload_digest=None,
    append_tag_text=True,
):
    """Publish via local xhs SDK (LocalPublisher)."""
    if payload_digest:
        print(f"  🧾 fallback payload_digest={payload_digest}")

    # Check dependencies
    try:
        subprocess.run([sys.executable, "-c", "import dotenv, requests"], check=True)
    except subprocess.CalledProcessError:
        print("❌ 缺少依赖，使用 --break-system-packages 安装...")
        subprocess.run([
            sys.executable, "-m", "pip", "install",
            "--break-system-packages",
            "python-dotenv", "requests", "xhs"
        ], check=False)

    # Use LocalPublisher
    sys.path.insert(0, str(Path(__file__).parent))
    from publish_xhs import LocalPublisher, load_cookie
    cookie = load_cookie()
    publisher = LocalPublisher(cookie)
    publisher.init_client()

    # Resolve topic keywords
    resolved_topics = []
    if topics:
        print("\n🏷️ 解析话题标签...")
        resolved_topics = publisher.resolve_topics(topics)
        print(f"  ✅ 成功解析 {len(resolved_topics)}/{len(topics)} 个话题\n")

    # Append tag text to desc (XHS hash_tag param doesn't render clickable tags)
    desc_for_publish = desc
    tag_text = " ".join([f"#{t.strip().lstrip('#')}" for t in (topics or []) if t.strip()])
    if append_tag_text and tag_text:
        desc_for_publish = f"{desc_for_publish}\n\n{tag_text}"

    result = publisher.publish(
        title=title,
        desc=desc_for_publish,
        images=images,
        is_private=private,
        topics=resolved_topics,
    )

    if result:
        note_id = None
        if isinstance(result, dict):
            note_id = result.get('note_id') or result.get('id')
        return True, note_id
    return False, None


def publish_note(
    title, desc, images, topics, private=False,
    *,
    mcp_constants,
    mcp_fallback_on_fail,
    check_cookie_expiry_fn,
    acquire_mcp_lock_fn,
    release_mcp_lock_fn,
    recover_note_id_from_mcp_fn,
    extract_note_id_from_url_fn,
):
    """Unified publish entry point."""
    print("\n🚀 发布小红书笔记...\n")

    if private:
        print("🔒 私密模式：仅自己可见\n")

    payload_digest = publish_payload_digest(title, desc, images, topics)
    print(f"  🧾 publish payload_digest={payload_digest}")

    if os.environ.get("USE_XHS_MCP") == "1":
        mcp_ok, note_id = _publish_via_mcp(
            title, desc, images, topics, private,
            mcp_constants=mcp_constants,
            check_cookie_expiry_fn=check_cookie_expiry_fn,
            acquire_mcp_lock_fn=acquire_mcp_lock_fn,
            release_mcp_lock_fn=release_mcp_lock_fn,
            recover_note_id_from_mcp_fn=recover_note_id_from_mcp_fn,
            extract_note_id_from_url_fn=extract_note_id_from_url_fn,
        )
        if mcp_ok:
            return mcp_ok, note_id
        if mcp_fallback_on_fail:
            print("  ⚠️ MCP 失败，启用 fallback（严格复用同一 payload）")
            return _publish_via_local(
                title, desc, images, topics, private,
                payload_digest=payload_digest,
                append_tag_text=False,
            )
        print("  ⛔ MCP 失败，未开启 fallback（XHS_MCP_FALLBACK_ON_FAIL=0）")
        return False, None

    return _publish_via_local(title, desc, images, topics, private, payload_digest=payload_digest)
