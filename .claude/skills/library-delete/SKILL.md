---
name: library-delete
description: Delete a library entry by slug from all storage locations (Obsidian, INDEX.md, JSON index). 用户说"删除归档"、"移除条目"、"library delete"时触发。
user-invocable: true
allowed-tools: Bash Read
---

# library-delete

Delete a library entry from all 3 storage locations by slug.

## What it does
Removes an entry from:
1. Obsidian vault (via REST API DELETE, recursive)
2. `knowledge-base/INDEX.md` (via REST API GET + PUT)
3. `reference/library-index.json` (direct file edit)

## Quick Usage

```bash
# Delete an entry (auto-detect type from JSON index)
~/myenv/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/delete_entry.py bb-browser --vault-path <VAULT_PATH>

# Override type manually
~/myenv/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/delete_entry.py bb-browser --type project --vault-path <VAULT_PATH>

# Dry run (show what would be deleted)
~/myenv/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/delete_entry.py bb-browser --dry-run --vault-path <VAULT_PATH>
```

## Workflow
1. Receive delete request with slug (e.g. "delete bb-browser")
2. Run delete script
3. Script auto-detects entry type from JSON index (or use `--type`)
4. REST API recursively deletes files, filesystem cleans empty folders
5. Removes entry from INDEX.md and JSON index
6. Report result

## Credentials
- `OBSIDIAN_REST_API_KEY` — Obsidian REST API auth

## Guardrails
- Never delete without explicit user confirmation
- Always run `--dry-run` first if uncertain
- Do not delete entries that other entries depend on without checking

## Error Handling
- REST API unreachable → exit 1, report connection error
- Slug not found → exit 1, report "nothing to delete"
- Partial failure → report which locations succeeded/failed
