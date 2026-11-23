"""Collect recent, not-yet-proposed items from the feeds listed in sources.md."""

import argparse
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.request import Request, urlopen

ATOM = "{http://www.w3.org/2005/Atom}"
RSS1 = "{http://purl.org/rss/1.0/}"
DC = "{http://purl.org/dc/elements/1.1/}"
URL_RE = re.compile(r"https?://[^\s)>\]]+")
# YYYY-MM-DD-HHMM.md, so a second run on the same day never overwrites the first; older
# digests are named YYYY-MM-DD.md.
DIGEST_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:-\d{4})?\.md$")
DIGEST_ITEM_RE = re.compile(r"^## \d+\. \[(.+)\]\(", re.MULTILINE)
MAX_ITEMS_PER_FEED = 15
MIN_WINDOW = timedelta(hours=36)
MAX_WINDOW = timedelta(days=7)
COVERED_WINDOW = timedelta(days=14)


@dataclass
class Item:
    category: str
    source: str
    title: str
    url: str
    published: str
    summary: str


def read_sources(path: Path) -> list[tuple[str, str]]:
    """Return (category, url) pairs: each `- <url>` line under its `## <category>` heading."""
    sources, category = [], ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            category = line[3:].strip()
        elif line.lstrip().startswith("- ") and (match := URL_RE.search(line)):
            sources.append((category, match.group()))
    return sources


def parse_date(text: str | None) -> datetime | None:
    if not text:
        return None
    text = text.strip()
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def clean_text(text: str | None, limit: int = 400) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def _first_text(element: ET.Element, *tags: str) -> str | None:
    for tag in tags:
        value = element.findtext(tag)
        if value and value.strip():
            return value
    return None


def _atom_link(entry: ET.Element) -> str | None:
    for link in entry.findall(ATOM + "link"):
        if link.get("rel", "alternate") == "alternate":
            return link.get("href")
    return None


def parse_feed(content: bytes, category: str) -> list[tuple[datetime | None, Item]]:
    # ElementTree resolves no external entity and Python's expat caps entity
    # expansion, so parsing untrusted feeds is safe enough here.
    root = ET.fromstring(content)
    if root.tag == ATOM + "feed":
        source = _first_text(root, ATOM + "title") or ""
        entries = [
            (
                e,
                _first_text(e, ATOM + "title"),
                _atom_link(e),
                _first_text(e, ATOM + "published", ATOM + "updated"),
                _first_text(e, ATOM + "summary", ATOM + "content"),
            )
            for e in root.findall(ATOM + "entry")
        ]
    else:
        ns = RSS1 if root.find(RSS1 + "channel") is not None else ""
        channel = root.find(ns + "channel")
        source = _first_text(channel, ns + "title") if channel is not None else ""
        items = channel.findall("item") if ns == "" and channel is not None else root.findall(ns + "item")
        entries = [
            (
                i,
                _first_text(i, ns + "title"),
                _first_text(i, ns + "link"),
                _first_text(i, "pubDate", DC + "date"),
                _first_text(i, ns + "description"),
            )
            for i in items
        ]
    result = []
    for _, title, link, date_text, summary in entries:
        if not link:
            continue
        date = parse_date(date_text)
        item = Item(
            category=category,
            source=clean_text(source, 80),
            title=clean_text(title, 200),
            url=link.strip(),
            published=date.isoformat() if date else "",
            summary=clean_text(summary),
        )
        result.append((date, item))
    return result


def seen_urls(digests: Path) -> set[str]:
    return {url for file in digests.glob("*.md") for url in URL_RE.findall(file.read_text(encoding="utf-8"))}


def _dated_digests(digests: Path) -> list[tuple[datetime, Path]]:
    return [
        (datetime.fromisoformat(m.group(1)).replace(tzinfo=UTC), f)
        for f in digests.glob("*.md")
        if (m := DIGEST_NAME_RE.match(f.name))
    ]


def covered_stories(digests: Path, now: datetime) -> list[str]:
    """Titles of recent digest items: the same story comes back under other URLs, which URL
    dedup cannot catch, so the prompt compares titles instead."""
    return [
        title
        for day, file in sorted(_dated_digests(digests))
        if now - day <= COVERED_WINDOW
        for title in DIGEST_ITEM_RE.findall(file.read_text(encoding="utf-8"))
    ]


def window_start(digests: Path, now: datetime) -> datetime:
    """Cover everything since the last digest, so days without a run are not lost."""
    dates = [day for day, _ in _dated_digests(digests)]
    gap = now - max(dates) if dates else MIN_WINDOW
    return now - min(max(gap, MIN_WINDOW), MAX_WINDOW)


def download(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "techwatch-feed-reader/0.1"})
    with urlopen(request, timeout=20) as response:
        return response.read()


def fetch_one(category: str, url: str) -> tuple[str, list[tuple[datetime | None, Item]] | Exception]:
    try:
        return url, parse_feed(download(url), category)
    except Exception as error:  # one broken feed must not stop the others
        return url, error


def fetch_all(sources: list[tuple[str, str]]):
    with ThreadPoolExecutor(max_workers=16) as pool:
        return list(pool.map(lambda s: fetch_one(*s), sources))


def collect(sources_file: Path, digests: Path, now: datetime, since: datetime | None = None) -> dict:
    since = since or window_start(digests, now)
    seen = seen_urls(digests)
    items, failures, scanned = [], [], 0
    for url, result in fetch_all(read_sources(sources_file)):
        if isinstance(result, Exception):
            failures.append({"url": url, "error": f"{type(result).__name__}: {result}"[:200]})
            continue
        recent = sorted(
            ((date, item) for date, item in result if date and date >= since and item.url not in seen),
            key=lambda pair: pair[0],
            reverse=True,
        )[:MAX_ITEMS_PER_FEED]
        scanned += 1
        items.extend(asdict(item) for _, item in recent)
    return {
        "since": since.isoformat(),
        "feeds_ok": scanned,
        "feeds_failed": failures,
        "covered_stories": covered_stories(digests, now),
        "digest": str(digests / f"{now.astimezone():%Y-%m-%d-%H%M}.md"),
        "items": sorted(items, key=lambda i: (i["category"], i["published"])),
    }


def check(sources_file: Path) -> int:
    """Print the health of every feed: item count and newest date."""
    failed = 0
    for url, result in fetch_all(read_sources(sources_file)):
        if isinstance(result, Exception):
            failed += 1
            print(f"FAIL {url}  {type(result).__name__}: {result}"[:200])
        else:
            dates = [d for d, _ in result if d]
            newest = max(dates).date().isoformat() if dates else "no date"
            print(f"ok   {len(result):3d} items, newest {newest}  {url}")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=Path("sources.md"))
    parser.add_argument("--digests", type=Path, default=Path("digests"))
    parser.add_argument("--since", type=date.fromisoformat, help="collect from this date (YYYY-MM-DD) on")
    parser.add_argument("--check", action="store_true", help="report the health of each feed and exit")
    args = parser.parse_args()
    if args.check:
        return check(args.sources)
    since = datetime.combine(args.since, datetime.min.time(), UTC) if args.since else None
    json.dump(collect(args.sources, args.digests, datetime.now(UTC), since), sys.stdout, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
