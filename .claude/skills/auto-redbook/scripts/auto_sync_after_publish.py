#!/usr/bin/env python3
"""
小红书发布后自动同步脚本
- 归档到 archive/YYYY-MM-DD/
- 同步到飞书（文档 + 图片附件）
- 同步到Notion（Database记录 + 图片信息）

架构说明：
==========================================
本脚本通过直接 API 调用完成同步：
1. 飞书 Bitable：认证 + 图片上传 + 创建记录（REST API）
2. Notion：创建 Database 页面（curl 调用 Notion API）
3. 归档：move 源文件到 archive/YYYY-MM-DD/ 目录
"""

import os
import sys
import json
import shutil
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess

# Sync runtime controls
def _env_int(name: str, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if min_value is not None and value < min_value:
        value = min_value
    if max_value is not None and value > max_value:
        value = max_value
    return value


FEISHU_SYNC_TIMEOUT = _env_int("XHS_FEISHU_SYNC_TIMEOUT", 180, min_value=10, max_value=600)
NOTION_SYNC_TIMEOUT = _env_int("XHS_NOTION_SYNC_TIMEOUT", 180, min_value=10, max_value=600)
NOTION_TEXT_MAX_UNITS = _env_int("XHS_NOTION_TEXT_MAX_UNITS", 1900, min_value=200, max_value=2000)


# 加载 .env 文件（强制覆盖系统环境变量）
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent / '.env'
    if env_file.exists():
        load_dotenv(env_file, override=True)
except ImportError:
    pass


def retry(max_attempts=2, delay=2):
    """重试装饰器：失败后重试，最多 max_attempts 次"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    if result is not None:  # 成功
                        return result
                    if attempt < max_attempts:
                        print(f"  ⚠️  第 {attempt} 次失败，{delay}秒后重试...")
                        time.sleep(delay)
                except Exception as e:
                    if attempt < max_attempts:
                        print(f"  ⚠️  第 {attempt} 次异常: {e}，{delay}秒后重试...")
                        time.sleep(delay)
                    else:
                        print(f"  ✗ 达到最大重试次数，放弃")
                        raise
            return None
        return wrapper
    return decorator


def clear_pending_sync_marker():
    """Clear pending_sync.json only after full sync success."""
    pending_file = Path(__file__).parent.parent / "pending_sync.json"
    if pending_file.exists():
        pending_file.unlink(missing_ok=True)
        print(f"✓ 已清理恢复标记: {pending_file}")


def _notion_units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _truncate_for_notion(text: str, max_units: int) -> str:
    if _notion_units(text) <= max_units:
        return text
    units = 0
    buf = []
    for ch in text:
        ch_units = len(ch.encode("utf-16-le")) // 2
        if units + ch_units > max_units:
            break
        buf.append(ch)
        units += ch_units
    return "".join(buf)


def archive_files(xhs_note_id, source_dir, archive_root="archive", target_md_file=None, task_id=None):
    """归档小红书笔记文件（move 模式，归档后删除源文件）
    
    归档结构: archive/YYYY-MM-DD/{task_id}_{doc_name}/
    
    Args:
        xhs_note_id: 小红书笔记ID
        source_dir: 源目录
        archive_root: 归档根目录
        target_md_file: 指定的markdown文件路径（可选）
        task_id: 任务ID，用于匹配图片文件（可选）
    """
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Build subdirectory name: {task_id}_{doc_name}
    doc_name = "unknown"
    if target_md_file and Path(target_md_file).exists():
        doc_name = Path(target_md_file).stem.replace('_xhs', '')
    
    if task_id:
        sub_dir = f"{task_id}_{doc_name}"
    else:
        sub_dir = doc_name
    
    # 如果 source_dir 已经在 archive 目录内，改用 SKILL_DIR 避免二次嵌套
    skill_dir = Path(__file__).parent.parent
    source_path_obj = Path(source_dir).resolve()
    archive_base = (skill_dir / archive_root).resolve()
    if str(source_path_obj).startswith(str(archive_base)):
        archive_dir = archive_base / today / sub_dir
    else:
        archive_dir = source_path_obj / archive_root / today / sub_dir
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n📦 归档文件到 {archive_dir}...")
    
    source_path = Path(source_dir)
    archived_files = []
    
    # 归档指定的markdown文件（move）
    if target_md_file and Path(target_md_file).exists():
        md_file = Path(target_md_file)
        dest = archive_dir / md_file.name
        shutil.move(str(md_file), str(dest))
        archived_files.append(str(dest))
        print(f"  ✓ {md_file.name} (moved)")
    else:
        # 向后兼容：归档所有匹配的markdown文件
        for md_file in source_path.glob("*.md"):
            if "lara" in md_file.name.lower() or "xhs" in md_file.name.lower():
                dest = archive_dir / md_file.name
                shutil.move(str(md_file), str(dest))
                archived_files.append(str(dest))
                print(f"  ✓ {md_file.name} (moved)")
    
    # 归档图片文件（move，使用 task_id 匹配）
    if task_id:
        for ext in ["jpg", "jpeg", "png"]:
            for img_file in sorted(source_path.glob(f"{task_id}_*.{ext}")):
                dest = archive_dir / img_file.name
                shutil.move(str(img_file), str(dest))
                archived_files.append(str(dest))
                print(f"  ✓ {img_file.name} (moved)")
    else:
        # 向后兼容：归档所有 xhs_*.png/jpg 文件
        for ext in ["jpg", "jpeg", "png"]:
            for img_file in sorted(source_path.glob(f"xhs_*.{ext}")):
                dest = archive_dir / img_file.name
                shutil.move(str(img_file), str(dest))
                archived_files.append(str(dest))
                print(f"  ✓ {img_file.name} (moved)")
    
    # 归档描述文件（move）
    for txt_file in source_path.glob("xhs_*.txt"):
        dest = archive_dir / txt_file.name
        shutil.move(str(txt_file), str(dest))
        archived_files.append(str(dest))
        print(f"  ✓ {txt_file.name} (moved)")
    
    return archive_dir, archived_files


@retry(max_attempts=2, delay=2)
def sync_to_feishu(title, content, xhs_url=None, note_id=None, image_paths=None, tags=None):
    """同步到飞书 Bitable（多维表格）
    
    支持单图或多图上传（image_paths 为列表）
    
    通过飞书开放平台 REST API 完成：
    1. 获取 tenant_access_token（认证）
    2. 上传图片到飞书云文档，获取 file_token
    3. 创建 Bitable 记录（含图片附件）
    """
    print(f"\n📄 同步到飞书 Bitable...")
    
    try:
        import requests
        
        # 从环境变量获取飞书凭证
        app_id = os.getenv("FEISHU_APP_ID")
        app_secret = os.getenv("FEISHU_APP_SECRET")
        bitable_app_token = os.getenv("FEISHU_BITABLE_APP_TOKEN")
        bitable_table_id = os.getenv("FEISHU_BITABLE_TABLE_ID")
        
        if not app_id or not app_secret:
            print(f"  ⚠️  飞书配置未设置，跳过飞书同步")
            return None
        
        if not bitable_app_token or not bitable_table_id:
            print(f"  ⚠️  飞书 Bitable 配置未设置，跳过飞书同步")
            return None
        
        # Get tenant_access_token
        auth_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        auth_response = requests.post(auth_url, json={
            "app_id": app_id,
            "app_secret": app_secret
        })
        auth_data = auth_response.json()
        
        if auth_data.get("code") != 0:
            print(f"  ✗ 飞书认证失败: {auth_data.get('msg')}")
            return None
        
        access_token = auth_data["tenant_access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # === 图片上传（支持多图）===
        file_tokens = []
        
        # 统一处理为列表
        if image_paths is None:
            image_list = []
        elif isinstance(image_paths, (str, Path)):
            image_list = [image_paths]
        else:
            image_list = list(image_paths)
        
        for idx, img_path in enumerate(image_list, 1):
            if not img_path or not Path(img_path).exists():
                continue
                
            try:
                print(f"  📸 上传图片 {idx}/{len(image_list)}...")
                
                image_filename = Path(img_path).name
                file_size = os.path.getsize(img_path)
                mime_type = 'image/png' if str(img_path).endswith('.png') else 'image/jpeg'
                
                upload_url = "https://open.feishu.cn/open-apis/drive/v1/medias/upload_all"
                
                with open(img_path, 'rb') as f:
                    files = {
                        'file_name': (None, image_filename),
                        'parent_type': (None, 'bitable'),
                        'parent_node': (None, bitable_app_token),
                        'size': (None, str(file_size)),
                        'file': (image_filename, f, mime_type)
                    }
                    upload_response = requests.post(upload_url, headers=headers, files=files)
                
                upload_data = upload_response.json()
                
                if upload_data.get("code") == 0:
                    token = upload_data['data']['file_token']
                    file_tokens.append({
                        "file_token": token,
                        "name": image_filename
                    })
                    print(f"  ✓ 图片 {idx} 上传成功")
                else:
                    print(f"  ⚠️ 图片 {idx} 上传失败: {upload_data.get('msg')}")
            
            except Exception as e:
                print(f"  ✗ 图片 {idx} 上传异常: {e}")
        
        # === 创建Bitable记录 ===
        
        # 提取note_id
        if not note_id and xhs_url:
            note_id = xhs_url.split('/')[-1].split('?')[0]
        
        # 构建字段数据
        fields_data = {
            "标题": title,
            "笔记ID": note_id,
            "链接": {"link": xhs_url, "text": "查看笔记"} if xhs_url else None,
            "状态": "私密",
            "发布时间": int(datetime.now().timestamp() * 1000),
            "图片数量": len(file_tokens),
            "内容": content[:2000],  # Bitable字段长度限制
            "标签": ", ".join(tags) if tags else ""
        }
        
        if file_tokens:
            fields_data["图片"] = file_tokens
        
        # 创建记录
        create_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{bitable_app_token}/tables/{bitable_table_id}/records"
        create_response = requests.post(
            create_url,
            headers={**headers, "Content-Type": "application/json"},
            json={"fields": fields_data}
        )
        create_data = create_response.json()
        
        if create_data.get("code") != 0:
            print(f"  ✗ Bitable记录创建失败: {create_data.get('msg')}")
            return None
        
        record_id = create_data["data"]["record"]["record_id"]
        
        print(f"  ✓ 飞书 Bitable 记录创建成功")
        print(f"  📎 记录ID: {record_id}")
        
        return {
            "record_id": record_id,
            "app_token": bitable_app_token,
            "table_id": bitable_table_id
        }
        
    except ImportError:
        print(f"  ⚠️  requests 库未安装，跳过飞书同步")
        return None
    except Exception as e:
        print(f"  ✗ 飞书同步失败: {e}")
        return None


@retry(max_attempts=2, delay=2)
def sync_to_notion(title, content, xhs_url, image_paths=None, tags=None):
    """同步到Notion（支持多图）
    
    使用 curl 调用 Notion API，通过环境变量中的 credentials 认证。
    避免引入 notion-client Python SDK 依赖。
    """
    print(f"\n📘 同步到Notion...")
    
    notion_api_key = os.getenv("NOTION_API_KEY")
    notion_database_id = os.getenv("NOTION_DATABASE_ID")
    
    if not notion_api_key:
        print(f"  ⚠️  NOTION_API_KEY 未配置，跳过Notion同步")
        return None
    
    if not notion_database_id:
        print(f"  ⚠️  NOTION_DATABASE_ID 未配置，跳过Notion同步")
        return None
    
    try:
        content_for_notion = _truncate_for_notion(content, NOTION_TEXT_MAX_UNITS)
        if content_for_notion != content:
            print(
                f"  ℹ️ Notion内容已截断（units: {_notion_units(content)} -> {_notion_units(content_for_notion)}）"
            )

        # 构建Notion API payload
        notion_payload = {
            "parent": {"database_id": notion_database_id},
            "properties": {
                "Name": {
                    "title": [{"text": {"content": title}}]
                },
                "笔记ID": {
                    "rich_text": [{"text": {"content": xhs_url.split('/')[-1]}}]
                },
                "链接": {
                    "url": xhs_url
                },
                "状态": {
                    "select": {"name": "私密"}
                },
                "发布时间": {
                    "date": {
                        "start": datetime.now(timezone(timedelta(hours=8))).isoformat()
                    }
                },
                "图片数量": {
                    "number": len(image_paths) if image_paths else 0
                },
                "内容摘要": {
                    "rich_text": [{"text": {"content": content_for_notion}}]
                },
                "标签": {
                    "multi_select": [{"name": t.strip()} for t in (tags or []) if t.strip()]
                }
            },
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": content_for_notion}}]
                    }
                }
            ]
        }
        
        # 如果有图片，添加所有图片的说明
        if image_paths:
            for idx, img_path in enumerate(image_paths, 1):
                if img_path and Path(img_path).exists():
                    img_type = "封面图" if "cover" in str(img_path) else f"分图{idx-1}"
                    notion_payload["children"].append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{
                                "type": "text",
                                "text": {"content": f"📸 {img_type}：{Path(img_path).name}"}
                            }]
                        }
                    })
        
        # ✅ Use curl instead of Python SDK (follows SKILL_DEVELOPMENT.md)
        payload_json = json.dumps(notion_payload)
        
        result = subprocess.run([
            'curl', '-X', 'POST',
            'https://api.notion.com/v1/pages',
            '-H', 'Authorization: Bearer ' + notion_api_key,
            '-H', 'Content-Type: application/json',
            '-H', 'Notion-Version: 2022-06-28',
            '-d', payload_json
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"  ✗ curl调用失败: {result.stderr}")
            return None
        
        response_data = json.loads(result.stdout)
        
        if 'id' not in response_data:
            print(f"  ✗ Notion API错误: {response_data.get('message', '未知错误')}")
            return None
        
        print(f"  ✓ Notion页面创建成功")
        print(f"  📎 页面ID: {response_data['id']}")
        
        return response_data
        
    except Exception as e:
        print(f"  ✗ Notion同步失败: {e}")
        return None


def send_telegram_notification(title, xhs_url, feishu_result, notion_result, note_id):
    """同步完成后发送 Telegram 通知"""
    import re
    token = os.getenv("TELEGRAM_BOT_TOKEN_GEGEEWU_POST") or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token:
        # 尝试从 ~/.env 读取
        env_path = Path.home() / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                m = re.match(r'^TELEGRAM_BOT_TOKEN_GEGEEWU_POST=(.+)$', line.strip())
                if m:
                    token = m.group(1).strip().strip('"').strip("'")
                    break
            if not token:
                for line in env_path.read_text().splitlines():
                    m = re.match(r'^TELEGRAM_BOT_TOKEN=(.+)$', line.strip())
                    if m:
                        token = m.group(1).strip().strip('"').strip("'")
                        break
    if not token:
        print("  ⚠️  TELEGRAM_BOT_TOKEN 未配置，跳过通知")
        return

    feishu_line = f"飞书 ✅ {feishu_result['record_id']}" if feishu_result else "飞书 ❌ 同步失败"
    notion_line = f"Notion ✅ {notion_result['id']}" if notion_result else "Notion ❌ 同步失败"

    msg = (
        f"📦 回写完成：{title}\n"
        f"🔗 {xhs_url}\n"
        f"{feishu_line}\n"
        f"{notion_line}"
    )

    result = subprocess.run([
        "curl", "-s", "-X", "POST",
        f"https://api.telegram.org/bot{token}/sendMessage",
        "-d", f"chat_id={chat_id}",
        "-d", f"text={msg}",
    ], capture_output=True, text=True)
    if result.returncode == 0:
        print("✓ Telegram 通知已发送")
    else:
        print(f"⚠️ Telegram 通知发送失败: {result.stderr}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='小红书发布后自动同步脚本')
    parser.add_argument('--note-id', required=True, help='小红书笔记ID')
    parser.add_argument('--note-url', required=True, help='小红书笔记链接')
    parser.add_argument('--content-file', required=True, help='内容文件路径（markdown）')
    parser.add_argument('--image-dir', default='.', help='图片目录路径')
    parser.add_argument('--title', help='笔记标题（可选，默认从内容提取）')
    parser.add_argument('--task-id', required=True, help='任务ID（用于匹配图片文件）')
    parser.add_argument('--tags', nargs='*', default=[], help='话题标签列表')
    
    args = parser.parse_args()
    
    xhs_note_id = args.note_id
    xhs_url = args.note_url
    target_md_file = args.content_file
    source_dir = args.image_dir
    
    # 读取内容以提取标题
    with open(target_md_file, 'r', encoding='utf-8') as f:
        content_text = f.read()
    
    # 提取标题
    if args.title:
        title = args.title
    else:
        # 从内容提取第一个标题
        import re
        title_match = re.search(r'^#\s+(.+)$', content_text, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
        else:
            title = "小红书笔记"
    
    print("=" * 60)
    print("🚀 小红书发布后自动同步")
    print("=" * 60)
    print(f"📌 笔记ID: {xhs_note_id}")
    print(f"📝 标题: {title}")
    print(f"🔗 链接: {xhs_url}")
    print(f"📄 内容文件: {target_md_file}")
    print(f"📁 图片目录: {source_dir}")
    if args.tags:
        print(f"🏷️ 标签: {', '.join(args.tags)}")
    print("=" * 60)
    
    # 使用指定的markdown文件
    content_file = target_md_file
    
    # 读取内容
    with open(content_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 从image_dir收集图片文件（使用task-id精确匹配，支持 jpg/jpeg/png）
    image_files = []
    source_path = Path(source_dir)
    task_id = args.task_id
    for ext in ["jpg", "jpeg", "png"]:
        for img_file in source_path.glob(f"{task_id}_*.{ext}"):
            image_files.append(str(img_file))
    image_files.sort()  # 确保 cover 在前
    
    if not content_file or not Path(content_file).exists():
        print("\n❌ 内容文件不存在")
        sys.exit(1)
    
    # 清理markdown标记
    import re
    content = re.sub(r'```[\s\S]*?```', '', content)
    content = re.sub(r'^#+\s+', '', content, flags=re.MULTILINE)
    content = re.sub(r'\*\*([^\*]+)\*\*', r'\1', content)
    content = re.sub(r'^---+$', '', content, flags=re.MULTILINE)
    content = re.sub(r'\n{3,}', '\n\n', content)
    content = content.strip()
    
    # 确保图片路径正确
    validated_images = []
    for img in image_files:
        img_path = str(Path(source_dir) / img) if not Path(img).is_absolute() else img
        if Path(img_path).exists():
            validated_images.append(img_path)
        else:
            print(f"\n⚠️ 图片文件不存在: {img_path}")
    
    if not validated_images:
        print(f"\n⚠️ 未找到有效图片文件")
    
    # 步骤1: 并行同步到飞书和Notion（先同步，再归档）
    print("\n📤 并行同步到飞书和Notion...")
    with ThreadPoolExecutor(max_workers=2) as executor:
        feishu_future = executor.submit(
            sync_to_feishu, title, content, xhs_url, xhs_note_id, validated_images, args.tags
        )
        notion_future = executor.submit(
            sync_to_notion, title, content, xhs_url, validated_images, args.tags
        )

        # 等待飞书结果（可配置超时）
        try:
            feishu_result = feishu_future.result(timeout=FEISHU_SYNC_TIMEOUT)
            if feishu_result:
                print(f"✓ 飞书同步成功: record_id={feishu_result['record_id']}")
            else:
                print("⚠️ 飞书同步失败")
        except Exception as e:
            print(f"⚠️ 飞书同步异常: {e}")
            feishu_result = None

        # 等待Notion结果（可配置超时）
        try:
            notion_result = notion_future.result(timeout=NOTION_SYNC_TIMEOUT)
            if notion_result:
                print(f"✓ Notion同步成功: page_id={notion_result['id']}")
            else:
                print("⚠️ Notion同步失败")
        except Exception as e:
            print(f"⚠️ Notion同步异常: {e}")
            notion_result = None
    
    # 步骤2: 归档文件（同步完成后 move，不再 copy）
    try:
        archive_dir, archived_files = archive_files(xhs_note_id, source_dir, target_md_file=target_md_file, task_id=args.task_id)
        print(f"✓ 归档完成: {len(archived_files)} 个文件 → {archive_dir}")
    except Exception as e:
        print(f"⚠️ 归档失败: {e}")
        archive_dir = Path(source_dir) / "archive" / datetime.now().strftime("%Y-%m-%d")
        archived_files = []
    
    # 步骤3: 生成同步记录（写入归档目录）
    sync_ok = bool(feishu_result) and bool(notion_result)
    sync_record = {
        "note_id": xhs_note_id,
        "xhs_url": xhs_url,
        "archive_dir": str(archive_dir),
        "feishu_record_id": feishu_result.get('record_id') if feishu_result else None,
        "notion_page_id": notion_result.get('id') if notion_result else None,
        "sync_time": datetime.now().isoformat(),
        "status": "success" if sync_ok else "partial_failed"
    }
    
    sync_record_file = archive_dir / "sync_record.json"
    with open(sync_record_file, 'w', encoding='utf-8') as f:
        json.dump(sync_record, f, ensure_ascii=False, indent=2)
    
    if sync_ok:
        clear_pending_sync_marker()
        print(f"\n✅ 所有同步完成！")
    else:
        print(f"\n⚠️ 同步未完全成功（feishu={bool(feishu_result)}, notion={bool(notion_result)}），保留 pending_sync.json 以便重试")
    print(f"📝 同步记录: {sync_record_file}")
    # 发送 Telegram 同步完成通知
    send_telegram_notification(title, xhs_url, feishu_result, notion_result, xhs_note_id)
    if not sync_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
