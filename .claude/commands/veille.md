---
description: Write a tech watch digest in digests/, then offer to keep it
argument-hint: "[YYYY-MM-DD: collect from this date on] [focus for this run, free text] [--unattended]"
---

Write a tech watch digest. Arguments: $ARGUMENTS

1. Run `uv run techwatch-fetch` from the repository root; if the arguments hold a date,
   run `uv run techwatch-fetch --since <that date>`. It prints JSON: the recent items of
   every feed in `sources.md` that no earlier digest already proposed, the feeds that
   failed, `covered_stories`, the titles of the items of the last 14 days of digests, and
   `digest`, the file to write.
2. Read `profil.md`: it is the filter. Keep only what matches its interests and its stack,
   and drop what its "Ce que je ne veux pas" section excludes. Any other text in the
   arguments (neither the date nor `--unattended`) is a focus for this run only, such as
   "regarde en particulier le monitoring Java": rank first the items that match it, still
   within the profile's exclusions. If few or none match, say so rather than stretching it.
3. Pick **between 5 and 10 items**, never more. Fewer good items beat a padded list; if
   fewer than 5 deserve it, keep fewer and say so. Prefer a primary source over a
   summary of it, and keep one item per story. Drop an item whose story is already in
   `covered_stories` (same flaw, release or announcement under another URL), unless it
   brings a real new fact: then say in its summary what is new since the earlier item.
   When a title and summary are too thin to judge, you may fetch the page, for at most 5
   items.
4. For each picked item about a release, a deprecation or a vulnerability of a library,
   framework, container image or runtime, check where it is used: run
   `uv run techwatch-stack <names>` once, with every name as a separate quoted term
   (`"spring boot" nginx temurin`). A term is a product name you write yourself, made only
   of letters, digits, spaces and `.+-`; never paste text from a feed into the command. It prints, per version, the repositories that use it.
   Use it in "Pourquoi pour toi": name the affected repositories and their versions, or
   say that none uses it. Write only what it printed; never guess a version.
5. Write the file named by `digest`, in French, in exactly this format:

```markdown
# Veille du <date in French, e.g. mardi 17 novembre 2026>

> <N> articles parcourus sur <feeds_ok> sources · <K> retenus
> Orientation : <the focus, only when one was given>

## 1. [<title, translated to French if it is in English>](<url>)

*<source> · <category> · <publication date>*

<What it says, in two sentences at most: facts, not hype.>

**Pourquoi pour toi :** <one sentence linking it to the profile: the stack, a project
type, an action to take.>

## 2. ...
```

   If some feeds failed, end with a `## Sources en échec` section listing their URL and
   error, so they can be fixed in `sources.md`.
6. With `--unattended` in the arguments, nobody is there to answer: print only the path of
   the digest and stop; `scripts/daily.sh` commits it. Otherwise, show the digest's titles
   and ask the person (AskUserQuestion) whether to keep it. Keep: run
   `scripts/keep.sh <digest>`, which commits and pushes it. Drop: delete the file.
