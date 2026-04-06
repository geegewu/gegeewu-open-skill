#!/usr/bin/env python3
"""
并发预处理 blog-digest 文件，提取元数据供 LLM 快速筛选

输入：blog-digests/YYYY-MM-DD.md（18K，30 篇文章）
输出：JSON（~3K，结构化元数据）

优势：
- 并发处理（8 线程，秒级完成）
- LLM 输入缩小 6x（18K → 3K）
- 跳过两轮筛选（直接 30 → 6-8 篇）
"""
import argparse
from pathlib import Path
import re
from concurrent.futures import ThreadPoolExecutor
import json
import sys


def extract_article_metadata(article_text, index, summary_max_chars=300):
    """提取单篇文章的元数据（不用 LLM，纯正则 + 字符串处理）
    
    Args:
        article_text: 文章正文
        index: 文章索引
        summary_max_chars: 摘要最大字符数（默认 300，适配 47 篇场景）
    """
    lines = article_text.strip().split('\n')
    
    # 提取标题（第一个 ## 开头的行，移除 markdown 链接）
    title = ""
    for line in lines:
        if line.startswith('## '):
            title = line[3:].strip()
            # 移除 [text](url) → text
            title = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', title)
            break
    
    # 提取来源域名和发布日期
    domain = ""
    published = ""
    for line in lines:
        if line.startswith('**来源**:'):
            # **来源**: example.com | **发布**: 2026-02-24
            parts = line.split('**来源**:')[1].split('|')
            domain = parts[0].strip()
            if len(parts) > 1 and '**发布**:' in parts[1]:
                pub_match = re.search(r'\*\*发布\*\*:\s*(\S+)', parts[1])
                if pub_match:
                    published = pub_match.group(1)
        elif '**发布**:' in line and not published:
            pub_match = re.search(r'\*\*发布\*\*:\s*(\S+)', line)
            if pub_match:
                published = pub_match.group(1)
    
    # 提取摘要（跳过标题和元信息行，取第一段正文）
    summary_lines = []
    in_summary = False
    for line in lines:
        stripped = line.strip()
        # 跳过标题、分隔线、元信息
        if stripped.startswith('##') or stripped.startswith('---') or stripped.startswith('**来源**') or stripped.startswith('**发布**'):
            in_summary = True  # 元信息后进入摘要区
            continue
        
        if in_summary and stripped:
            summary_lines.append(stripped)
            if len(' '.join(summary_lines)) > summary_max_chars:
                break
    
    summary = ' '.join(summary_lines)[:summary_max_chars].strip()
    
    # 计算信息密度评分（供 LLM 参考）
    # 更长的文章 + 更长的摘要 = 更可能有深度内容
    density_score = min(100, (len(article_text) / 10) + (len(summary) / 2))
    
    return {
        'index': index,
        'title': title,
        'domain': domain,
        'published': published,
        'summary': summary,
        'char_count': len(article_text),
        'density_score': round(density_score, 1)
    }


def preprocess_digest(input_file, max_workers=8, summary_max_chars=300):
    """并发预处理 digest 文件
    
    Args:
        input_file: 输入文件路径
        max_workers: 并发线程数
        summary_max_chars: 每篇摘要最大字符数（30篇→300，47篇→200）
    """
    content = Path(input_file).read_text(encoding='utf-8')
    
    # 移除 front matter
    body = re.sub(r'^---\n.*?---\n', '', content, count=1, flags=re.DOTALL)
    
    # 分割文章（用 \n---\n 分隔）
    articles = [a.strip() for a in body.split('\n---\n') if a.strip() and len(a.strip()) > 50]
    
    print(f"📊 正在并发处理 {len(articles)} 篇文章（{max_workers} 线程，摘要上限 {summary_max_chars} 字）...", file=sys.stderr)
    
    # 并发提取元数据
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(
            lambda x: extract_article_metadata(x[1], x[0], summary_max_chars),
            enumerate(articles)
        ))
    
    # 按 density_score 降序排序（可选，供 LLM 快速定位高质量文章）
    results.sort(key=lambda x: x.get('density_score', 0), reverse=True)
    
    # 预计输出大小
    output_size_kb = sum(len(json.dumps(r, ensure_ascii=False)) for r in results) / 1024
    
    print(f"✅ 预处理完成：{len(results)} 篇文章元数据已提取", file=sys.stderr)
    print(f"   预计输出大小：{output_size_kb:.1f} KB（原文 {len(content)/1024:.1f} KB，压缩率 {output_size_kb/(len(content)/1024)*100:.0f}%）", file=sys.stderr)
    
    return {
        'total': len(articles),
        'articles': results,
        'summary_max_chars': summary_max_chars
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='并发预处理 blog-digest 文件，提取元数据供 LLM 快速筛选'
    )
    parser.add_argument('input_file', help='输入文件路径（blog-digests/YYYY-MM-DD.md）')
    parser.add_argument('--max-workers', type=int, default=8, help='并发线程数（默认 8）')
    parser.add_argument('--summary-max-chars', type=int, default=300, 
                        help='每篇摘要最大字符数（默认 300，30篇→300，47篇→200）')
    parser.add_argument('--output', '-o', help='输出 JSON 文件路径（默认 stdout）')
    args = parser.parse_args()
    
    result = preprocess_digest(args.input_file, args.max_workers, args.summary_max_chars)
    
    output = json.dumps(result, ensure_ascii=False, indent=2)
    
    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
        print(f"✅ 已保存到 {args.output}", file=sys.stderr)
    else:
        print(output)
