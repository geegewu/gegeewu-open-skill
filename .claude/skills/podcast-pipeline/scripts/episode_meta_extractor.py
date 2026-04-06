#!/usr/bin/env python3
"""Episode metadata extraction prompt template and JSON schema.

This module defines the prompt and expected output format for extracting
structured metadata (host, guests, key_names) from podcast episode descriptions.

The actual LLM call is done by the agent using its own model (subagent default
or primary model), NOT by this script directly.

Usage by agent:
    1. Read the system_prompt from get_extraction_prompt()
    2. Call LLM with the episode description as user message
    3. Parse the JSON response
    4. Write to state['extracted_meta']
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Expected JSON output schema
META_SCHEMA = {
    "host": "本期实际主持人姓名",
    "host_title": "主持人头衔/身份（没有则留空）",
    "guests": [{"name": "嘉宾姓名", "title": "嘉宾头衔/身份"}],
    "summary": "一句话干净概要（≤100字）",
    "key_names": ["人名或专有名词（用于 Whisper 转录纠错）"],
}


def get_extraction_prompt(podcast_name: str, static_hosts: str = "", lang: str = "zh") -> str:
    """Return the system prompt for metadata extraction.

    The agent should use this as the system message, with the episode
    description as the user message.
    """
    lang_hint = "中文" if lang == "zh" else "English"
    return f"""你是播客元信息提取器。从播客 episode 的 description 中提取结构化信息。

播客名称：{podcast_name}
静态主持人（可能不准确）：{static_hosts}
语言：{lang_hint}

请严格输出以下 JSON 格式（不要输出其他内容）：
{{
  "host": "本期实际主持人姓名",
  "host_title": "主持人头衔/身份（从 description 提取，没有则留空）",
  "guests": [{{"name": "嘉宾姓名", "title": "嘉宾头衔/身份"}}],
  "summary": "一句话干净概要（去广告、去节目推广噪音，≤100字）",
  "key_names": ["人名或专有名词1", "人名或专有名词2"]
}}

规则：
1. host 优先从 description 提取，如果 description 没有明确主持人信息，使用静态主持人
2. guests 只提取本期嘉宾，不含主持人
3. key_names 包含所有在 description 中出现的人名、产品名、公司名（用于 Whisper 转录纠错）
4. summary 必须干净：去掉广告、赞助商信息、往期推荐、订阅提示等噪音
5. 如果某字段无法提取，用空字符串或空列表"""


def parse_meta_response(raw: str) -> dict[str, Any]:
    """Parse and validate LLM response into structured metadata dict."""
    # Strip code fences if present
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[: text.rfind("```")]
    text = text.strip()

    result = json.loads(text)

    # Ensure all expected keys exist
    expected_keys = {"host", "host_title", "guests", "summary", "key_names"}
    for key in expected_keys:
        if key not in result:
            result[key] = [] if key in ("guests", "key_names") else ""

    return result
