# xhs_comment.py（评论工具 CLI）

路径：`skills/auto-redbook/scripts/xhs_comment.py`
功能：封装 MCP comment 工具，纯 stdlib，输出 JSON 到 stdout。

## 用法

```bash
# 搜索帖子
python3 xhs_comment.py search --keyword "AI工作流"

# 列出帖子评论（含热身）
python3 xhs_comment.py list --feed-id <id> --xsec-token <token>

# 发评论
python3 xhs_comment.py post --feed-id <id> --xsec-token <token> --content "内容"

# 回复评论（需 PR #479 合并后生效）
python3 xhs_comment.py reply --feed-id <id> --xsec-token <token> --content "回复" --comment-id <id>
```

## 注意事项

- 每次调用前自动热身（`check_login_status`），无需手动调用
- `reply` 命令依赖 go-rod CSS selector 修复（PR #479，待合并）
- MCP server 必须运行在 port 18060
