#!/usr/bin/env python3
"""Delete a library entry from all 3 storage locations."""

import argparse
import json
import os
import re
import shutil
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_BASE = "https://127.0.0.1:27124"
# Locate library-index.json: walk up from script to find repo root (has CLAUDE.md)
def _find_repo_root():
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(10):
        if os.path.exists(os.path.join(d, "CLAUDE.md")):
            return d
        d = os.path.dirname(d)
    return os.path.dirname(os.path.abspath(__file__))

INDEX_JSON = os.path.join(_find_repo_root(), "reference", "library-index.json")
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def get_api_key():
    key = os.environ.get("OBSIDIAN_REST_API_KEY")
    if not key:
        for env_path in [
            os.path.expanduser("~/.env"),
            os.path.expanduser("~/.env"),
        ]:
            if os.path.exists(env_path):
                with open(env_path) as f:
                    for line in f:
                        if line.startswith("OBSIDIAN_REST_API_KEY="):
                            key = line.strip().split("=", 1)[1].strip("\"'")
                            break
            if key:
                break
    if not key:
        print("ERROR: OBSIDIAN_REST_API_KEY not found", file=sys.stderr)
        sys.exit(1)
    return key


def api_request(method, path, api_key, body=None, content_type=None):
    url = f"{API_BASE}{path}"
    data = body.encode("utf-8") if body else None
    req = Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {api_key}")
    if content_type:
        req.add_header("Content-Type", content_type)
    try:
        with urlopen(req, context=SSL_CTX) as resp:
            return resp.status, resp.read().decode("utf-8")
    except HTTPError as e:
        return e.code, e.read().decode("utf-8")
    except URLError as e:
        print(f"ERROR: REST API unreachable: {e.reason}", file=sys.stderr)
        sys.exit(1)


def delete_from_json_index(slug):
    index_path = os.path.normpath(INDEX_JSON)
    if not os.path.exists(index_path):
        print(f"WARN: {index_path} not found, skipping JSON index", file=sys.stderr)
        return False

    with open(index_path) as f:
        entries = json.load(f)

    original_count = len(entries)
    entries = [e for e in entries if e.get("slug") != slug]

    if len(entries) == original_count:
        print(f"  JSON index: slug '{slug}' not found, skipping")
        return False

    with open(index_path, "w") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"  JSON index: removed '{slug}' ({original_count} -> {len(entries)})")
    return True


def list_vault_dir(api_path, api_key):
    """List files in a vault directory. Returns list of filenames or empty list."""
    status, body = api_request("GET", api_path, api_key)
    if status != 200:
        return []
    try:
        data = json.loads(body)
        return data.get("files", [])
    except json.JSONDecodeError:
        return []


def delete_vault_recursive(dir_path, api_key):
    """Delete all files in a vault directory recursively via REST API."""
    files = list_vault_dir(dir_path, api_key)
    deleted = 0
    for f in files:
        full = dir_path.rstrip("/") + "/" + f
        if f.endswith("/"):
            # Subdirectory — recurse
            deleted += delete_vault_recursive(full, api_key)
        else:
            status, _ = api_request("DELETE", full, api_key)
            if status == 204:
                print(f"  Obsidian: deleted {full.replace('/vault/', '')}")
                deleted += 1
            else:
                print(f"  Obsidian: failed to delete {full} (status {status})", file=sys.stderr)
    return deleted


def cleanup_empty_dir(vault_path, entry_type, slug):
    """Remove empty directory from filesystem after REST API file deletion."""
    if not vault_path:
        return
    dir_path = os.path.join(vault_path, "knowledge-base", f"{entry_type}s", slug)
    if os.path.isdir(dir_path):
        try:
            shutil.rmtree(dir_path)
            print(f"  Filesystem: removed empty dir {dir_path}")
        except OSError as e:
            print(f"  Filesystem: failed to remove dir: {e}", file=sys.stderr)


def delete_from_obsidian(slug, entry_type, api_key, vault_path=None):
    dir_path = f"/vault/knowledge-base/{entry_type}s/{slug}/"
    files = list_vault_dir(dir_path, api_key)

    if not files:
        print(f"  Obsidian: directory not found or empty, skipping")
        return False

    deleted = delete_vault_recursive(dir_path, api_key)

    if deleted > 0:
        # Clean up empty folders left on filesystem
        cleanup_empty_dir(vault_path, entry_type, slug)
        print(f"  Obsidian: {deleted} file(s) deleted")
        return True

    return False


def delete_from_index_md(slug, api_key):
    status, content = api_request(
        "GET",
        "/vault/knowledge-base/INDEX.md",
        api_key,
    )
    if status != 200:
        print(f"  INDEX.md: failed to read (status {status})", file=sys.stderr)
        return False

    # Remove the entry block: ### slug + all following "- key: value" lines
    pattern = rf"### {re.escape(slug)}\n(?:- .*\n)*\n?"
    new_content = re.sub(pattern, "", content)

    # Also remove wikilink style entries
    new_content = re.sub(
        rf"- \[\[.*?{re.escape(slug)}.*?\]\].*\n?", "", new_content
    )

    if new_content == content:
        print(f"  INDEX.md: slug '{slug}' not found, skipping")
        return False

    status, _ = api_request(
        "PUT",
        "/vault/knowledge-base/INDEX.md",
        api_key,
        body=new_content,
        content_type="text/markdown",
    )
    if status == 204:
        print(f"  INDEX.md: removed '{slug}'")
        return True
    else:
        print(f"  INDEX.md: failed to update (status {status})", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Delete a library entry by slug")
    parser.add_argument("slug", help="Entry slug to delete (e.g. bb-browser)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be deleted without doing it"
    )
    parser.add_argument(
        "--vault-path", help="Obsidian vault absolute path (for cleaning empty folders)"
    )
    parser.add_argument(
        "--type", help="Override entry type (project/skill/tool/article/concept/collection)"
    )
    args = parser.parse_args()

    slug = args.slug
    vault_path = args.vault_path
    api_key = get_api_key()

    # Determine entry type: CLI override > JSON index > default
    entry_type = args.type
    if not entry_type:
        index_path = os.path.normpath(INDEX_JSON)
        if os.path.exists(index_path):
            with open(index_path) as f:
                entries = json.load(f)
            for e in entries:
                if e.get("slug") == slug:
                    entry_type = e.get("type", "project")
                    break

    if not entry_type:
        print(f"WARN: '{slug}' not in JSON index, trying 'project' as default type")
        entry_type = "project"

    print(f"Deleting '{slug}' (type: {entry_type})...")

    if args.dry_run:
        print(f"  [DRY RUN] Would delete Obsidian: knowledge-base/{entry_type}s/{slug}/ (all files)")
        print(f"  [DRY RUN] Would remove from INDEX.md")
        print(f"  [DRY RUN] Would remove from library-index.json")
        if vault_path:
            print(f"  [DRY RUN] Would remove empty dir: {vault_path}/knowledge-base/{entry_type}s/{slug}/")
        return

    results = []
    results.append(("Obsidian", delete_from_obsidian(slug, entry_type, api_key, vault_path)))
    results.append(("INDEX.md", delete_from_index_md(slug, api_key)))
    results.append(("JSON index", delete_from_json_index(slug)))

    success = sum(1 for _, ok in results if ok)
    print(f"\nDone: {success}/3 locations cleaned.")

    if success == 0:
        print("Nothing was found to delete.")
        sys.exit(1)


if __name__ == "__main__":
    main()
