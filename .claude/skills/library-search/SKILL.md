---
name: library-search
description: Search gegeewu-library archives using three-layer search (JSON index + Obsidian REST API full-text + structured query). 用户说"搜索知识库"、"查找归档"、"library search"时触发。
user-invocable: true
allowed-tools: Bash Read Grep
---

# library-search

Use this skill before any new intake or to search existing archives.

## Goal
- Prevent duplicate archives
- Return the best existing match and the next action
- Support multi-dimensional search (exact, full-text, structured)

## Search Modes

### Mode A: Duplicate Check (intake internal)
- Execute: Layer 1 + Layer 2
- Return: hit/miss + recommended action (update/create new)

### Mode B: User Search
- Execute: Layer 1 + Layer 2 + Layer 3 (as needed)
- Return: matching entries list + summary info

## Three-Layer Search

### Layer 1: JSON Exact Match
- File: `reference/library-index.json`
- Match against: name, slug, aliases (exact or fuzzy)
- Optional filter: type, category, tags

### Layer 2: Obsidian REST API Full-Text
- API: `POST https://127.0.0.1:27124/search/simple/?query=<keyword>`
- Header: `Authorization: Bearer ${OBSIDIAN_REST_API_KEY}`
- TLS: skip cert verification

### Layer 3: JSON Structured Filtering
- Filter by type / category / tags from `library-index.json`
- Examples:
  - "All AI agent projects" → type=project, category=ai/agent
  - "CLI tools" → tags contains "cli"
  - "Recent archives" → sort by updated_at desc

## Search Routing
- **Duplicate check**: Layer 1 + Layer 2
- **Exact lookup** ("is opencli archived?"): Layer 1 only
- **Fuzzy search** ("CLI related"): Layer 1 tags + Layer 2 full-text
- **Category browse** ("all AI agent"): Layer 3 structured
- **Broad search** ("tools for posting to XHS"): Layer 1 + Layer 2 combined

## Expected Output
- Type, match status (exact / close / none)
- Existing name, path, category and tags
- Recommended action: update existing / create new

## Hard Rules
- JSON index alone is not enough; check Obsidian too
- If the two disagree, report drift
- If REST API is unavailable: stop and report error
- Do not falsely report search results
