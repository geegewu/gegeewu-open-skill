#!/usr/bin/env python3
"""
Apple 备忘录管理工具
通过 AppleScript 控制 macOS 备忘录应用
"""

import subprocess
import sys
from datetime import datetime

def run_applescript(script):
    """运行 AppleScript"""
    result = subprocess.run(
        ['osascript', '-e', script],
        capture_output=True,
        text=True
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode

def create_note(title, body, folder="备忘录"):
    """创建新备忘录"""
    script = f'''
    tell application "Notes"
        tell account "iCloud"
            make new note at folder "{folder}" with properties {{name:"{title}", body:"{body}"}}
        end tell
    end tell
    '''
    stdout, stderr, rc = run_applescript(script)
    if rc == 0:
        print(f"备忘录创建成功: {title}")
        return True
    else:
        print(f"创建失败: {stderr}")
        return False

def list_notes(folder="备忘录", limit=10):
    """列出备忘录"""
    script = f'''
    tell application "Notes"
        tell account "iCloud"
            set noteList to name of every note in folder "{folder}"
            return noteList
        end tell
    end tell
    '''
    stdout, stderr, rc = run_applescript(script)
    if rc == 0:
        notes = stdout.split(", ")
        print(f"{folder} 中的备忘录:")
        for i, note in enumerate(notes[:limit], 1):
            print(f"  {i}. {note}")
        return notes
    else:
        print(f"获取失败: {stderr}")
        return []

def search_notes(query):
    """搜索备忘录"""
    script = f'''
    tell application "Notes"
        set searchResults to {{}}
        repeat with eachNote in (get every note)
            if (name of eachNote contains "{query}") or (body of eachNote contains "{query}") then
                set end of searchResults to (name of eachNote)
            end if
        end repeat
        return searchResults
    end tell
    '''
    stdout, stderr, rc = run_applescript(script)
    if rc == 0:
        if stdout:
            notes = stdout.split(", ")
            print(f"搜索结果:")
            for i, note in enumerate(notes, 1):
                print(f"  {i}. {note}")
            return notes
        else:
            print("未找到匹配的备忘录")
            return []
    else:
        print(f"搜索失败: {stderr}")
        return []

def show_note(title):
    """显示备忘录内容"""
    script = f'''
    tell application "Notes"
        repeat with eachNote in (get every note)
            if name of eachNote is "{title}" then
                return body of eachNote
            end if
        end repeat
        return "未找到"
    end tell
    '''
    stdout, stderr, rc = run_applescript(script)
    if rc == 0:
        print(f"{title}:")
        print("=" * 50)
        print(stdout)
        return stdout
    else:
        print(f"获取失败: {stderr}")
        return None

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Apple 备忘录管理工具")
    parser.add_argument("action", choices=["create", "list", "search", "show"], help="操作")
    parser.add_argument("--title", "-t", help="标题")
    parser.add_argument("--body", "-b", help="内容")
    parser.add_argument("--folder", "-f", default="备忘录", help="文件夹")
    parser.add_argument("--query", "-q", help="搜索关键词")

    args = parser.parse_args()

    if args.action == "create":
        if not args.title:
            print("请提供标题: --title '标题'")
            sys.exit(1)
        body = args.body or f"创建于 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        create_note(args.title, body, args.folder)

    elif args.action == "list":
        list_notes(args.folder)

    elif args.action == "search":
        if not args.query:
            print("请提供搜索词: --query '关键词'")
            sys.exit(1)
        search_notes(args.query)

    elif args.action == "show":
        if not args.title:
            print("请提供标题: --title '标题'")
            sys.exit(1)
        show_note(args.title)
