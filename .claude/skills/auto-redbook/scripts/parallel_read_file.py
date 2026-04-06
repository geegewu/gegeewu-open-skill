#!/usr/bin/env python3
"""
并行读取大文件（优化性能，避免超时）
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sys


def read_chunk(file_path, start_line, end_line, chunk_id):
    """读取文件的指定行范围"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = []
            for i, line in enumerate(f, 1):
                if i >= start_line and i <= end_line:
                    lines.append(line)
                if i > end_line:
                    break
        return chunk_id, lines, None
    except Exception as e:
        return chunk_id, None, str(e)


def parallel_read_file(file_path, chunk_size=500, max_workers=4):
    """并行读取大文件"""
    file_path = Path(file_path)

    # 1. 获取总行数
    print(f"正在统计文件行数...", file=sys.stderr)
    with open(file_path, 'r', encoding='utf-8') as f:
        total_lines = sum(1 for _ in f)

    # 2. 计算批次
    num_chunks = (total_lines + chunk_size - 1) // chunk_size
    print(f"文件总行数: {total_lines}, 分 {num_chunks} 批次并行读取（每批 {chunk_size} 行）", file=sys.stderr)

    # 3. 并行读取
    chunks = {}
    failed_chunks = []

    with ThreadPoolExecutor(max_workers=min(num_chunks, max_workers)) as executor:
        futures = {}

        # 提交所有任务
        for i in range(num_chunks):
            start = i * chunk_size + 1
            end = min((i + 1) * chunk_size, total_lines)
            future = executor.submit(read_chunk, file_path, start, end, i)
            futures[future] = i

        # 收集结果
        for future in as_completed(futures):
            chunk_id, lines, error = future.result()

            if error:
                print(f"⚠️  批次 {chunk_id+1} 失败: {error}", file=sys.stderr)
                failed_chunks.append(chunk_id)
            else:
                chunks[chunk_id] = lines
                print(f"✓ 批次 {chunk_id+1}/{num_chunks} 完成（{len(lines)} 行）", file=sys.stderr)

    # 4. 重试失败的批次
    if failed_chunks:
        print(f"重试失败的批次: {failed_chunks}", file=sys.stderr)
        for chunk_id in failed_chunks:
            start = chunk_id * chunk_size + 1
            end = min((chunk_id + 1) * chunk_size, total_lines)
            _, lines, error = read_chunk(file_path, start, end, chunk_id)

            if error:
                print(f"✗ 批次 {chunk_id+1} 重试失败: {error}", file=sys.stderr)
                sys.exit(1)
            else:
                chunks[chunk_id] = lines
                print(f"✓ 批次 {chunk_id+1} 重试成功", file=sys.stderr)

    # 5. 按顺序合并
    all_lines = []
    for i in range(num_chunks):
        if i not in chunks:
            print(f"✗ 批次 {i+1} 缺失", file=sys.stderr)
            sys.exit(1)
        all_lines.extend(chunks[i])

    # 6. 验证行数
    if len(all_lines) != total_lines:
        print(f"⚠️  警告: 预期 {total_lines} 行, 实际 {len(all_lines)} 行", file=sys.stderr)
        sys.exit(1)

    print(f"✅ 读取完成: {total_lines} 行", file=sys.stderr)
    return ''.join(all_lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='并行读取大文件')
    parser.add_argument("--file", required=True, help="文件路径")
    parser.add_argument("--chunk-size", type=int, default=500, help="每批行数（默认500）")
    parser.add_argument("--max-workers", type=int, default=4, help="并发数（默认4）")
    args = parser.parse_args()

    try:
        content = parallel_read_file(args.file, args.chunk_size, args.max_workers)
        print(content)  # 输出到 stdout
    except Exception as e:
        print(f"✗ 错误: {e}", file=sys.stderr)
        sys.exit(1)
