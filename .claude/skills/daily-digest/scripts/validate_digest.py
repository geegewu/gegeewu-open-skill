#!/usr/bin/env python3
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path


ACCOUNT_RE = re.compile(r"^###\s+@([A-Za-z0-9_]+)\b", re.MULTILINE)
HANDLE_ANYWHERE_RE = re.compile(r"@([A-Za-z0-9_]{2,})\b")
DATE_CN_FULL_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
DATE_CN_SHORT_RE = re.compile(r"(?<!\d)(\d{1,2})月(\d{1,2})日(?!\d)")


def parse_watchlist_handles(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return ACCOUNT_RE.findall(text)


def parse_digest_handles(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return set(HANDLE_ANYWHERE_RE.findall(text))


def check_date_mentions(path: Path, target_date: datetime.date) -> list[str]:
    text = path.read_text(encoding="utf-8")
    issues: list[str] = []

    for lineno, line in enumerate(text.splitlines(), start=1):
        # Focus on rows that typically contain tweet timestamps.
        if ("来源" not in line) and (not line.strip().startswith("|")):
            continue

        for m in DATE_CN_FULL_RE.finditer(line):
            y, mon, day = map(int, m.groups())
            if (y, mon, day) != (target_date.year, target_date.month, target_date.day):
                issues.append(
                    f"line {lineno}: found out-of-window date {y:04d}-{mon:02d}-{day:02d} in '{line.strip()}'"
                )

        for m in DATE_CN_SHORT_RE.finditer(line):
            mon, day = map(int, m.groups())
            if (mon, day) != (target_date.month, target_date.day):
                issues.append(
                    f"line {lineno}: found out-of-window date {target_date.year:04d}-{mon:02d}-{day:02d} in '{line.strip()}'"
                )

        if "小时前" in line or "分钟前" in line:
            issues.append(
                f"line {lineno}: relative time marker found ('{line.strip()}'), should normalize to absolute target date"
            )

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate AI digest date window and account coverage.")
    parser.add_argument("--digest", required=True, help="Digest markdown path")
    parser.add_argument("--watchlist", required=True, help="Watchlist markdown path")
    parser.add_argument("--target-date", required=True, help="Expected date in YYYY-MM-DD (yesterday)")
    args = parser.parse_args()

    digest_path = Path(args.digest)
    watchlist_path = Path(args.watchlist)
    target_date = datetime.strptime(args.target_date, "%Y-%m-%d").date()

    if not digest_path.exists():
        print(f"VALIDATION_FAILED: digest not found: {digest_path}")
        return 2
    if not watchlist_path.exists():
        print(f"VALIDATION_FAILED: watchlist not found: {watchlist_path}")
        return 2

    watchlist_handles = parse_watchlist_handles(watchlist_path)
    digest_handles = parse_digest_handles(digest_path)

    date_issues = check_date_mentions(digest_path, target_date)

    # Account coverage: info only (accounts with 0 tweets won't appear in digest — that's normal)
    covered = len([h for h in watchlist_handles if h in digest_handles])
    failed = False

    if date_issues:
        failed = True
        print("VALIDATION_FAILED: out-of-window or non-normalized tweet timestamps")
        for msg in date_issues:
            print(f"- {msg}")

    if failed:
        return 1

    print("VALIDATION_OK")
    print(f"- target_date: {target_date.isoformat()}")
    print(f"- account_coverage: {covered}/{len(watchlist_handles)} accounts with content")
    return 0


if __name__ == "__main__":
    sys.exit(main())
