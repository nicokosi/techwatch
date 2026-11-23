# Agent instructions for TechWatch

Read this before changing anything. It applies to every coding agent and to humans alike.
`CLAUDE.md` only imports this file.

## What this project is

A personal daily tech watch. A script collects the recent items of the feeds listed in
`sources.md`; Claude Code filters them against `profil.md` and writes a digest of 5 to 10
items in `digests/YYYY-MM-DD-HHMM.md`, which `scripts/daily.sh` commits.

Base branch: `main`.

## Setup and commands

```sh
mise install            # python and uv
mise run install        # dependencies (dev tools only; the fetcher uses the stdlib)

mise run check          # lint + format + types + tests  <- green before any commit
mise run fix            # auto-format and auto-fix lint
mise run sources        # health of every feed: item count, newest date, failures
mise run veille         # write, commit and push a new digest (needs network and claude)
mise run install-timer  # install the systemd user timer (08:00, catches up after boot)
claude "/veille 2026-11-15"  # interactive digest since that date, then asks whether to keep it
claude "/veille monitoring Java"  # the same, ranking first what matches this focus
```

Run one test: `uv run pytest tests/test_fetch.py -k atom`. Tests need no network.

## Layout

```
sources.md                  feeds, one `- <url>` per line under a `## <category>`
profil.md                   the filter: interests, stack, exclusions (French)
reactions.jsonl             👍/👎 on digest items, last vote per URL wins (absent until a vote)
digests/                    one file per run (French), written by `/veille`
src/techwatch/fetch.py      feed collection: window since last digest, dedup by URL
src/techwatch/reactions.py  records a vote (`techwatch-react`), reads the votes back
src/techwatch/stack.py      which repositories use a library, image or runtime (`techwatch-stack`)
.claude/commands/veille.md  the prompt that turns collected items into a digest
.claude/commands/profil.md  proposes profil.md edits from the votes
.claude/settings.json       permissions that let `claude -p` run unattended
scripts/daily.sh            runs `/veille --unattended` headless, then keeps the digest
scripts/keep.sh             commits and pushes one digest (daily.sh, and /veille on request)
deploy/systemd/             user service and timer
herdr/techwatch/            Herdr mod: browse digests, start a run
```

A URL that appears in any digest is never proposed again: `fetch.py` reads them back. The
same story under another URL is caught by `/veille`, which compares against the titles of
the last 14 days of digests (`covered_stories`).
Renaming or rewriting old digests therefore changes what gets proposed.

## Conventions

- **Language**: code, comments, commit messages and docs in English; `profil.md` and
  digests are in French, the reader's language.
- **Comments** explain the *why*, never the *what*.
- **Fetcher**: standard library only, so the daily job has no dependency to break.
- **Commits**: `<gitmoji> <type>(<scope>): <imperative subject>`, one theme per commit,
  `mise run check` green. Digests: `📰 docs(digest): add digest of YYYY-MM-DD-HHMM`.

## Documentation

If documentation misled you (wrong command, dead path, missing pitfall), fix it in the same
commit: the smallest edit that would have prevented the mistake.

## Pitfalls we already paid for

- Some health sites (Healthcare IT News, MobiHealthNews, Digital Health) answer 403 to
  scripts; TICsanté and the ANS have no working RSS. Check a new feed with
  `mise run sources` before adding it.
- Reddit serves one anonymous RSS request per minute and per IP (429 beyond), and on
  2026-11-18 it began answering 404 to every anonymous feed. Reddit needs the official
  API with an OAuth app; do not work around the block.
