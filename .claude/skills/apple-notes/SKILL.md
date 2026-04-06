---
name: apple-notes
description: 通过 AppleScript 管理 macOS 备忘录应用，支持创建、列出、搜索和查看备忘录。用户说"创建备忘录"、"查看备忘录"、"搜索备忘录"时触发。
user-invocable: true
allowed-tools: Bash Read
---

# Apple 备忘录管理工具

通过 AppleScript 控制 macOS 自带的备忘录应用。

## 功能

- **创建备忘录**: `python3 ${CLAUDE_SKILL_DIR}/scripts/notes.py create --title "标题" --body "内容"`
- **列出备忘录**: `python3 ${CLAUDE_SKILL_DIR}/scripts/notes.py list [--folder "文件夹"]`
- **搜索备忘录**: `python3 ${CLAUDE_SKILL_DIR}/scripts/notes.py search --query "关键词"`
- **查看内容**: `python3 ${CLAUDE_SKILL_DIR}/scripts/notes.py show --title "标题"`

## 使用示例

```bash
# 创建备忘录
python3 ${CLAUDE_SKILL_DIR}/scripts/notes.py create --title "会议记录" --body "今天讨论了项目进度..."

# 创建到指定文件夹
python3 ${CLAUDE_SKILL_DIR}/scripts/notes.py create --title "购物清单" --body "- 牛奶\n- 鸡蛋" --folder "个人"

# 列出备忘录
python3 ${CLAUDE_SKILL_DIR}/scripts/notes.py list

# 搜索
python3 ${CLAUDE_SKILL_DIR}/scripts/notes.py search --query "项目"

# 查看内容
python3 ${CLAUDE_SKILL_DIR}/scripts/notes.py show --title "会议记录"
```

## 注意事项

- 需要 macOS 系统
- 备忘录数据存储在 iCloud（默认）
- 首次使用可能需要授权访问备忘录
