#!/usr/bin/env python3
"""Step 3b+c executor with real Round 1 concurrency."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROUND1_CONCURRENCY = 5
MODEL_NAME = os.environ.get("STEP3_MODEL", "claude-3-5-sonnet-20241022")


def _normalize_batch(batch: object, batch_idx: int) -> dict:
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


def _build_round1_prompt(meta: dict, batch_info: dict, total_batches: int) -> str:
    line_scope = ""
    if batch_info.get("start_line") and batch_info.get("end_line"):
        line_scope = (
            f"\n片段范围：第 {batch_info['start_line']}-{batch_info['end_line']} 行"
            f"\n核心区间：第 {batch_info.get('core_start_line', batch_info['start_line'])}-"
            f"{batch_info.get('core_end_line', batch_info['end_line'])} 行"
            f"\n边界重叠：前后最多各 {batch_info.get('overlap_lines', 0)} 行仅用于上下文，"
            "不要把重复边界内容当成新的主要信息。"
        )
    return f"""你是播客转录提炼助手。当前处理的播客：
- 节目：{meta.get('节目', 'N/A')}
- 标题：{meta.get('标题', 'N/A')}
- 主持人：{meta.get('主持人', 'N/A')}
- 嘉宾：{meta.get('嘉宾', '')}
- 简介：{meta.get('简介', '')}
- 关键人名（用于修正 Whisper 转录错误）：{meta.get('关键人名', '')}

你的任务：
1. 阅读这一段转录文本（是完整转录的第 {batch_info['batch']}/{total_batches} 片段）
2. 提取核心内容：谁说了什么，具体观点、例子、数字
3. 修正明显的转录错误（参考关键人名列表）
4. 输出 400-500 字的中文摘要
5. 注明这段在整期节目中的位置感（开场/展开/深入/收尾）

要求：
- 保留具体的类比、案例、数字
- 标注"谁说的"，不模糊归因
- 不要添加评论或感受，只做忠实提炼
- 输出纯文本，不要 markdown 格式
- 无论原文是什么语言，一律用中文输出（专有名词保留英文原文）
- 如果边界内容和前后片段重复，只保留一次，不要因为 overlap 重复记述

{line_scope}
转录内容：
{batch_info['text']}

直接输出摘要，无需其他解释。"""


def _run_round1_batch(client, meta: dict, batch_info: dict, total_batches: int) -> tuple[int, dict]:
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=700,
        messages=[{"role": "user", "content": _build_round1_prompt(meta, batch_info, total_batches)}],
    )
    return batch_info["batch"], {
        "batch": batch_info["batch"],
        "start_line": batch_info.get("start_line"),
        "end_line": batch_info.get("end_line"),
        "core_start_line": batch_info.get("core_start_line"),
        "core_end_line": batch_info.get("core_end_line"),
        "summary": response.content[0].text.strip(),
    }


def run_step3(output_dir: str):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    batches_file = output_dir / "batches.json"
    meta_file = output_dir / "meta.json"

    if not batches_file.exists() or not meta_file.exists():
        print("❌ batches.json 或 meta.json 不存在")
        return False

    batches = json.loads(batches_file.read_text(encoding="utf-8"))
    meta = json.loads(meta_file.read_text(encoding="utf-8"))

    print(f"📖 读取 {len(batches)} 个 batch，开始 Round 1+2...")

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

        normalized_batches = [_normalize_batch(batch, i) for i, batch in enumerate(batches, start=1)]
        summaries: list[dict] = [{} for _ in normalized_batches]
        max_workers = min(ROUND1_CONCURRENCY, max(1, len(batches)))
        print(f"⚡ Round 1 并发启动：{len(batches)} 个 batch，最大并发 {max_workers}")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(_run_round1_batch, client, meta, batch_info, len(normalized_batches))
                for batch_info in normalized_batches
            ]
            for future in as_completed(futures):
                batch_idx, summary_info = future.result()
                summaries[batch_idx - 1] = summary_info
                print(f"  ✅ Batch {batch_idx}/{len(batches)} 完成")

        summaries_path = output_dir / "summaries.json"
        summaries_path.write_text(
            json.dumps(summaries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"✅ Round 1 完成，summaries.json 已保存（{len(summaries)} 段）")

        summaries_text = "\n\n---\n\n".join([
            (
                f"【第 {summary['batch']} 段摘要】\n"
                f"覆盖行号：{summary.get('start_line')}-{summary.get('end_line')}\n"
                f"核心区间：{summary.get('core_start_line')}-{summary.get('core_end_line')}\n"
                f"{summary['summary']}"
            )
            for summary in summaries
        ])

        round2_prompt = f"""你是非虚构写作者。将以下播客摘要重构为有叙事张力的文章。

当前播客：{meta.get('标题', 'N/A')}

摘要如下：
{summaries_text}

你的任务：
1. 找到这期播客的一条核心叙事线
2. 围绕这条线重新组织材料，输出 2800-3500 字的核心文本
3. 保留嘉宾的具体类比、案例、数字
4. 来源精确：谁说的就是谁说的
5. 语言平实，禁止LLM总结体、虚假升华、并列堆砌
6. 相邻摘要来自带 overlap 的窗口，边界信息可能重复；汇总时按 batch 顺序保留时间线，并把重复边界内容去重，只保留一次

输出纯中文文本（专有名词如GPT、OpenAI保留英文）。"""

        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=4000,
            messages=[{"role": "user", "content": round2_prompt}],
        )
        narrative = response.content[0].text

        narrative_file = output_dir / "narrative.md"
        narrative_file.write_text(narrative, encoding="utf-8")
        print(f"✅ Round 2 完成，narrative.md 已保存")

        print("⏳ 运行 finalize...")
        result = subprocess.run([
            os.environ.get("PYTHON", str(Path.home() / "myenv" / "bin" / "python3")), "step3_pipeline.py", "finalize",
            "--narrative-file", str(narrative_file),
            "--output-dir", str(output_dir)
        ], cwd=str(Path(__file__).resolve().parent), capture_output=True, text=True)

        if result.returncode != 0:
            print(result.stdout.strip())
            print(f"❌ finalize 失败：{result.stderr.strip()}")
            return False

        print(result.stdout.strip())
        print("✅ Step 3 完成：cards.json 已生成")
        return True

    except Exception as e:
        print(f"❌ 错误：{e}")
        return False


if __name__ == "__main__":
    output_dir = sys.argv[1] if len(sys.argv) > 1 else "output/Zhang_Jun/"
    success = run_step3(output_dir)
    sys.exit(0 if success else 1)
