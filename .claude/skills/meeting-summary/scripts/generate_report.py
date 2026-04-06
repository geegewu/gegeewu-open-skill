#!/usr/bin/env python3
"""
generate_report.py - Convert meeting summary JSON to a self-contained offline HTML report.
Apple-inspired style: minimal, clear hierarchy, print-safe.

Usage:
    python3 generate_report.py --json /tmp/meeting_summary.json --output /tmp/meeting_report.html
"""

import argparse
import base64
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

:root {{
  --white: #ffffff;
  --ink: #1d1d1f;
  --ink2: #424245;
  --gray: #6e6e73;
  --line: #d2d2d7;
  --bg: #f5f5f7;
  --blue: #0a66d9;
  --blue-soft: #eaf3ff;
  --cyan-soft: #eff8ff;
  --green-soft: #eefaf2;
  --red-soft: #fff3f3;
  --orange-soft: #fff8f0;
  --warn-soft: #fff9e8;
  --warn-line: #f5b400;
  --high-line: #d93025;
  --medium-line: #f29900;
  --font: -apple-system, "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
  --font-display: -apple-system, "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}}

html {{ font-size: 16px; }}

body {{
  font-family: var(--font);
  background: var(--white);
  color: var(--ink);
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}}

.wrap {{
  max-width: 760px;
  margin: 0 auto;
  padding: 56px 28px 80px;
}}

/* Cover */
.cover {{
  padding: 28px 28px 44px;
  border-radius: 22px;
  background: linear-gradient(160deg, #ffffff 0%, #f8fbff 100%);
  margin-bottom: 56px;
  page-break-after: auto;
}}
.cover-eyebrow {{
  display: inline-flex;
  align-items: center;
  font-size: 0.76rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: #1752b3;
  background: var(--blue-soft);
  border: 1px solid #d9e9ff;
  border-radius: 999px;
  padding: 5px 12px;
  margin-bottom: 18px;
}}
.cover h1 {{
  font-family: var(--font-display);
  font-size: 2.7rem;
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.15;
  color: var(--ink);
  margin-bottom: 20px;
}}
.cover-meta {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 20px;
  font-size: 0.9rem;
  color: var(--ink2);
}}
.cover-meta-item {{
  display: flex;
  align-items: baseline;
  gap: 6px;
}}
.cover-meta-label {{
  color: var(--gray);
  white-space: nowrap;
}}
.cover-divider {{
  margin-top: 22px;
  height: 2px;
  background: linear-gradient(90deg, transparent 0%, #b8d4ff 15%, #8bb6ff 50%, #b8d4ff 85%, transparent 100%);
}}

/* Section */
.section {{
  margin-bottom: 54px;
}}
.section-label {{
  font-size: 1.05rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  text-transform: none;
  color: var(--ink);
  margin-bottom: 20px;
  padding: 8px 18px 8px 14px;
  background: #f0f4ff;
  border-left: 3px solid var(--line);
  border-radius: 0 6px 6px 0;
  display: block;
}}
.section-mindmap .section-label {{ border-left-color: #9bbdf2; background: #eef4ff; }}
.section-summary .section-label {{ border-left-color: #8cb6ff; background: #eef4ff; }}
.section-decisions .section-label {{ border-left-color: #8cb6ff; background: #eef4ff; }}
.section-todos .section-label {{ border-left-color: #f0ba72; background: #fff6ec; }}
.section-risks .section-label {{ border-left-color: #efc55d; background: #fffaec; }}

/* Markmap SVG wrap */
.markmap-wrap {{
  width: 100%;
  overflow-x: auto;
  background: #fafbff;
  border-radius: 14px;
  padding: 16px 8px;
}}
.markmap-wrap svg {{
  width: 100%;
  height: auto;
  min-height: 260px;
  display: block;
}}
.markmap-frame {{
  width: 100%;
  height: 460px;
  border: 0;
  border-radius: 12px;
  background: #fafbff;
}}
.mindmap-print-fallback {{
  display: none;
}}

/* Mindmap tree (pure CSS fallback) */
.mindmap {{
  margin-top: 6px;
  padding-left: 2px;
}}
.mm-node {{
  position: relative;
  border-left: 1px solid #d5dbe5;
  margin: 3px 0;
  padding: 8px 0 8px 16px;
}}
.mm-node::before {{
  content: "";
  position: absolute;
  left: -1px;
  top: 18px;
  width: 12px;
  border-top: 1px solid #d5dbe5;
}}
.mm-node.depth-1 {{
  margin-top: 20px;
  margin-left: 0;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #6b84a8;
  border-left: none;
  padding: 4px 0 2px 2px;
  background: none;
}}
.mm-node.depth-1::before {{ display: none; }}
.mm-node.depth-1:first-child {{ margin-top: 4px; }}
.mm-node.depth-2 {{
  margin-top: 6px;
  margin-left: 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: #1a2540;
  background: linear-gradient(90deg, #f0f5ff 0%, #ffffff 88%);
  border-left-color: #5a9af0;
  border-radius: 8px;
  padding-left: 14px;
}}
.mm-node.depth-2::before {{ border-top-color: #5a9af0; }}
.mm-node.depth-3 {{
  margin-left: 20px;
  font-size: 0.875rem;
  font-weight: 400;
  color: #4b5563;
}}
.mm-text {{
  display: inline-block;
  line-height: 1.55;
}}

/* Summary */
.summary-row {{
  padding: 16px 0 18px;
}}
.summary-row + .summary-row {{
  margin-top: 8px;
  border-top: 1px solid #ececf0;
}}
.summary-head {{
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 9px;
}}
.summary-index {{
  font-family: var(--font-mono);
  font-size: 0.74rem;
  color: #9aa0a6;
  min-width: 22px;
}}
.summary-topic {{
  border-left: 3px solid #8cb6ff;
  padding-left: 10px;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--ink);
}}
.summary-content {{
  font-size: 0.9rem;
  color: var(--ink2);
  line-height: 1.78;
  padding-left: 34px;
}}
.summary-content code {{
  font-family: var(--font-mono);
  font-size: 0.82em;
  background: #eef3ff;
  color: #1a4ccc;
  border-radius: 4px;
  padding: 1px 6px;
  border: 1px solid #d4e2ff;
  font-weight: 500;
}}

/* Decisions */
.decision-row {{
  padding: 14px 0;
}}
.decision-row + .decision-row {{
  border-top: 1px solid #ececf0;
}}
.decision-text {{
  font-size: 0.92rem;
  color: var(--ink);
  line-height: 1.65;
  font-weight: 600;
}}
.decision-meta {{
  margin-top: 6px;
  font-size: 0.79rem;
  color: var(--gray);
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}}
.owner-pill {{
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  border: 1px solid #d9e9ff;
  background: #eef5ff;
  color: #1950aa;
  padding: 1px 10px;
}}
.decision-time {{
  font-family: var(--font-mono);
  letter-spacing: 0.01em;
}}

/* Todos */
.todo-row {{
  padding: 14px 0;
}}
.todo-row + .todo-row {{
  border-top: 1px solid #ececf0;
}}
.todo-task {{
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--ink);
  line-height: 1.55;
  margin-bottom: 4px;
}}
.todo-info {{
  margin-top: 6px;
  font-size: 0.79rem;
  color: var(--gray);
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}}
.todo-priority {{
  border-radius: 999px;
  padding: 0 8px;
  border: 1px solid #e2e3e7;
  color: #5f6368;
  background: #ffffff;
}}
.todo-priority.high {{
  color: #a52714;
  border-color: #f1c9c5;
  background: #fff7f6;
}}
.todo-priority.medium {{
  color: #8a5a00;
  border-color: #f5dfbf;
  background: #fffaf2;
}}
.todo-time {{
  font-family: var(--font-mono);
}}

/* Risks */
.risk-row {{
  padding: 14px 0;
  font-size: 0.89rem;
  color: var(--ink);
  line-height: 1.65;
}}
.risk-row + .risk-row {{
  border-top: 1px solid #ececf0;
}}

/* Markmap live (hidden until CDN loads) */
#markmap-live {{
  display: none;
}}

/* Todo group label */
.todo-group-label {{
  font-size: 0.76rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  padding: 14px 0 5px;
  margin-top: 2px;
  border-bottom: 1px solid var(--line);
  color: var(--gray);
}}
.todo-group-label:first-child {{
  padding-top: 2px;
}}
.todo-group-label.high {{
  color: #a52714;
}}
.todo-group-label.medium {{
  color: #8a5a00;
}}

/* Sticky nav */
.topnav {{
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(255,255,255,0.92);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--line);
  display: flex;
  gap: 0;
  padding: 0 4px;
  margin: -40px -28px 44px;
}}
.topnav a {{
  display: inline-block;
  padding: 11px 14px;
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--gray);
  text-decoration: none;
  border-bottom: 2px solid transparent;
  white-space: nowrap;
}}
.topnav a:hover {{ color: var(--blue); border-bottom-color: var(--blue); }}
@media print {{
  .topnav {{ display: none; }}
  .section {{ page-break-before: always; break-before: page; }}
}}

/* Footer */
.footer {{
  margin-top: 62px;
  padding-top: 18px;
  border-top: 2px solid transparent;
  border-image: linear-gradient(90deg, transparent, #d0d8e8, #d0d8e8, transparent) 1;
  font-size: 0.76rem;
  color: #8a8a90;
  text-align: center;
}}


/* Print */
@media print {{
  body {{ background: white; }}
  .wrap {{
    max-width: 680px;
    width: 680px;
    margin: 0 auto;
    padding: 0;
  }}
  .cover {{
    page-break-after: always;
    break-after: page;
  }}
  .section {{
    page-break-inside: auto;
    break-inside: auto;
  }}
  .summary-row, .decision-row, .todo-row, .risk-row {{
    break-inside: avoid;
    page-break-inside: avoid;
  }}
  .markmap-wrap, .section-mindmap {{
    break-inside: avoid;
    page-break-inside: avoid;
  }}
  .markmap-frame {{
    height: 320px;
  }}
  .mindmap-print-fallback {{
    display: none !important;
  }}
  @page {{
    size: A4;
    margin: 18mm 16mm 18mm 16mm;
  }}
}}
</style>
</head>
<body>
<div class="wrap">
  <nav class="topnav">
    <a href="#mindmap">思维导图</a>
    <a href="#summary">议题摘要</a>
    <a href="#decisions">关键决策</a>
    <a href="#todos">待办事项</a>
    <a href="#risks">风险</a>
  </nav>

  <div class="cover">
    <div class="cover-eyebrow">会议纪要</div>
    <h1>{title}</h1>
    <div class="cover-meta">
      <div class="cover-meta-item"><span class="cover-meta-label">日期：</span><span>{date}</span></div>
      <div class="cover-meta-item"><span class="cover-meta-label">时长：</span><span>{duration}</span></div>
      <div class="cover-meta-item" style="grid-column: 1 / -1;"><span class="cover-meta-label">参会：</span><span>{participants}</span></div>
      {tags_html}
    </div>
    <div class="cover-divider"></div>
  </div>

  <div class="section section-mindmap" id="mindmap">
    <div class="section-label">思维导图</div>
    {mindmap_html}
  </div>

  {summary_section}
  {decisions_section}
  {todos_section}
  {risks_section}

  <div class="footer">Generated by meeting-summary · {generated_at}</div>
</div>
</body>
</html>"""


def _strip_keyword_tail(text: str) -> str:
    """Remove LLM-generated trailing '关键词：`A` `B`' list from summary content."""
    import re
    return re.sub(r'\s*关键词[：:][^\n]*$', '', text, flags=re.MULTILINE).rstrip()


def _highlight_keywords(text: str) -> str:
    """Convert `keyword` markdown backticks to <code> HTML tags."""
    import re
    return re.sub(r'`([^`]+)`', r'<code>\1</code>', text)


def build_mindmap(mindmap_md: str) -> str:
    """Render horizontal markmap offline via markmap-cli --offline; fallback to CSS tree."""
    import html as _html
    import os
    import subprocess
    import tempfile

    md_path = None
    html_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", encoding="utf-8", delete=False) as f:
            f.write(mindmap_md.strip())
            md_path = f.name

        html_path = md_path.replace(".md", ".html")
        result = subprocess.run(
            [
                "npx",
                "--yes",
                "markmap-cli",
                md_path,
                "-o",
                html_path,
                "--no-open",
                "--offline",
                "--no-toolbar",
            ],
            capture_output=True,
            timeout=45,
        )

        if result.returncode == 0 and os.path.exists(html_path):
            raw_html = Path(html_path).read_text(encoding="utf-8")
            # Count level-2 nodes to decide layout direction
            level2_count = sum(1 for ln in mindmap_md.strip().splitlines() if ln.startswith("## "))
            if level2_count > 6:
                # Inject TB (top-bottom) matrix patch: swaps x↔y axes in SVG
                tb_patch = (
                    "<script>\n"
                    "(function applyTBLayout(){\n"
                    "  var attempt=0;\n"
                    "  function tryApply(){\n"
                    "    attempt++;\n"
                    "    var svg=document.querySelector('svg#mindmap');\n"
                    "    if(!svg){if(attempt<20)setTimeout(tryApply,300);return;}\n"
                    "    var g=svg.querySelector('g');\n"
                    "    if(!g){if(attempt<20)setTimeout(tryApply,300);return;}\n"
                    "    if(g.querySelectorAll('g.markmap-node').length===0){if(attempt<20)setTimeout(tryApply,300);return;}\n"
                    "    var cur=g.getAttribute('transform')||'';\n"
                    "    g.setAttribute('transform',cur+' matrix(0,1,1,0,0,0)');\n"
                    "    setTimeout(function(){if(window.mm&&window.mm.fit)window.mm.fit();},100);\n"
                    "  }\n"
                    "  setTimeout(tryApply,600);\n"
                    "})();\n"
                    "</script>\n"
                )
                raw_html = raw_html.replace("</body>", tb_patch + "</body>")
            srcdoc = _html.escape(raw_html, quote=True)
            iframe_html = (
                f'<iframe class="markmap-frame" loading="lazy" srcdoc="{srcdoc}"></iframe>'
            )
            css_tree = _build_css_tree(mindmap_md)
            return (
                '<div class="markmap-wrap">'
                + iframe_html
                + f'<div class="mindmap-print-fallback">{css_tree}</div>'
                + '</div>'
            )
    except Exception:
        pass
    finally:
        for p in [md_path, html_path]:
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except Exception:
                    pass

    # Fallback: CSS tree only
    return '<div class="markmap-wrap">' + _build_css_tree(mindmap_md) + '</div>'


def _estimate_max_horizontal_nodes(mindmap_md: str) -> int:
    """Estimate max horizontal node count by sibling breadth across the heading tree."""
    counts: dict[tuple[int, str], int] = {}
    stack: list[str] = []

    for raw in mindmap_md.strip().splitlines():
        line = raw.strip()
        if not line.startswith("#"):
            continue
        depth = len(line) - len(line.lstrip("#"))
        if depth <= 0:
            continue

        title = line.lstrip("#").strip()
        if not title:
            continue

        while len(stack) >= depth:
            stack.pop()

        parent_key = " / ".join(stack[: depth - 1])
        key = (depth, parent_key)
        counts[key] = counts.get(key, 0) + 1

        stack.append(title)

    return max(counts.values(), default=0)


def _patch_srcdoc_markmap_options(raw_html: str, options: dict) -> str:
    """Patch generated markmap srcdoc call arg from null -> json options."""
    import json
    import re

    options_json = json.dumps(options, ensure_ascii=False, separators=(",", ":"))

    # markmap-cli output pattern:
    # ...})(() => window.markmap,null,<rootObject>,null)
    pattern = re.compile(
        r"(\}\)\(\(\)\s*=>\s*window\.markmap,null,.*),null\)(\s*</script>)",
        flags=re.DOTALL,
    )
    patched, n = pattern.subn(rf"\1,{options_json})\2", raw_html, count=1)
    if n:
        return patched

    # fallback: replace the last ',null)</script>' only once
    return raw_html.replace(",null)</script>", f",{options_json})</script>", 1)


def _inject_top_bottom_postprocess(raw_html: str) -> str:
    """Inject post-render JS to emulate top-bottom direction for wide mindmaps."""
    script = """
<script>
(function () {
  function applyTopBottom() {
    try {
      if (!window.mm || !window.mm.options || window.mm.options.direction !== 'top-bottom') return false;
      const svg = document.querySelector('svg#mindmap');
      if (!svg) return false;
      const root = svg.querySelector('g');
      if (!root) return false;

      const box = root.getBBox();
      const pad = 28;

      // Rotate the whole graph to emulate TB orientation.
      root.setAttribute('transform', `translate(${box.height + pad}, ${pad}) rotate(90)`);
      svg.setAttribute('viewBox', `0 0 ${Math.ceil(box.height + pad * 2)} ${Math.ceil(box.width + pad * 2)}`);
      svg.style.width = '100%';
      svg.style.height = `${Math.ceil(box.width + pad * 2)}px`;

      return true;
    } catch (e) {
      return false;
    }
  }

  let tries = 0;
  const timer = setInterval(() => {
    if (applyTopBottom() || ++tries > 20) clearInterval(timer);
  }, 120);
})();
</script>
""".strip()

    if "</body>" in raw_html:
      return raw_html.replace("</body>", script + "\n</body>", 1)
    return raw_html + "\n" + script


def _build_css_tree(mindmap_md: str) -> str:
    """Build pure-CSS mindmap tree (used for print and as fallback)."""
    nodes = []
    for line in mindmap_md.strip().splitlines():
        depth = len(line) - len(line.lstrip("#"))
        text = line.lstrip("#").strip()
        if not text or depth == 0:
            continue
        nodes.append(
            f'<div class="mm-node depth-{min(depth, 3)}">'
            f'<span class="mm-text">{text}</span>'
            f"</div>"
        )
    return '<div class="mindmap">\n' + "\n".join(nodes) + "\n</div>"


def build_summary(items: list) -> str:
    if not items:
        return ""

    rows = []
    for idx, item in enumerate(items, start=1):
        rows.append(
            f'<div class="summary-row">'
            f'<div class="summary-head">'
            f'<span class="summary-index">{idx:02d}</span>'
            f'<div class="summary-topic">{item.get("topic","")}</div>'
            f"</div>"
            f'<div class="summary-content">{_highlight_keywords(_strip_keyword_tail(item.get("content","")))}</div>'
            f"</div>"
        )

    return (
        '<div class="section section-summary" id="summary">'
        '<div class="section-label">议题摘要</div>'
        + "".join(rows)
        + "</div>"
    )


def build_decisions(items: list) -> str:
    if not items:
        return ""

    rows = []
    for item in items:
        meta = []
        if item.get("owner"):
            meta.append(f'<span class="owner-pill">负责人：{item["owner"]}</span>')
        if item.get("timestamp"):
            meta.append(f'<span class="decision-time">[{item["timestamp"]}]</span>')

        row = (
            f'<div class="decision-row">'
            f'<div class="decision-text">{item.get("content","")}</div>'
            + (f'<div class="decision-meta">{"".join(meta)}</div>' if meta else "")
            + "</div>"
        )
        rows.append(row)

    return (
        '<div class="section section-decisions" id="decisions">'
        '<div class="section-label">关键决策</div>'
        + "".join(rows)
        + "</div>"
    )


def build_todos(items: list) -> str:
    if not items:
        return ""

    group_labels = {
        "high": "🔴 高优先级",
        "medium": "🟡 中优先级",
        "low": "⚪ 低优先级",
    }
    priority_order = {"high": 0, "medium": 1, "low": 2}
    sorted_items = sorted(
        items,
        key=lambda x: priority_order.get(x.get("priority", "low"), 2),
    )

    inner = ""
    current_priority = None
    for item in sorted_items:
        priority = item.get("priority", "low")
        if priority not in priority_order:
            priority = "low"

        # 分组标题（每组只出现一次）
        if priority != current_priority:
            current_priority = priority
            label_class = priority if priority in ("high", "medium") else ""
            inner += (
                f'<div class="todo-group-label {label_class}">'
                f'{group_labels[priority]}'
                f"</div>"
            )

        due = item.get("due") or "待定"
        owner = item.get("owner") or "TBD"
        ts = item.get("timestamp", "")
        inner += (
            f'<div class="todo-row {priority}">'
            f'<div class="todo-task">{item.get("task","")}</div>'
            f'<div class="todo-info">'
            f'<span class="owner-pill">负责人：{owner}</span>'
            f'<span class="owner-pill">截止：{due}</span>'
            + (f'<span class="todo-time">[{ts}]</span>' if ts else "")
            + "</div></div>"
        )

    return (
        '<div class="section section-todos" id="todos">'
        '<div class="section-label">待办事项</div>'
        + inner
        + "</div>"
    )


def build_risks(items: list) -> str:
    if not items:
        return ""

    rows = "".join(
        f'<div class="risk-row">{r}</div>' for r in items
    )
    return (
        '<div class="section section-risks" id="risks">'
        '<div class="section-label">风险与阻碍</div>'
        + rows
        + "</div>"
    )


def build_markdown(data: dict) -> str:
    """Generate standard Markdown from meeting summary JSON."""
    lines = []
    title = data.get("title", "会议纪要")
    date = data.get("date", "")
    duration = data.get("duration", "")
    raw_p = data.get("participants", [])
    if isinstance(raw_p, list):
        participants = "、".join(str(p) for p in raw_p)
    else:
        participants = str(raw_p)

    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"📅 {date} · ⏱ {duration} · 👥 {participants}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Mindmap — markmap code block (Obsidian/markmap renderers render as horizontal tree)
    mindmap = data.get("mindmap", "")
    if mindmap:
        lines.append("## 🗺 思维导图")
        lines.append("")
        lines.append("```markmap")
        lines.append(mindmap.strip())
        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Summary
    summary = data.get("summary", [])
    if summary:
        lines.append("## 📋 议题摘要")
        lines.append("")
        for i, item in enumerate(summary, 1):
            lines.append(f"### {i:02d} · {item.get('topic', '')}")
            lines.append("")
            lines.append(item.get("content", ""))
            lines.append("")
        lines.append("---")
        lines.append("")

    # Decisions
    decisions = data.get("decisions", [])
    if decisions:
        lines.append("## ✅ 关键决策")
        lines.append("")
        for idx, item in enumerate(decisions):
            content = item.get("content", "")
            owner = item.get("owner", "")
            ts = item.get("timestamp", "")
            if idx > 0:
                lines.append('<hr style="border:none;border-top:1px solid #e8e8e8;margin:8px 0;">')
                lines.append("")
            lines.append(f"**{content}**")
            meta = []
            if owner:
                meta.append(f"负责人：{owner}")
            if ts:
                meta.append(f"时间：[{ts}]")
            if meta:
                lines.append(f'<span style="color:#aaa;font-size:0.85em;">{" ｜ ".join(meta)}</span>')
            lines.append("")
        lines.append("---")
        lines.append("")

    # Todos
    todos = data.get("todos", [])
    if todos:
        lines.append("## 📌 待办事项")
        lines.append("")
        priority_order = {"high": 0, "medium": 1, "low": 2}
        group_label_map = {"high": "🔴 高优先级", "medium": "🟡 中优先级", "low": "⚪ 低优先级"}
        sorted_todos = sorted(todos, key=lambda x: priority_order.get(x.get("priority", "low"), 2))
        current_p = None
        grp_idx = 0
        for item in sorted_todos:
            p = item.get("priority", "low")
            if p not in priority_order:
                p = "low"
            if p != current_p:
                current_p = p
                grp_idx = 0
                lines.append(f"**{group_label_map[p]}**")
                lines.append("")
            else:
                lines.append('<hr style="border:none;border-top:1px solid #e8e8e8;margin:8px 0;">')
                lines.append("")
            grp_idx += 1
            task = item.get("task", "").replace("|", "｜")
            owner = (item.get("owner", "") or "TBD").replace("|", "｜")
            deadline = (item.get("due") or item.get("deadline", "") or "待定").replace("|", "｜")
            lines.append(f"- [ ] **{task}**")
            lines.append(f'<span style="color:#aaa;font-size:0.85em;">负责人：{owner} ｜ 截止：{deadline}</span>')
            lines.append("")
        lines.append("---")
        lines.append("")

    # Risks
    risks = data.get("risks", [])
    if risks:
        lines.append("## ⚠️ 风险与阻碍")
        lines.append("")
        for i, item in enumerate(risks, 1):
            content = item if isinstance(item, str) else item.get("content", str(item))
            lines.append(f"**{i:02d}. {content}**")
            lines.append("")
        lines.append("")

    return "\n".join(lines)


def _yaml_quote(value: str) -> str:
    """Quote a string safely for YAML frontmatter; avoid unnecessary quotes if safe."""
    v = (value or "").strip()
    # If the value is empty, return quoted empty string.
    if not v:
        return '""'
    # If it contains special YAML characters, quote it and escape inner quotes.
    if re.search(r'[\"\'\n\r:#\{\}\[\],&*!?]|^(true|false|yes|no|on|off|null|~|\d{4}-\d{2}-\d{2}|\d+)$', v, re.IGNORECASE):
        escaped = v.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'
    return v


def _build_obsidian_markdown(data: dict, markdown_body: str) -> str:
    title = str(data.get("title", "会议纪要")).strip()
    date = str(data.get("date", "")).strip()
    duration = str(data.get("duration", "")).strip()
    participants = data.get("participants", [])

    if isinstance(participants, str):
        participants = [p.strip() for p in re.split(r"[、,，]", participants) if p.strip()]

    lines = [
        "---",
        f"title: {_yaml_quote(title)}",
        f"date: {_yaml_quote(date)}",
        f"duration: {_yaml_quote(duration)}",
        "participants:",
    ]
    for p in participants or []:
        lines.append(f"  - {_yaml_quote(str(p))}")

    lines.extend(
        [
            "tags:",
            "  - 会议纪要",
            "  - meeting-summary",
            "  - obsidian",
            "---",
            "",
            markdown_body.lstrip(),
        ]
    )
    return "\n".join(lines)


def sync_markdown_to_obsidian(md_output_path: Path, data: dict, html_output_path: Path | None = None) -> tuple[bool, str]:
    vault_path = os.getenv("OBSIDIAN_VAULT_PATH", "").strip()
    if not vault_path:
        return False, "OBSIDIAN_VAULT_PATH not set"

    meetings_dir = os.getenv("OBSIDIAN_MEETINGS_DIR", "Meetings").strip() or "Meetings"
    remote_host = os.getenv("OBSIDIAN_REMOTE_HOST", "macbook-jump").strip() or "macbook-jump"
    remote_vault = os.getenv("OBSIDIAN_REMOTE_VAULT_PATH", vault_path).strip() or vault_path

    title = str(data.get("title", "会议纪要")).strip() or "会议纪要"
    date = str(data.get("date", "")).strip() or datetime.now().strftime("%Y-%m-%d")
    safe_title = re.sub(r"[\\/:*?\"<>|]+", "-", title).strip()[:80] or "会议纪要"
    base_name = f"{date}-{safe_title}"

    md_body = md_output_path.read_text(encoding="utf-8")
    obsidian_md = _build_obsidian_markdown(data, md_body)
    html_body = html_output_path.read_bytes() if html_output_path and html_output_path.exists() else None

    # --- local write attempt (每次会议存入独立子文件夹) ---
    meeting_dir = Path(vault_path) / meetings_dir / base_name
    local_md = meeting_dir / f"{base_name}.md"
    local_html = meeting_dir / f"{base_name}.html" if html_body else None
    try:
        meeting_dir.mkdir(parents=True, exist_ok=True)
        local_md.write_text(obsidian_md, encoding="utf-8")
        if local_html and html_body:
            local_html.write_bytes(html_body)
        return True, f"local:{local_md}"
    except OSError as e:
        if getattr(e, "errno", None) not in (11, 35):
            return False, f"local write failed: {e}"

    # --- remote SSH fallback ---
    remote_md = f"{remote_vault.rstrip('/')}/{meetings_dir}/{base_name}/{base_name}.md"
    remote_html = f"{remote_vault.rstrip('/')}/{meetings_dir}/{base_name}/{base_name}.html" if html_body else None
    # Send payload via stdin to avoid oversized SSH command strings when HTML is large.
    html_payload = base64.b64encode(html_body).decode("ascii") if html_body else None
    remote_payload = {
        "md_target": remote_md,
        "md_text": obsidian_md,
        "html_target": remote_html,
        "html_b64": html_payload,
    }

    remote_py = (
        "python3 -c 'from pathlib import Path;import base64,json,sys;"
        "payload=json.loads(sys.stdin.read());"
        "target=Path(payload[\"md_target\"]);"
        "target.parent.mkdir(parents=True,exist_ok=True);"
        "target.write_text(payload[\"md_text\"],encoding=\"utf-8\");"
        "html_target=payload.get(\"html_target\");"
        "html_b64=payload.get(\"html_b64\");"
        "(Path(html_target).write_bytes(base64.b64decode(html_b64)) if html_target and html_b64 else None);"
        "print(target)'"
    )
    try:
        res = subprocess.run(
            ["ssh", remote_host, remote_py],
            input=json.dumps(remote_payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if res.returncode == 0:
            return True, f"remote:{res.stdout.strip()}"
        return False, f"remote write failed: {res.stderr.strip() or res.stdout.strip()}"
    except Exception as e:  # noqa: BLE001
        return False, f"remote sync exception: {e}"


def sync_todos_to_reminders(data: dict) -> None:
    """将待办事项同步到 Apple Reminders「会议待办」iCloud 列表
    使用 icloud-reminder-add CLI，强制写入 iCloud source（sourceType == .calDAV），
    避免命中本地同名列表。
    """
    import subprocess
    from datetime import datetime, timedelta

    action_items = data.get("action_items", data.get("todos", []))
    if not action_items:
        return

    # 检查 icloud-reminder-add 是否可用
    cli = "icloud-reminder-add"
    check = subprocess.run(["which", cli], capture_output=True, text=True)
    if check.returncode != 0:
        print(f"[reminders] 跳过：{cli} 未安装")
        return

    # 按优先级排序：high first
    priority_order = {"high": 0, "medium": 1, "low": 2}
    sorted_items = sorted(action_items, key=lambda x: priority_order.get(x.get("priority", "medium"), 1))

    base_date = datetime.now() + timedelta(days=1)
    results = []
    for i, item in enumerate(sorted_items):
        task = item.get("task", "").strip()
        if not task:
            continue
        owner = item.get("owner", "")
        deadline = item.get("due", item.get("deadline", ""))
        priority = item.get("priority", "medium")

        # 截止时间：deadline 有值就用，否则从明天起每天一条
        if deadline and deadline not in ("待定", "TBD", ""):
            due_str = deadline
        else:
            due_date = base_date + timedelta(days=i)
            due_str = due_date.strftime("%Y-%m-%d 09:00")

        # 标题加优先级前缀
        prefix = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(priority, "🟡")
        title = f"{prefix} {task}"
        if owner:
            title += f"（{owner}）"

        cmd = [cli, "--title", title, "--list", "会议待办", "--due", due_str, "--priority", priority]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        ok = result.returncode == 0
        results.append(f"{'✅' if ok else '❌'} {task[:30]}")
        if not ok and result.stderr:
            print(f"  [warn] {result.stderr.strip()}")

    print(f"[reminders] 同步完成（iCloud）：{len(results)} 条")
    for r in results:
        print(f"  {r}")


def main():
    parser = argparse.ArgumentParser(description="Generate meeting HTML report from JSON.")
    parser.add_argument("--json", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    data = json.loads(Path(args.json).read_text(encoding="utf-8"))

    title = data.get("title", "会议报告")
    date = data.get("date", "")
    duration = data.get("duration", "")
    participants = "、".join(data.get("participants", []))
    tags = data.get("tags", [])
    if tags:
        pills = " ".join(f'<span class="owner-pill">#{t}</span>' for t in tags)
        tags_html = f'<div class="cover-meta-item" style="grid-column: 1 / -1;"><span class="cover-meta-label">标签：</span><span>{pills}</span></div>'
    else:
        tags_html = ""
    mindmap_md = data.get("mindmap", f"# {title}")

    html = HTML_TEMPLATE.format(
        title=title,
        date=date,
        duration=duration,
        participants=participants,
        tags_html=tags_html,
        mindmap_html=build_mindmap(mindmap_md),
        summary_section=build_summary(data.get("summary", [])),
        decisions_section=build_decisions(data.get("decisions", [])),
        todos_section=build_todos(data.get("todos", [])),
        risks_section=build_risks(data.get("risks", [])),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    output_path = Path(args.output)
    output_path.write_text(html, encoding="utf-8")
    print(f"✅ Report saved: {output_path}")

    md_output_path = output_path.with_suffix(".md")
    md_output_path.write_text(build_markdown(data), encoding="utf-8")
    print(f"Markdown: {md_output_path}")

    synced, msg = sync_markdown_to_obsidian(md_output_path, data, html_output_path=output_path)
    status = "✅" if synced else "⚠️"
    print(f"{status} Obsidian sync: {msg}")

    sync_todos_to_reminders(data)


if __name__ == "__main__":
    main()
