#!/usr/bin/env python3
"""
Publish state management layer for XHS publishing.

Responsibilities:
  - Published lock files (check/mark/path)
  - Pending sync state (write/read/clear)
  - Task ID inference from image filenames

This module does NOT handle:
  - MCP lock management (stays in publish_all_in_one)
  - Cookie checking (stays in publish_all_in_one)
  - Publishing (see publish_pipeline.py)
  - Note ID recovery (see note_recovery.py)
"""

import json
import time
from datetime import datetime
from pathlib import Path


def get_published_lock_path(
    published_lock_dir: Path,
    date_str: str,
    lock_type: str = "narrative",
) -> Path:
    return published_lock_dir / f"published_{lock_type}_{date_str}.lock"


def check_published_today(
    published_lock_dir: Path,
    date_str: str,
    lock_type: str = "narrative",
) -> tuple:
    lock_file = get_published_lock_path(published_lock_dir, date_str, lock_type)
    if lock_file.exists():
        try:
            note_id, ts, title = lock_file.read_text().strip().split("|", 2)
            # UNKNOWN_UNCERTAIN 表示发布不确定，允许重新发布
            if note_id == "UNKNOWN_UNCERTAIN":
                print(f"⚠️  检测到不确定锁（UNKNOWN_UNCERTAIN），允许重新发布")
                return False, ""
            return True, note_id
        except Exception:
            return False, ""
    return False, ""


def mark_published(
    published_lock_dir: Path,
    date_str: str,
    note_id: str,
    title: str,
    lock_type: str = "narrative",
):
    get_published_lock_path(published_lock_dir, date_str, lock_type).write_text(
        f"{note_id}|{datetime.now().isoformat()}|{title}"
    )


def write_pending_sync(
    pending_sync_file: Path,
    note_id,
    title,
    xhs_url,
    task_id,
    image_dir,
    tags,
    content,
    extra: dict = None,
):
    """Write pending_sync.json for idempotent recovery."""
    data = {
        "note_id": note_id,
        "title": title,
        "xhs_url": xhs_url,
        "task_id": task_id,
        "image_dir": str(image_dir),
        "tags": tags,
        "content": content,
        "published_at": datetime.now().isoformat(),
    }
    if extra and isinstance(extra, dict):
        data.update(extra)
    try:
        with open(pending_sync_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  ✓ 已写入恢复标记: {pending_sync_file}")
        return True
    except Exception as e:
        print(f"  ⚠️ 写入恢复标记失败: {e}")
        return False


def read_pending_sync(pending_sync_file: Path):
    """Read pending_sync.json, return data or None."""
    if not pending_sync_file.exists():
        return None
    try:
        with open(pending_sync_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠️ 读取恢复标记失败: {e}")
        return None


def clear_pending_sync(pending_sync_file: Path):
    """Delete pending_sync.json after successful sync."""
    try:
        if pending_sync_file.exists():
            pending_sync_file.unlink()
            print(f"  ✓ 已清除恢复标记")
            return True
    except Exception as e:
        print(f"  ⚠️ 清除恢复标记失败: {e}")
    return False


def infer_task_id_from_images(images: list) -> str:
    if images:
        first_img = Path(images[0]).stem
        if "_cover" in first_img:
            return first_img.replace("_cover", "")
        if "_image_" in first_img:
            return first_img.split("_image_")[0]
    return f"{int(time.time())}_xhs"
