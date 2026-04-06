#!/usr/bin/env python3
"""
Round 1：并发处理 batches，生成摘要。
输入：batches.json
输出：summaries.json
"""
import json
import sys
import asyncio
import os
from pathlib import Path

# 注意：这是一个子脚本，需要在主 agent 的并发调用中使用
# 实际的批处理应该由 Claude 直接以并发方式调用


def load_batches(batches_file: str) -> list:
    """Load batch data from JSON."""
    with open(batches_file) as f:
        return json.load(f)


def load_meta(meta_file: str) -> dict:
    """Load metadata."""
    with open(meta_file) as f:
        return json.load(f)


def normalize_batch(batch: object, batch_idx: int) -> dict:
    if isinstance(batch, dict):
        return batch
    return {
        "batch": batch_idx,
        "start_line": None,
        "end_line": None,
        "core_start_line": None,
        "core_end_line": None,
        "overlap_lines": 0,
        "text": str(batch),
    }


def generate_round1_prompt(meta: dict, batch_info: dict, total_batches: int) -> str:
    """Generate system + user prompt for Round 1."""
    line_scope = ""
    if batch_info.get("start_line") and batch_info.get("end_line"):
        line_scope = (
            f"\n片段范围：第 {batch_info['start_line']}-{batch_info['end_line']} 行"
            f"\n核心区间：第 {batch_info.get('core_start_line', batch_info['start_line'])}-"
            f"{batch_info.get('core_end_line', batch_info['end_line'])} 行"
            f"\n边界重叠：前后最多各 {batch_info.get('overlap_lines', 0)} 行仅用于上下文，"
            "不要把重复边界内容当成新的主要信息。"
        )

    system = f"""你是播客转录提炼助手。当前处理的播客：
- 节目：{meta['节目']}
- 标题：{meta['标题']}
- 主持人：{meta['主持人']}
- 嘉宾：{meta.get('嘉宾', '')}
- 简介：{meta['简介'][:200]}...
- 关键人名（用于修正 Whisper 转录错误）：{meta.get('关键人名', '')}

你的任务：
1. 阅读这一段转录文本（是完整转录的第 {batch_info['batch']}/{total_batches} 片段）
2. 提取核心内容：谁说了什么，具体观点、例子、数字
3. 修正明显的转录错误（参考关键人名列表）
   - 即使关键人名列表为空，也要根据主题和上下文，用领域知识修正转录错误
   - 中文常见：同音/近音字替换（如"多么泰"→"多模态"、"可令"→"可灵"、"豆包"不要写成"抖包"）
   - 英文常见：专有名词拼写错误（如"Samman"→"Sam Altman"、"Whimo"→"Waymo"、"Entropic"→"Anthropic"）
   - AI/科技高频词表（Whisper 常错）：
     Anthropic, OpenAI, DeepSeek, Mistral, Gemini, Claude, GPT, LLaMA, Whisper,
     Kimi, MiniMax, Moonshot, Zhipu/智谱, Baichuan/百川, Qwen/通义千问,
     NVIDIA, AMD, TSMC, Hugging Face, LangChain, RAG, LoRA, RLHF, MoE
4. 输出 400-500 字的段落摘要
5. 注明这段在整期节目中的位置感（开场/展开/深入/收尾）

要求：
- 保留具体的类比、案例、数字
- 标注"谁说的"，不模糊归因
- 不要添加评论或感受，只做忠实提炼
- 输出纯文本，不要 markdown 格式
- 如果边界内容和前后片段重复，只保留一次，不要因为 overlap 重复记述
- ⚠️ 无论原文是什么语言，一律用中文输出（专有名词保留英文原文，如 GPT-5.4、OpenAI）"""

    user = f"""以下是第 {batch_info['batch']}/{total_batches} 段转录文本：{line_scope}

{batch_info['text']}"""

    return system, user


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 round1_batch_processor.py <output_dir>")
        sys.exit(1)
    
    output_dir = sys.argv[1]
    batches_file = Path(output_dir) / "batches.json"
    meta_file = Path(output_dir) / "meta.json"
    
    batches = load_batches(str(batches_file))
    meta = load_meta(str(meta_file))
    
    print(f"[Round 1] 加载 {len(batches)} 个 batch，准备生成摘要...")
    print(f"[Round 1] 批次信息已准备，等待 agent 并发处理")
    
    # 输出 batch 信息供 agent 使用
    for i, batch in enumerate(batches, 1):
        batch_info = normalize_batch(batch, i)
        print(f"\n📝 Batch {i}/{len(batches)}")
        system, user = generate_round1_prompt(meta, batch_info, len(batches))
        print(f"   Text length: {len(batch_info['text'])} chars")
        if batch_info.get("start_line") and batch_info.get("end_line"):
            print(
                f"   Lines: {batch_info['start_line']}-{batch_info['end_line']} "
                f"(core {batch_info.get('core_start_line')}-{batch_info.get('core_end_line')})"
            )
