# Auto-Redbook Workflow Details

## End-to-End Flow

### Phase 0: Input Normalization
- Read source markdown.
- Ensure front matter exists (`title`, `emoji`, `tags`, `style`).
- For digest input, keep structure and card semantics unchanged.

### Phase 1: Image Generation
- Entry: `scripts/generate_xhs_images.py`
- Branches:
  - `style: digest` -> local renderer (`digest_card_renderer.py`), fast deterministic output
  - non-digest -> Gemini pipeline with key rotation and retries
- Output: `{task_id}_xhs_image_N.(jpg|png)` (+ optional cover)

### Phase 2: Publish
- Entry: `scripts/publish_all_in_one.py` → `orchestrator.run_publish_flow()` → `publish_pipeline.publish_note()`
- Primary path: MCP publish (`USE_XHS_MCP=1`) via `publish_pipeline._publish_via_mcp()`
- Fallback path: local publisher (`publish_pipeline._publish_via_local()` → `publish_xhs.py`)

### Phase 3: note_id Recovery (when MCP response id is empty)
- Prefer `POST /api/v1/publish` response id/url parsing.
- If missing, query `GET /api/v1/user/me`:
  1. title-matched feed first
  2. Title match failed → return None (no latest-feed fallback).
- If uncertain: keep `pending_sync.json` with `sync_state=uncertain_note_id` and stop write-back.
- Recovery logic lives in `note_recovery.py`.

### Phase 4: Sync Write-back
- Entry: `scripts/auto_sync_after_publish.py`
- Trigger condition: only when note_id is confirmed.
- Mode: background fire-and-forget (`/tmp/xhs_sync.log`).
- Targets:
  - Feishu Bitable (direct HTTP API)
  - Notion database (direct Notion API)

### Phase 5: Archive and State
- Archive markdown + images + sync metadata to:
  `archive/YYYY-MM-DD/<task_id>_<doc_name>/`
- State files:
  - `pending_sync.json`: pending/uncertain recovery state
  - `locks/published_{lock_type}_YYYY-MM-DD.lock`: daily idempotency guard

## Operational Controls

### MCP Performance Knobs
- `XHS_MCP_LOCK_MAX_WAIT`
- `XHS_MCP_LOCK_POLL_INTERVAL`
- `XHS_MCP_STALE_LOCK_MINUTES`
- `XHS_MCP_CONNECT_TIMEOUT`
- `XHS_MCP_START_WAIT_SECONDS`
- `XHS_MCP_HTTP_TIMEOUT`
- `XHS_MCP_MAX_ATTEMPTS`
- `XHS_MCP_RETRY_WAIT_SECONDS`

### note_id Recovery Knobs
- `XHS_MCP_NOTE_ID_RECOVERY_MAX_WAIT`
- `XHS_MCP_NOTE_ID_RECOVERY_INTERVAL`
- `XHS_MCP_NOTE_ID_RECOVERY_REQUEST_TIMEOUT`
- `XHS_MCP_LATEST_FEED_TIME_WINDOW_SECONDS`
- `XHS_MCP_LATEST_FEED_MIN_TITLE_SIMILARITY_BPS`

## Data Path Summary

```text
markdown -> rewritten.md
  -> publish_all_in_one.py (thin entry)
    -> orchestrator.run_publish_flow()
      -> content_prep.py (parse, tags, length)
      -> generate_xhs_images.py (image gen)
      -> publish_pipeline.py (MCP/local publish)
      -> note_recovery.py (note_id recovery if needed)
      -> publish_state.py (lock, pending_sync)
      -> orchestrator.trigger_post_publish_sync()
        -> auto_sync_after_publish.py -> archive/sync_record.json
  -> (uncertain note_id) pending_sync.json retained for safe recovery
```
