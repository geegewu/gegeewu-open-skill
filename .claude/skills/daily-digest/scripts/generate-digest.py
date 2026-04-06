#!/usr/bin/env python3
"""
Blog Digest Generator for HN Top 92 RSS feeds.
Scans all feeds, fetches article summaries, returns today's new articles as JSON.
"""
import os
import subprocess
import re
import json
import sys
import requests
from pathlib import Path
import concurrent.futures
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser

# HTTP headers for Cloudflare Markdown-for-Agents
HTTP_HEADERS = {
    'Accept': 'text/markdown, text/html',
    'User-Agent': 'Mozilla/5.0 (compatible; RSS-Digest-Bot/1.0)'
}


def run(cmd, timeout=900):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.stdout, result.stderr


def get_today():
    # Asia/Shanghai offset: UTC+8, return yesterday (digest runs next morning)
    tz = timezone(timedelta(hours=8))
    return (datetime.now(tz) - timedelta(days=1)).strftime('%Y-%m-%d')


def parse_articles(raw):
    articles = []
    current = {}
    for line in raw.split('\n'):
        stripped = line.strip()
        if not stripped:
            if current.get('id'):
                articles.append(current)
                current = {}
            continue
        m = re.match(r'\[(\d+)\]\s+\[([^\]]+)\]\s+(.*)', stripped)
        if m:
            if current.get('id'):
                articles.append(current)
            current = {'id': m.group(1), 'status': m.group(2), 'title': m.group(3)}
        elif stripped.startswith('Blog:'):
            current['blog'] = stripped[5:].strip()
        elif stripped.startswith('URL:'):
            current['url'] = stripped[4:].strip()
        elif stripped.startswith('Published:'):
            current['published'] = stripped[10:].strip()
    if current.get('id'):
        articles.append(current)
    return articles


class TextExtractor(HTMLParser):
    """Extract text content from HTML <p>, <article>, and <section> tags."""
    
    def __init__(self):
        super().__init__()
        self.texts = []
        self.in_tag = False
    
    def handle_starttag(self, tag, attrs):
        if tag in ('p', 'article', 'section'):
            self.in_tag = True
    
    def handle_endtag(self, tag):
        if tag in ('p', 'article', 'section'):
            self.in_tag = False
    
    def handle_data(self, data):
        if self.in_tag and data.strip():
            self.texts.append(data.strip())


def fetch_summary(url, max_chars=500):
    """Fetch article summary from URL using Markdown-for-Agents header."""
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=10)
        ct = resp.headers.get('content-type', '')
        
        # Record x-markdown-tokens if present (Cloudflare feature)
        md_tokens = resp.headers.get('x-markdown-tokens', None)
        
        if 'text/markdown' in ct:
            # Use markdown directly, skip HTML parsing
            text = resp.text.strip()
        else:
            # Parse HTML to extract text content
            parser = TextExtractor()
            parser.feed(resp.text)
            text = ' '.join(parser.texts)
        
        # Truncate to max_chars
        summary = text[:max_chars].strip()
        if len(text) > max_chars:
            summary += '...'
        
        return summary
    except Exception as e:
        print(f"Warning: Failed to fetch summary for {url}: {e}", file=sys.stderr)
        return ''


def fetch_summaries_concurrent(articles, max_workers=5):
    """Fetch summaries for all articles concurrently."""
    def fetch_for_article(article):
        url = article.get('url')
        if url:
            article['summary'] = fetch_summary(url)
        else:
            article['summary'] = ''
        return article
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        articles = list(executor.map(fetch_for_article, articles))
    
    return articles


if __name__ == '__main__':
    today = get_today()

    # Step 1: scan
    print(f"Scanning feeds for {today}...", file=sys.stderr)
    blogwatcher = os.environ.get("BLOGWATCHER_BIN", str(Path.home() / "go" / "bin" / "blogwatcher"))
    run([blogwatcher, 'scan', '--workers', '8'], timeout=900)

    # Step 2: get unread articles
    raw, _ = run([blogwatcher, 'articles'])
    all_articles = parse_articles(raw)

    # Step 3: filter today
    today_articles = [a for a in all_articles if a.get('published') == today]
    
    # Step 4: fetch summaries for today's articles (concurrent)
    if today_articles:
        print(f"Fetching summaries for {len(today_articles)} articles...", file=sys.stderr)
        today_articles = fetch_summaries_concurrent(today_articles)
    
    # Step 5: mark all read
    run([blogwatcher, 'read-all'])

    result = {
        'date': today,
        'total_unread': len(all_articles),
        'today_count': len(today_articles),
        'articles': today_articles
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
