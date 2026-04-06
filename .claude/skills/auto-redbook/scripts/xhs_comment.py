#!/usr/bin/env python3
"""
xhs_comment.py - 小红书评论 MCP 客户端

Usage:
  python xhs_comment.py list   --feed-id <id> --xsec-token <token> [--all] [--limit 20]
  python xhs_comment.py post   --feed-id <id> --xsec-token <token> --content "..."
  python xhs_comment.py reply  --feed-id <id> --xsec-token <token> --content "..." [--comment-id <id>] [--user-id <uid>]
  python xhs_comment.py search --keyword "..." [--limit 10]
"""
import argparse
import json
import sys
import urllib.request
import urllib.error

MCP_URL = "http://localhost:18060/mcp/"


class MCPClient:
    def __init__(self, timeout: int = 30):
        self.session_id = None
        self.timeout = timeout
        self._initialize()

    def _post(self, payload: dict) -> dict:
        data = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(MCP_URL, data=data, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.URLError as e:
            raise ConnectionError(f"MCP server not running at {MCP_URL}: {e}") from e
        sid = resp.headers.get("Mcp-Session-Id", "")
        if sid:
            self.session_id = sid
        return json.loads(resp.read())

    def _initialize(self):
        result = self._post({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "xhs_comment", "version": "1.0"},
            },
        })
        if "error" in result:
            raise RuntimeError(f"MCP initialize failed: {result['error']}")
        print(f"[MCP] connected, session={self.session_id}", file=sys.stderr)

    def call_tool(self, name: str, arguments: dict) -> dict:
        result = self._post({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        if "error" in result:
            raise RuntimeError(f"Tool '{name}' error: {result['error']}")
        contents = result.get("result", {}).get("content", [])
        for c in contents:
            if c.get("type") == "text":
                try:
                    return json.loads(c["text"])
                except json.JSONDecodeError:
                    return {"raw": c["text"]}
        return result.get("result", {})


def _out(data: dict):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_list(args):
    client = MCPClient(timeout=90)
    # 热身：让 go-rod 浏览器加载 cookies
    print("[MCP] warming up...", file=sys.stderr)
    client.call_tool("check_login_status", {})
    print("[MCP] calling get_feed_detail...", file=sys.stderr)
    kwargs = {"feed_id": args.feed_id, "xsec_token": args.xsec_token}
    if args.load_all:
        kwargs["load_all_comments"] = True
        kwargs["limit"] = args.limit
    raw = client.call_tool("get_feed_detail", kwargs)

    # 实测结构: data.comments.list
    comments_raw = (
        raw.get("data", {}).get("comments", {}).get("list")
        or raw.get("comments", {}).get("list")
        or raw.get("comments")
        or []
    )

    comments = []
    for c in comments_raw:
        ui = c.get("userInfo") or c.get("user") or {}
        comments.append({
            "id": c.get("id") or c.get("comment_id", ""),
            "user_id": ui.get("userId") or ui.get("user_id", ""),
            "nickname": ui.get("nickname") or ui.get("nickName", ""),
            "content": c.get("content") or c.get("text", ""),
            "time": c.get("createTime") or c.get("create_time") or c.get("time", ""),
            "like_count": c.get("likeCount") or c.get("like_count", 0),
            "reply_count": c.get("subCommentCount") or c.get("sub_comment_count", 0),
        })

    _out({"comments": comments, "total": len(comments)})


def cmd_post(args):
    client = MCPClient()
    print("[MCP] posting comment...", file=sys.stderr)
    raw = client.call_tool("post_comment_to_feed", {
        "feed_id": args.feed_id,
        "xsec_token": args.xsec_token,
        "content": args.content,
    })
    _out({"success": True, "result": raw})


def cmd_reply(args):
    client = MCPClient()
    print("[MCP] replying to comment...", file=sys.stderr)
    params = {
        "feed_id": args.feed_id,
        "xsec_token": args.xsec_token,
        "content": args.content,
    }
    if args.comment_id:
        params["comment_id"] = args.comment_id
    if args.user_id:
        params["user_id"] = args.user_id
    raw = client.call_tool("reply_comment_in_feed", params)
    _out({"success": True, "result": raw})


def cmd_search(args):
    client = MCPClient()
    print("[MCP] searching feeds...", file=sys.stderr)
    raw = client.call_tool("search_feeds", {
        "keyword": args.keyword,
    })

    feeds_raw = (
        raw.get("note_list")
        or raw.get("feeds")
        or raw.get("data", {}).get("feeds")
        or raw.get("items")
        or []
    )

    feeds = []
    for f in feeds_raw:
        feeds.append({
            "feed_id": f.get("id") or f.get("noteId") or f.get("note_id", ""),
            "xsec_token": f.get("xsecToken") or f.get("xsec_token", ""),
            "title": f.get("title") or f.get("desc", ""),
            "author": (f.get("user") or {}).get("nickname") or f.get("author", ""),
        })

    _out({"feeds": feeds, "total": len(feeds), "_raw_keys": list(raw.keys())})


def main():
    parser = argparse.ArgumentParser(description="小红书评论 MCP 客户端")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # list
    p_list = sub.add_parser("list", help="获取笔记评论列表")
    p_list.add_argument("--feed-id", required=True)
    p_list.add_argument("--xsec-token", required=True)
    p_list.add_argument("--all", dest="load_all", action="store_true", default=False)
    p_list.add_argument("--limit", type=int, default=20)

    # post
    p_post = sub.add_parser("post", help="发表评论")
    p_post.add_argument("--feed-id", required=True)
    p_post.add_argument("--xsec-token", required=True)
    p_post.add_argument("--content", required=True)

    # reply
    p_reply = sub.add_parser("reply", help="回复评论")
    p_reply.add_argument("--feed-id", required=True)
    p_reply.add_argument("--xsec-token", required=True)
    p_reply.add_argument("--content", required=True)
    p_reply.add_argument("--comment-id", default=None)
    p_reply.add_argument("--user-id", default=None)

    # search
    p_search = sub.add_parser("search", help="搜索笔记（获取 feed_id + xsec_token）")
    p_search.add_argument("--keyword", required=True)
    p_search.add_argument("--limit", type=int, default=10)

    args = parser.parse_args()

    try:
        dispatch = {
            "list": cmd_list,
            "post": cmd_post,
            "reply": cmd_reply,
            "search": cmd_search,
        }
        dispatch[args.cmd](args)
    except ConnectionError as e:
        _out({"success": False, "error": str(e)})
        sys.exit(1)
    except RuntimeError as e:
        _out({"success": False, "error": str(e)})
        sys.exit(1)
    except Exception as e:
        _out({"success": False, "error": f"Unexpected error: {e}"})
        sys.exit(1)


if __name__ == "__main__":
    main()
