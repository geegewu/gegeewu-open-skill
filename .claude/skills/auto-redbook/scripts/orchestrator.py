#!/usr/bin/env python3
"""
Orchestrator layer for XHS publishing workflow.

Responsibilities:
  - Wire together content_prep, publish_pipeline, note_recovery, publish_state
  - Recovery flow (pending_sync.json continuation)
  - Main publish flow split into 3 steps with Telegram notifications:
    Step 1: Content preparation (prerequisites + parse + tags + length)
    Step 2: Image generation (subprocess to generate_xhs_images.py)
    Step 3: Publish + sync (MCP publish + note_id recovery + Feishu/Notion)
  - Post-publish sync trigger (subprocess + Telegram notification)

This module does NOT handle:
  - CLI argument parsing (stays in publish_all_in_one main())
  - Constant definitions (stays in publish_all_in_one)
  - MCP lock management (stays in publish_all_in_one)
  - Prerequisites checking (stays in publish_all_in_one)
"""

import json
import os
import re
import subprocess
import time
from pathlib import Path


def _get_telegram_token() -> str | None:
    """Get Telegram bot token from env or ~/.env."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN_GEGEEWU_POST") or os.environ.get("TELEGRAM_BOT_TOKEN")
    if token:
        return token
    env_path = Path.home() / ".env"
    if not env_path.exists():
        return None
    for key in ("TELEGRAM_BOT_TOKEN_GEGEEWU_POST", "TELEGRAM_BOT_TOKEN"):
        for line in env_path.read_text().splitlines():
            m = re.match(rf"^{key}=(.+)$", line.strip())
            if m:
                return m.group(1).strip().strip('"').strip("'")
    return None


def _send_step_notification(step: int, message: str):
    """Send Telegram notification after a step completes. Fire-and-forget."""
    try:
        token = _get_telegram_token()
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not token:
            print(f"  ⚠️ Step {step} 通知跳过：未配置 Telegram token")
            return
        subprocess.run(
            ["curl", "-s", "-X", "POST",
             f"https://api.telegram.org/bot{token}/sendMessage",
             "-d", f"chat_id={chat_id}",
             "-d", f"text={message}"],
            capture_output=True, text=True, timeout=5,
        )
        print(f"  📨 Step {step} 通知已发送")
    except Exception as e:
        print(f"  ⚠️ Step {step} 通知发送失败: {e}")


def trigger_post_publish_sync(
    *,
    sync_script: Path,
    python_bin: str,
    note_id: str,
    title: str,
    xhs_url: str,
    md_file: Path,
    output_dir: Path,
    task_id: str,
    topics: list,
):
    """Launch auto_sync_after_publish.py in background + send Telegram notification."""
    sync_cmd = [
        python_bin,
        str(sync_script),
        "--note-id", note_id,
        "--note-url", xhs_url,
        "--content-file", str(md_file),
        "--image-dir", str(output_dir),
        "--title", title,
        "--task-id", task_id,
    ]
    if topics:
        sync_cmd.extend(["--tags"] + list(topics))

    subprocess.Popen(
        sync_cmd,
        stdout=open("/tmp/xhs_sync.log", "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    print("  🔄 Feishu/Notion同步已后台启动（fire-and-forget，日志: /tmp/xhs_sync.log）")

    # Step 3 completion notification
    _send_step_notification(3, (
        f"✅ Step 3 完成：发布成功\n"
        f"📌 {title}\n"
        f"🔗 {xhs_url}\n"
        f"🔄 Feishu/Notion 回写进行中..."
    ))


def run_recovery_flow(
    pending_data: dict,
    *,
    skill_dir: Path,
    python_bin: str,
    pending_sync_file: Path,
    recover_note_id_from_mcp_fn,
    clear_pending_sync_fn,
    run_command_streaming_fn,
    mcp_recovery_constants: dict,
) -> int:
    """Recovery flow: continue from pending_sync.json.

    Returns exit code (0=success, 1=sync failed, 2=uncertain note_id).
    """
    print("🔄 检测到未完成的同步任务，进入恢复模式...\n")
    print(f"   笔记ID: {pending_data.get('note_id') or '(未确定)'}")
    print(f"   标题: {pending_data.get('title')}")
    print(f"   发布时间: {pending_data.get('published_at')}\n")

    # note_id uncertain: try MCP recovery first
    if not str(pending_data.get("note_id") or "").strip():
        print("⚠️ pending 中 note_id 不确定，先执行安全恢复（双重校验）...")
        mcp_base = os.environ.get("XHS_MCP_URL", "http://localhost:18060")
        recovered_note_id, recovered_url, recover_meta = recover_note_id_from_mcp_fn(
            mcp_base,
            expected_title=str(pending_data.get("title") or ""),
            max_wait=mcp_recovery_constants["max_wait"],
            interval=mcp_recovery_constants["interval"],
            request_timeout=mcp_recovery_constants["request_timeout"],
        )
        if not recovered_note_id:
            pending_data["sync_state"] = "uncertain_note_id"
            if recover_meta:
                pending_data["note_id_recovery_meta"] = recover_meta
            try:
                with open(pending_sync_file, "w", encoding="utf-8") as f:
                    json.dump(pending_data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            print("❌ note_id 仍未确定，保留 pending，避免错误回写")
            print(f"   恢复文件: {pending_sync_file}")
            return 2

        pending_data["note_id"] = recovered_note_id
        pending_data["xhs_url"] = recovered_url or f"https://www.xiaohongshu.com/explore/{recovered_note_id}"
        pending_data["sync_state"] = "ready_after_recovery"
        if recover_meta:
            pending_data["note_id_recovery_meta"] = recover_meta
        with open(pending_sync_file, "w", encoding="utf-8") as f:
            json.dump(pending_data, f, ensure_ascii=False, indent=2)
        print(f"✅ note_id 已恢复: {recovered_note_id}，继续执行同步\n")

    # Run sync
    sync_script = skill_dir / "scripts" / "auto_sync_after_publish.py"
    sync_cmd = [
        python_bin,
        str(sync_script),
        "--note-id", pending_data["note_id"],
        "--note-url", pending_data["xhs_url"],
        "--content-file", pending_data["content"],
        "--image-dir", pending_data["image_dir"],
        "--title", pending_data["title"],
        "--task-id", pending_data["task_id"],
    ]
    if pending_data.get("tags"):
        sync_cmd.extend(["--tags"] + list(pending_data["tags"]))

    sync_return_code, _ = run_command_streaming_fn(sync_cmd)

    if sync_return_code == 0:
        print("\n✅ 恢复同步完成！")
        clear_pending_sync_fn()
        print("\n🎉 任务全部完成！")
        return 0
    else:
        print("\n❌ 同步仍然失败，保留恢复标记以便下次重试")
        print(f"   恢复文件: {pending_sync_file}")
        return 1


def run_publish_flow(
    *,
    md_file: Path,
    output_dir: str,
    num_images: int,
    is_private: bool,
    skip_check: bool,
    skip_cover: bool,
    lock_type: str,
    today_str: str,
    skill_dir: Path,
    python_bin: str,
    pending_sync_file: Path,
    content_limit: int,
    mcp_content_max: int,
    soft_content_limit: int,
    mcp_recovery_constants: dict,
    # Function dependencies
    check_prerequisites_fn,
    parse_markdown_frontmatter_fn,
    validate_digest_publish_input_fn,
    prepare_content_fn,
    extract_tags_fn,
    enforce_content_limit_fn,
    extract_generated_images_fn,
    run_command_streaming_fn,
    publish_note_fn,
    recover_note_id_from_mcp_fn,
    write_pending_sync_fn,
    mark_published_fn,
    infer_task_id_from_images_fn,
) -> int:
    """Main publish flow: 3 steps with Telegram notifications.

    Step 1: Content preparation
    Step 2: Image generation
    Step 3: Publish + sync

    Returns exit code (0=success, 1=failure, 2=uncertain note_id).
    """

    # ================================================================
    # Step 1: Content Preparation
    # ================================================================
    print("=" * 60)
    print("📝 Step 1: 内容准备")
    print("=" * 60)

    # 1a. Prerequisites
    if not skip_check:
        if not check_prerequisites_fn():
            print("\n❌ 前置条件检查失败，请先完成配置")
            _send_step_notification(1, "❌ Step 1 失败：前置条件检查未通过")
            return 1
    else:
        print("⚡ 跳过前置条件检查（快速测试模式）\n")

    # 1b. Prepare content
    metadata, _ = parse_markdown_frontmatter_fn(md_file)
    validate_digest_publish_input_fn(md_file, metadata, skip_cover)

    title, desc, doc_style = prepare_content_fn(md_file)

    # 1c. Extract tags
    topics = extract_tags_fn(metadata, md_file)

    # 1d. Content length enforcement
    tag_text = " ".join([f"#{t}" for t in topics])

    use_mcp = os.environ.get("USE_XHS_MCP") == "1"
    effective_limit = soft_content_limit
    if use_mcp:
        effective_limit = min(effective_limit, mcp_content_max)
        print(
            f"\nℹ️ 长度策略: soft={soft_content_limit}, "
            f"mcp_hard={mcp_content_max}, effective={effective_limit}"
        )
    else:
        print(f"\nℹ️ 长度策略: soft={soft_content_limit}, effective={effective_limit}")

    desc, full_text = enforce_content_limit_fn(title, desc, tag_text, effective_limit, doc_style)

    # Step 1 complete
    print(f"\n✅ Step 1 完成\n")
    _send_step_notification(1, (
        f"✅ Step 1 完成：文案准备就绪\n"
        f"📌 {title}\n"
        f"🎨 风格: {doc_style} | 话题: {len(topics)}个\n"
        f"📊 {len(full_text)}字 / {effective_limit}字限制"
    ))

    # ================================================================
    # Step 2: Image Generation
    # ================================================================
    print("=" * 60)
    print(f"🎨 Step 2: 图片生成（{num_images} 张）")
    print("=" * 60)

    img_script = skill_dir / "scripts" / "generate_xhs_images.py"
    publish_task_id = f"{int(time.time())}_xhs"
    img_cmd = [
        python_bin, str(img_script),
        str(md_file),
        "--num-images", str(num_images),
        "--output-dir", output_dir,
        "--style", doc_style,
        "--task-id", publish_task_id,
    ]
    if skip_cover:
        img_cmd.append("--skip-cover")

    return_code, combined_output = run_command_streaming_fn(img_cmd)

    if return_code != 0:
        print("❌ 图片生成失败")
        if not combined_output.strip():
            print("（无详细日志输出）")
        print("\n小红书帖子必须配图，无法发布纯文字版")
        print("\n可能原因：")
        print("  1. Gemini API 配额用完（等待重置：UTC 00:00）")
        print("  2. Gemini 返回文本而非图片")
        print("  3. 网络问题或 API 异常")
        _send_step_notification(2, (
            f"❌ Step 2 失败：图片生成失败\n"
            f"📌 {title}\n"
            f"🚨 exit_code={return_code}"
        ))
        return 1

    images = extract_generated_images_fn(combined_output, Path(output_dir).resolve(), publish_task_id)

    if not images:
        print(f"❌ 未找到生成的图片文件（task_id={publish_task_id}）")
        print(combined_output)
        _send_step_notification(2, (
            f"❌ Step 2 失败：未找到生成的图片\n"
            f"📌 {title}\n"
            f"🔑 task_id={publish_task_id}"
        ))
        return 1

    # Step 2 complete
    # Show image paths relative to skill_dir for readability
    skill_dir_resolved = skill_dir.resolve()
    rel_images = []
    for img in images:
        try:
            rel_images.append(str(Path(img).relative_to(skill_dir_resolved)))
        except ValueError:
            rel_images.append(img)

    print(f"\n✅ Step 2 完成：{len(images)} 张图片\n")
    for ri in rel_images:
        print(f"  📷 {ri}")

    _send_step_notification(2, (
        f"✅ Step 2 完成：{len(images)}张图片生成成功\n"
        f"📌 {title}\n"
        f"🎨 风格: {doc_style}\n"
        f"📷 " + " / ".join(Path(ri).name for ri in rel_images)
    ))

    # ================================================================
    # Step 3: Publish + Sync
    # ================================================================
    print("\n" + "=" * 60)
    print("🚀 Step 3: 发布")
    print("=" * 60)

    # 3a. Pre-publish summary
    print(f"\n话题: {', '.join(topics)}\n")
    print(f"标题: {title} ({len(title)}字)")
    print(f"图片: {len(images)} 张")
    print(f"正文: {len(desc)} 字")
    print(f"话题: {len(topics)} 个 ({len(tag_text)}字)")
    print(f"总长度: {len(full_text)} 字 / {effective_limit} 字限制")

    # 3b. Publish
    success, note_id = publish_note_fn(title, desc, images, topics, private=is_private)

    if not success:
        print("\n❌ 发布失败，请检查错误信息")
        _send_step_notification(3, (
            f"❌ Step 3 失败：发布失败\n"
            f"📌 {title}"
        ))
        return 1

    print("\n🎉 发布完成！")
    note_id_recovery_meta = None

    # 3c. Post-publish note_id recovery (if MCP didn't return one)
    if not note_id and os.environ.get("USE_XHS_MCP") == "1":
        mcp_base = os.environ.get("XHS_MCP_URL", "http://localhost:18060")
        print("\n🔎 尝试恢复 note_id（用于飞书/Notion同步）...")
        note_id, recovered_url, note_id_recovery_meta = recover_note_id_from_mcp_fn(
            mcp_base,
            expected_title=title,
            max_wait=mcp_recovery_constants["max_wait"],
            interval=mcp_recovery_constants["interval"],
            request_timeout=mcp_recovery_constants["request_timeout"],
        )
        if recovered_url:
            print(f"  🔗 已恢复链接: {recovered_url}")
        elif note_id_recovery_meta:
            print(f"  ⚠️ note_id 恢复未通过安全校验: {note_id_recovery_meta}")

    # 3d. Post-publish sync or uncertain handling
    if note_id:
        print("\n🔄 开始自动同步到飞书和Notion...")
        sync_script = skill_dir / "scripts" / "auto_sync_after_publish.py"
        xhs_url = f"https://www.xiaohongshu.com/explore/{note_id}"

        task_id = infer_task_id_from_images_fn(images)

        write_pending_sync_fn(
            note_id=note_id,
            title=title,
            xhs_url=xhs_url,
            task_id=task_id,
            image_dir=Path(output_dir).resolve(),
            tags=topics,
            content=str(md_file.resolve()),
        )
        if lock_type != "narrative":
            mark_published_fn(today_str, note_id or "", title, lock_type)

        trigger_post_publish_sync(
            sync_script=sync_script,
            python_bin=python_bin,
            note_id=note_id,
            title=title,
            xhs_url=xhs_url,
            md_file=md_file.resolve(),
            output_dir=Path(output_dir).resolve(),
            task_id=task_id,
            topics=topics,
        )
        return 0
    else:
        task_id = infer_task_id_from_images_fn(images)
        uncertain_extra = {
            "sync_state": "uncertain_note_id",
            "uncertain_reason": "MCP latest feed fallback rejected by time-window + title-similarity guard",
        }
        if note_id_recovery_meta:
            uncertain_extra["note_id_recovery_meta"] = note_id_recovery_meta
            uncertain_extra["candidate_note_id"] = note_id_recovery_meta.get("candidate_note_id")
            uncertain_extra["candidate_url"] = note_id_recovery_meta.get("candidate_url")

        write_pending_sync_fn(
            note_id="",
            title=title,
            xhs_url="",
            task_id=task_id,
            image_dir=Path(output_dir).resolve(),
            tags=topics,
            content=str(md_file.resolve()),
            extra=uncertain_extra,
        )
        if lock_type != "narrative":
            mark_published_fn(today_str, "UNKNOWN_UNCERTAIN", title, lock_type)

        _send_step_notification(3, (
            f"⚠️ Step 3 完成但 note_id 不确定\n"
            f"📌 {title}\n"
            f"🔄 已保留 pending_sync，可稍后重试"
        ))
        print("\n⚠️ 未获取到可确认 note_id，已标记不确定并保留 pending")
        print(f"   恢复文件: {pending_sync_file}")
        print("   可稍后直接重试：python3 scripts/publish_all_in_one.py")
        return 2
