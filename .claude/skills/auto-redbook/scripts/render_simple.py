#!/usr/bin/env python3
"""
简化版小红书图片生成 - 针对 API 限流优化
"""
import subprocess
import sys
import os
from pathlib import Path
import time

nano_script = str(Path(__file__).resolve().parent.parent.parent / "nano-banana-pro" / "scripts" / "generate_image.py")

def test_api():
    """测试 Gemini API 是否可用"""
    print("🔍 检测 Gemini API 状态...")
    test_prompt = "A simple red square"
    test_file = "/tmp/gemini_test.png"
    
    try:
        cmd = ["uv", "run", nano_script, 
               "--prompt", test_prompt,
               "--filename", test_file,
               "--resolution", "1K"]
        
        start = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        elapsed = time.time() - start
        
        if result.returncode == 0:
            print(f"✓ API 正常 (耗时 {elapsed:.1f}s)")
            if Path(test_file).exists():
                os.remove(test_file)
            return True
        else:
            print(f"✗ API 错误:")
            print(result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        print("✗ API 超时 (可能是限流或网络问题)")
        return False
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False


def generate_simple_card(title, content, filename, resolution="2K"):
    """生成简化版卡片 - 极简 prompt"""
    prompt = f"""Xiaohongshu post card (3:4 vertical):
Title: {title}
Content: {content}
Style: Clean white card, light gray background, simple typography
NO decorations"""
    
    print(f"生成: {filename}")
    try:
        cmd = ["uv", "run", nano_script,
               "--prompt", prompt,
               "--filename", filename,
               "--resolution", resolution]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0:
            print(f"✓ 成功: {filename}")
            return True
        else:
            print(f"✗ 失败: {filename}")
            print(f"错误: {result.stderr[:200]}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"✗ 超时: {filename}")
        return False
    except Exception as e:
        print(f"✗ 异常: {e}")
        return False


def main():
    # 1. 检测 API
    if not test_api():
        print("\n⚠️  Gemini API 不可用")
        print("可能原因:")
        print("  1. API 限流 (每日配额用完)")
        print("  2. GEMINI_API_KEY 未设置或无效")
        print("  3. 网络连接问题")
        print("\n建议:")
        print("  - 检查环境变量: echo $GEMINI_API_KEY")
        print("  - 等待配额重置 (通常在 UTC 00:00)")
        print("  - 或使用备用 API key")
        sys.exit(1)
    
    print("\n=== 开始生成小红书图片 ===\n")
    
    # 2. 生成架构图 (简化 prompt)
    arch_prompt = """Technical system diagram, vertical 3:4 layout:
Sales Data Analysis System
Components: Database -> Processing -> Cache -> Charts -> UI
Tech: Python Dash, MySQL, Plotly
Simple boxes and arrows, clean design"""
    
    print("生成架构图...")
    cmd = ["uv", "run", nano_script,
           "--prompt", arch_prompt,
           "--filename", "sales_arch.png",
           "--resolution", "2K"]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode == 0:
        print("✓ 架构图完成")
    else:
        print(f"✗ 架构图失败: {result.stderr[:200]}")
    
    print("\n=== 完成 ===")


if __name__ == "__main__":
    main()
