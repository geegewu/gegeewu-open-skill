---
name: summarize
description: Summarize URLs, local files, PDFs, images, audio, or YouTube links using the summarize CLI. 用户说"总结这个链接"、"摘要"、"summarize"时触发。
user-invocable: true
allowed-tools: Bash Read
---

# Summarize

Fast CLI to summarize URLs, local files, and YouTube links.

## Quick Start

```bash
summarize "https://example.com" --model google/gemini-3-flash-preview
summarize "/path/to/file.pdf" --model google/gemini-3-flash-preview
summarize "https://youtu.be/VIDEO_ID" --youtube auto
```

## Model + Keys

Set the API key for your chosen provider:
- Google: `GEMINI_API_KEY`
- OpenAI: `OPENAI_API_KEY`
- Anthropic: `ANTHROPIC_API_KEY`
- xAI: `XAI_API_KEY`

Default model is `google/gemini-3-flash-preview` if none is set.

## Useful Flags

- `--length short|medium|long|xl|xxl|<chars>` — summary length
- `--max-output-tokens <count>` — max tokens
- `--extract-only` — extract content without summarizing (URLs only)
- `--json` — machine readable output
- `--firecrawl auto|off|always` — fallback extraction for blocked sites
- `--youtube auto` — Apify fallback if `APIFY_API_TOKEN` set

## Config

Optional config file: `~/.summarize/config.json`

```json
{ "model": "google/gemini-3-flash-preview" }
```

## Optional Services
- `FIRECRAWL_API_KEY` for blocked sites
- `APIFY_API_TOKEN` for YouTube fallback
