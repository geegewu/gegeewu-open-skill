# Meeting Summary Reference

详细配置和运维信息，按需加载。

---

## Obsidian 自动同步（由 generate_report.py 内部执行）

generate_report.py 执行完后会自动将以下文件写入 Obsidian vault，**按子文件夹组织**：
- `$OBSIDIAN_VAULT_PATH/Meetings/{YYYY-MM-DD}-{title}/{YYYY-MM-DD}-{title}.md`
- `$OBSIDIAN_VAULT_PATH/Meetings/{YYYY-MM-DD}-{title}/{YYYY-MM-DD}-{title}.html`

同步策略：
- 优先直接写入（本地 iCloud Drive 路径）
- 失败时检查 iCloud Drive 同步状态

环境变量（已写入 `~/.env`）：
```bash
OBSIDIAN_VAULT_PATH=~/Library/Mobile Documents/iCloud~md~obsidian/Documents/<vault-name>
```

---

## Apple Reminders 同步（由 generate_report.py 内部执行）

`generate_report.py` 执行完成后自动调用 `sync_todos_to_reminders(data)`，将待办事项写入 Apple Reminders。

**工具**：`icloud-reminder-add`（Swift CLI，源码在 `tools/icloud-reminder-add/`）
**列表**：`会议待办`（iCloud 账户，不存在时自动在 iCloud source 下创建）
**写入策略**：强制指定 `sourceType == .calDAV`（iCloud source），避免命中本地同名列表
**归属过滤**：写入全部待办（含多人负责的条目）
**截止时间**：deadline 有值用 deadline，否则从明天起每条 +1 天
**优先级前缀**：🔴高 / 🟡中 / 🟢低

**授权**（首次）：
```bash
# 首次运行需 Full Access
icloud-reminder-add --title "test" --list 会议待办
# 系统弹窗授权后即可
```

**注意事项**：
- Mac Mini headless 下需先手动授权（系统设置 → 隐私 → 提醒事项 → Full Access）
- EventKit 强制写 iCloud source，不再依赖系统默认列表顺序
- iCloud 全同步开启后，写入内容自动同步到手机和 Calendar.app

---

## 其他注意事项

- 文字稿较长（>8000字）时提前告知用户正在处理
- `due` 为 null 的 TODO 显示为「待定」
- HTML 文件为完全离线包，无需网络，浏览器直接打开
- 若 `npx markmap-cli` 不可用，思维导图降级为文本大纲展示
- **输出路径必须用 `archive/`**，不能用 `/tmp`
- **思维导图方向**：generate_report.py 自动统计 mindmap 二级节点数；`> 6` 个节点时自动注入垂直布局切换；`≤ 6` 个节点保持默认水平布局
- **markmap 无原生 direction 选项**：方向切换是 post-render DOM 操作，不是 markmap 配置参数
