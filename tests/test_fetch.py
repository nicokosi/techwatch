from datetime import UTC, datetime, timedelta
from pathlib import Path

from techwatch.fetch import (
    clean_text,
    collect,
    covered_stories,
    parse_date,
    parse_feed,
    read_sources,
    seen_urls,
    window_start,
)

RSS2 = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Some Blog</title>
<item><title>Post &amp; more</title><link>https://ex.com/a</link>
<pubDate>Mon, 16 Nov 2026 08:00:00 GMT</pubDate>
<description>&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;/p&gt;</description></item>
<item><title>No link</title></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Releases</title>
<entry><title>v1.2.0</title><link rel="self" href="https://ex.com/self"/>
<link rel="alternate" href="https://ex.com/v1.2.0"/><updated>2026-11-16T10:00:00Z</updated>
<content type="html">Fixes</content></entry></feed>"""

RDF = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel><title>Old School</title></channel>
<item><title>Rdf post</title><link>https://ex.com/rdf</link><dc:date>2026-11-16</dc:date></item>
</rdf:RDF>"""


def test_parse_rss2_skips_items_without_link_and_strips_html():
    [(date, item)] = parse_feed(RSS2, "Java")
    assert (item.source, item.title, item.url, item.summary) == (
        "Some Blog",
        "Post & more",
        "https://ex.com/a",
        "Hello world",
    )
    assert date == datetime(2026, 11, 16, 8, tzinfo=UTC)


def test_parse_atom_uses_alternate_link():
    [(date, item)] = parse_feed(ATOM, "IA")
    assert (item.source, item.url, item.summary) == ("Releases", "https://ex.com/v1.2.0", "Fixes")
    assert date == datetime(2026, 11, 16, 10, tzinfo=UTC)


def test_parse_rss1_rdf():
    [(date, item)] = parse_feed(RDF, "Santé")
    assert (item.source, item.url) == ("Old School", "https://ex.com/rdf")
    assert date == datetime(2026, 11, 16, tzinfo=UTC)


def test_parse_date_rejects_garbage():
    assert parse_date("yesterday") is None
    assert parse_date(None) is None


def test_clean_text_truncates_on_word():
    assert clean_text("aaa bbb ccc", limit=6) == "aaa…"


def test_read_sources_keeps_category_and_ignores_prose(tmp_path: Path):
    file = tmp_path / "sources.md"
    file.write_text("Intro https://not-a-source.com\n## IA\n- https://a.com/feed  # A\n## Java\n- https://b.com/rss\n")
    assert read_sources(file) == [("IA", "https://a.com/feed"), ("Java", "https://b.com/rss")]


def test_seen_urls_and_window_from_last_digest(tmp_path: Path):
    (tmp_path / "2026-11-14.md").write_text("## [T](https://ex.com/a)\n")
    now = datetime(2026, 11, 17, 6, tzinfo=UTC)
    assert seen_urls(tmp_path) == {"https://ex.com/a"}
    assert window_start(tmp_path, now) == datetime(2026, 11, 14, tzinfo=UTC)


def test_window_is_at_least_36h_and_at_most_7_days(tmp_path: Path):
    now = datetime(2026, 11, 17, 6, tzinfo=UTC)
    assert window_start(tmp_path, now) == now - timedelta(hours=36)
    (tmp_path / "2026-01-01.md").write_text("")
    assert window_start(tmp_path, now) == now - timedelta(days=7)


def test_covered_stories_keeps_item_titles_of_the_last_14_days(tmp_path: Path):
    (tmp_path / "2026-11-01.md").write_text("## 1. [Too old](https://ex.com/o)\n")
    (tmp_path / "2026-11-16-0815.md").write_text(
        "# Veille\n## 1. [Faille [NGINX] HTTP/2](https://ex.com/n)\n## Sources en échec\n"
    )
    now = datetime(2026, 11, 17, 6, tzinfo=UTC)
    assert covered_stories(tmp_path, now) == ["Faille [NGINX] HTTP/2"]


def test_collect_names_the_digest_after_the_local_time(tmp_path: Path):
    (tmp_path / "sources.md").write_text("")
    now = datetime(2026, 11, 17, 6, 5, tzinfo=UTC)
    digest = collect(tmp_path / "sources.md", tmp_path, now)["digest"]
    assert digest == str(tmp_path / f"{now.astimezone():%Y-%m-%d-%H%M}.md")
