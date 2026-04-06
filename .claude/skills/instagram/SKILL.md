---
name: instagram
description: Control Instagram account via Graph API. Read profile/posts/insights, publish images (from URL or local file via Cloudinary), manage comments. 用户说"发 Instagram"、"查看 IG"、"回复评论"时触发。
user-invocable: true
allowed-tools: Bash Read
---

# Instagram Skill

## What it does
Direct control over an Instagram Creator account via the official Instagram Graph API (graph.instagram.com).

## Quick Usage
```bash
SCRIPT=${CLAUDE_SKILL_DIR}/scripts/instagram_api.py

python3.12 $SCRIPT get_profile
python3.12 $SCRIPT get_posts --limit 10
python3.12 $SCRIPT get_post_insights --post-id POST_ID
python3.12 $SCRIPT publish_image --image-url "https://..." --caption "文案"
python3.12 $SCRIPT publish_from_local --image-path /path/to/image.jpg --caption "文案"
python3.12 $SCRIPT get_comments --post-id POST_ID --limit 20
python3.12 $SCRIPT reply_comment --comment-id COMMENT_ID --message "回复内容"
python3.12 $SCRIPT search_hashtag --hashtag "ai" --limit 10
```

## Workflow
1. Ensure environment variables are set (see Credentials)
2. Run script with tool name + args
3. Parse JSON output, report to user

## Credentials

Required environment variables:
| Key | Purpose |
|-----|---------|
| `INSTAGRAM_ACCESS_TOKEN` | Instagram Login token (IGAAH...) |
| `INSTAGRAM_ACCOUNT_ID` | Numeric account ID |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary cloud name |
| `CLOUDINARY_API_KEY` | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret |

## Cloudinary Integration
`publish_from_local` flow:
1. Local image → Cloudinary upload (URL with random hash)
2. Public URL → Instagram Graph API publish
3. Auto-delete Cloudinary image after publish

## Important Notes
- Token: Instagram Login API (IGAAH prefix), NOT Facebook token (EAAN prefix)
- API base: graph.instagram.com only
- Token expires in 60 days — check expiry, re-generate via Meta Developer when needed
- publish_image needs public URL; publish_from_local accepts local path (auto Cloudinary)
- insights / search_hashtag require Business account (Creator account limited)

## Guardrails
- Never expose INSTAGRAM_ACCESS_TOKEN in output
- Do not publish without explicit user confirmation
- Do not reply to comments without user-provided message

## Error Handling
| Error | Cause | Fix |
|-------|-------|-----|
| 190 Invalid OAuth token | Token expired | Re-generate via Meta Developer |
| 100 Parameter missing | Missing arg | Check --post-id / --comment-id |
| 10 Permission denied | Missing scope | Re-authorize with required permissions |
