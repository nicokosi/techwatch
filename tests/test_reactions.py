import json
from pathlib import Path

from techwatch.reactions import record, votes


def test_the_last_vote_on_a_url_wins_and_zero_clears_it(tmp_path: Path):
    file = tmp_path / "reactions.jsonl"
    record(file, "https://ex.com/a", 1, title="A", day="2026-11-20")
    record(file, "https://ex.com/b", -1, title="B", day="2026-11-20")
    record(file, "https://ex.com/a", -1, title="A", day="2026-11-21")
    record(file, "https://ex.com/b", 0, title="B", day="2026-11-21")
    assert votes(file) == {"https://ex.com/a": -1}
    lines = [json.loads(line) for line in file.read_text().splitlines()]
    assert lines[0] == {"date": "2026-11-20", "url": "https://ex.com/a", "title": "A", "vote": 1}


def test_votes_of_a_missing_file_are_empty(tmp_path: Path):
    assert votes(tmp_path / "reactions.jsonl") == {}


def test_a_note_is_kept(tmp_path: Path):
    file = tmp_path / "reactions.jsonl"
    record(file, "https://ex.com/a", 1, title="A", note="exactement mon sujet", day="2026-11-20")
    assert json.loads(file.read_text())["note"] == "exactement mon sujet"


def test_a_broken_line_costs_one_vote_and_the_next_vote_starts_a_new_line(tmp_path: Path):
    file = tmp_path / "reactions.jsonl"
    file.write_text('{"url": "https://ex.com/a", "vote": 1}\nnot json')
    record(file, "https://ex.com/b", -1, day="2026-11-20")
    assert votes(file) == {"https://ex.com/a": 1, "https://ex.com/b": -1}
