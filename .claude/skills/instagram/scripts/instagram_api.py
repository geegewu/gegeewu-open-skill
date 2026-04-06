#!/usr/bin/env python3
"""Instagram Graph API CLI — reads from environment variables."""
import os, sys, json, argparse
import httpx
from pathlib import Path

import cloudinary
import cloudinary.uploader

BASE = "https://graph.instagram.com/v21.0"
TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID", "")

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME", ""),
    api_key=os.getenv("CLOUDINARY_API_KEY", ""),
    api_secret=os.getenv("CLOUDINARY_API_SECRET", ""),
    secure=True
)

def api_get(path, params=None):
    p = {"access_token": TOKEN, **(params or {})}
    r = httpx.get(f"{BASE}{path}", params=p, timeout=15)
    r.raise_for_status()
    return r.json()

def api_post(path, data=None):
    d = {"access_token": TOKEN, **(data or {})}
    r = httpx.post(f"{BASE}{path}", data=d, timeout=15)
    r.raise_for_status()
    return r.json()

def get_profile():
    return api_get("/me", {"fields": "id,username,account_type,followers_count,media_count,biography,website"})

def get_posts(limit=10):
    return api_get("/me/media", {"fields": "id,caption,media_type,timestamp,permalink,like_count,comments_count", "limit": limit})

def get_post_insights(post_id):
    return api_get(f"/{post_id}/insights", {"metric": "impressions,reach,engagement,saved"})

def publish_image(image_url, caption):
    container = api_post(f"/{ACCOUNT_ID}/media", {"image_url": image_url, "caption": caption})
    cid = container.get("id")
    if not cid:
        return {"error": "Failed to create container", "response": container}
    return api_post(f"/{ACCOUNT_ID}/media_publish", {"creation_id": cid})

def get_comments(post_id, limit=20):
    return api_get(f"/{post_id}/comments", {"fields": "id,text,username,timestamp", "limit": limit})

def reply_comment(comment_id, message):
    return api_post(f"/{comment_id}/replies", {"message": message})

def search_hashtag(hashtag, search_type="top_media", limit=10):
    ht = api_get("/ig_hashtag_search", {"q": hashtag, "user_id": ACCOUNT_ID})
    htid = ht.get("data", [{}])[0].get("id")
    if not htid:
        return {"error": f"Hashtag not found: {hashtag}"}
    return api_get(f"/{htid}/{search_type}", {"fields": "id,caption,media_type,permalink", "limit": limit, "user_id": ACCOUNT_ID})

def upload_to_cloudinary(image_path):
    result = cloudinary.uploader.upload(
        image_path,
        resource_type="image",
        type="upload",
        use_filename=False,
        unique_filename=True,
    )
    return result.get("secure_url"), result.get("public_id")

def delete_from_cloudinary(public_id):
    return cloudinary.uploader.destroy(public_id)

def publish_from_local(image_path, caption):
    path = Path(image_path).expanduser()
    if not path.exists():
        return {"error": f"File not found: {image_path}"}
    image_url, public_id = upload_to_cloudinary(str(path))
    if not image_url:
        return {"error": "Cloudinary upload failed"}
    try:
        result = publish_image(image_url, caption)
        return {"published": result, "cloudinary_cleaned": delete_from_cloudinary(public_id)}
    except Exception as e:
        delete_from_cloudinary(public_id)
        raise

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("tool", choices=["get_profile","get_posts","get_post_insights","publish_image","get_comments","reply_comment","search_hashtag","publish_from_local"])
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--post-id")
    p.add_argument("--comment-id")
    p.add_argument("--image-url")
    p.add_argument("--caption")
    p.add_argument("--message")
    p.add_argument("--hashtag")
    p.add_argument("--search-type", default="top_media")
    p.add_argument("--image-path")
    args = p.parse_args()
    try:
        if args.tool == "get_profile": result = get_profile()
        elif args.tool == "get_posts": result = get_posts(args.limit)
        elif args.tool == "get_post_insights": result = get_post_insights(args.post_id)
        elif args.tool == "publish_image": result = publish_image(args.image_url, args.caption)
        elif args.tool == "get_comments": result = get_comments(args.post_id, args.limit)
        elif args.tool == "reply_comment": result = reply_comment(args.comment_id, args.message)
        elif args.tool == "search_hashtag": result = search_hashtag(args.hashtag, args.search_type, args.limit)
        elif args.tool == "publish_from_local": result = publish_from_local(args.image_path, args.caption)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except httpx.HTTPStatusError as e:
        print(json.dumps({"error": str(e), "status": e.response.status_code}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
