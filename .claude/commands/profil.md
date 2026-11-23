---
description: Propose changes to profil.md from the 👍/👎 given to digest items
---

Adjust the watch profile to what the person liked and disliked.

1. Read `reactions.jsonl`: one vote per line, `{date, url, title, vote, note?}`. The last
   vote on a URL counts; 0 withdraws it. Without any vote, say so and stop.
2. For each voted URL, find its item in `digests/` (search for the URL) to see its
   category, source and summary.
3. Read `profil.md`, then look for patterns: themes, kinds of content (releases, opinion
   pieces, field reports, tutorials) or sources that keep getting the same vote. One vote
   is not a pattern: wait for about three, unless a note says it plainly. Skip what the
   profile already says.
4. Propose the smallest edits that would have produced these votes: an interest to add,
   sharpen or move up, an exclusion to add. Back each one with the votes behind it. A
   source that only gets 👎 is a suggestion for `sources.md`, not an edit.
5. Ask the person which edits to apply (AskUserQuestion, several answers allowed), and
   apply only those, in French like the rest of `profil.md`.
6. Commit `profil.md` and `reactions.jsonl` only, whatever else is staged
   (`git commit -m … -- profil.md reactions.jsonl`), message
   `🎯 docs(profil): adjust the profile to recent reactions`, with a body listing the
   applied edits, then push.
