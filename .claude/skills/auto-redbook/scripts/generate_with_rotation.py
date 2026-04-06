#!/usr/bin/env python3
"""
Gemini API Key 轮替生成小红书图片
"""
import subprocess
import sys
import os
from pathlib import Path
import time

nano_script = str(Path(__file__).resolve().parent.parent.parent / "nano-banana-pro" / "scripts" / "generate_image.py")

def _load_api_keys():
    """Load Gemini API keys from environment variables."""
    dotenv = Path.home() / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    keys_str = os.environ.get("GEMINI_API_KEYS", "")
    if keys_str:
        return [k.strip() for k in keys_str.split(",") if k.strip()]
    single = os.environ.get("GEMINI_API_KEY", "")
    if single:
        return [single]
    print("❌ 未找到 GEMINI_API_KEYS 或 GEMINI_API_KEY 环境变量")
    sys.exit(1)

API_KEYS = _load_api_keys()


def test_api_key(api_key, key_index):
    """测试单个API key是否可用"""
    print(f"  测试 KEY_{key_index + 1}...", end=" ")
    
    test_prompt = "A simple blue circle"
    test_file = f"/tmp/test_key_{key_index}.png"
    
    try:
        cmd = [
            "uv", "run", nano_script,
            "--prompt", test_prompt,
            "--filename", test_file,
            "--resolution", "1K",
            "--api-key", api_key
        ]
        
        start = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        elapsed = time.time() - start
        
        if result.returncode == 0 and Path(test_file).exists():
            print(f"✓ 可用 ({elapsed:.1f}s)")
            os.remove(test_file)
            return True
        else:
            error_msg = result.stderr[:100] if result.stderr else "未知错误"
            print(f"✗ 失败: {error_msg}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"✗ 超时")
        return False
    except Exception as e:
        print(f"✗ 异常: {str(e)[:50]}")
        return False


def find_available_key():
    """找到第一个可用的API key"""
    print("🔍 检测可用的 Gemini API keys:\n")
    
    for i, key in enumerate(API_KEYS):
        if test_api_key(key, i):
            return key, i
    
    return None, None


def generate_image(prompt, filename, api_key, resolution="2K"):
    """使用指定API key生成图片"""
    try:
        cmd = [
            "uv", "run", nano_script,
            "--prompt", prompt,
            "--filename", filename,
            "--resolution", resolution,
            "--api-key", api_key
        ]
        
        print(f"生成: {filename}...", end=" ")
        start = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        elapsed = time.time() - start
        
        if result.returncode == 0:
            print(f"✓ 成功 ({elapsed:.1f}s)")
            return True
        else:
            print(f"✗ 失败")
            print(f"  错误: {result.stderr[:150]}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"✗ 超时")
        return False
    except Exception as e:
        print(f"✗ 异常: {e}")
        return False


def main():
    print("=== 小红书图片生成（API轮替） ===\n")
    
    # 1. 找到可用的API key
    api_key, key_index = find_available_key()
    
    if not api_key:
        print("\n❌ 所有API keys都不可用")
        print("可能原因:")
        print("  1. 所有keys都达到配额限制")
        print("  2. 网络连接问题")
        print("  3. Gemini服务异常")
        sys.exit(1)
    
    print(f"\n✅ 使用 KEY_{key_index + 1} 生成图片\n")
    
    # 2. 生成销售系统架构图（极简prompt）
    arch_prompt = """System diagram (3:4 vertical):
Sales Data Analysis
Flow: DB→Process→Cache→Charts→UI
Tech: Python Dash, MySQL, Plotly
Simple layout, clean design"""
    
    print("=== 生成系统架构图 ===\n")
    success = generate_image(arch_prompt, "sales_arch.png", api_key, "2K")
    
    if success:
        print(f"\n✓ 图片已保存: {Path.cwd() / 'sales_arch.png'}")
    
    print("\n=== 完成 ===")


if __name__ == "__main__":
    main()
