# Troubleshooting

## High-Frequency Failures

### 1) MCP publish is slow or hangs
Symptoms:
- publish step stalls for minutes
- repeated lock wait messages

Checks:
- verify MCP params printed at runtime
- verify lock file state: `/tmp/xhs_mcp.lock`

Actions:
- use bounded settings in `~/.env`:
  - `XHS_MCP_LOCK_MAX_WAIT=180`
  - `XHS_MCP_HTTP_TIMEOUT=90`
  - `XHS_MCP_MAX_ATTEMPTS=2`
- clear stale lock only when no active publish process.

### 2) note_id missing after MCP success
Symptoms:
- MCP says success, but no note_id in response

Expected behavior:
- script auto-runs `/api/v1/user/me` recovery
- latest-feed fallback must pass dual guard (time window + title similarity)

If recovery still fails:
- `pending_sync.json` is kept with `sync_state=uncertain_note_id`
- write-back to Feishu/Notion is intentionally skipped

### 3) Feishu/Notion write-back missing
Symptoms:
- post is published but no record in Feishu/Notion

Checks:
- `tail -n 200 /tmp/xhs_sync.log`
- inspect latest `archive/**/sync_record.json`
- inspect `pending_sync.json`

Actions:
- if `pending_sync.json` exists and note_id empty, run recovery path first
- if API auth fails, verify env keys:
  - `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_BITABLE_*`
  - `NOTION_API_KEY`, `NOTION_DATABASE_ID`

### 4) Digest image generation unexpectedly slow
Symptoms:
- digest content routes to Gemini path

Checks:
- verify front matter `style: digest`

Actions:
- use current code path where front matter style has priority over CLI style.

## Safe Verification Commands

```bash
cd ~/gegeewu-skills/.claude/skills/auto-redbook

# run once
python3 scripts/publish_all_in_one.py /tmp/test.md --num-images 4 --skip-cover

# inspect sync log
tail -n 200 /tmp/xhs_sync.log

# inspect pending state
cat pending_sync.json 2>/dev/null || echo "pending_sync.json not exists"
```

## Dependency Notes

- `publish_all_in_one.py` orchestrates image -> publish -> sync -> archive
- `auto_sync_after_publish.py` performs direct Feishu/Notion API write-back (not MCP)
- `generate_xhs_images.py` handles digest/local renderer and non-digest/Gemini branches
