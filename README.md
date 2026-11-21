# inference-digest

A daily inference engineering digest for one reader: serving engines, kernels, speculative decoding, KV-cache
work, quantization, new papers, and the occasional big provider, model or hardware story. It is short on
purpose: a few items on a good day, nothing on a quiet one. Each item is a one or two sentence summary, a
word-for-word quote, and a link to the source.

## How it works

1. **Collect** (first step of the Claude routine, daily). `digest/collect.py` fetches every source in
   `sources.json`, applies each source's keyword filter, and keeps what it has not seen before. It writes
   `data/candidates/<date>.json` and article text in `data/texts/` for this run, and the routine commits
   `data/seen.json` so nothing is offered twice. Candidates and texts are not committed: the repo is public.
2. **Edit** (same routine). Follows `ROUTINE.md`: reads the candidates, `preferences.md` and the reader's past
   feedback, picks at most five items, and writes summaries and quotes.
3. **Check.** `digest/verify.py` rejects the digest unless every quote is word for word in the source text and
   every link is exactly the collected one.
4. **Send.** `digest/render.py` builds the email and the routine sends it through Gmail. With no items, nothing
   is sent.

## Steering it

- **Reply to a digest email** in plain words: "2 wasn't worth it", "more like 1", "missed: <link>". The next
  run reads replies from the last 45 days.
- **Edit `preferences.md`** for standing rules about what counts as noteworthy.
- **Edit `sources.json`** to add or drop a source. `feed` is RSS or Atom (GitHub releases have one at
  `github.com/<owner>/<repo>/releases.atom`). `links` is a page with no feed: every link matching `pattern`
  is an item. On a page's first visit, the posts already listed are reported only if their own
  pages date them inside the window; the rest are recorded as seen. `hn` is Hacker News
  stories above `min_points`.
- **Filters.** Busy sources take `match_title` (a regex the title must match) or `match` (a regex the title or
  the first 3,000 characters of text must match). Both are case-insensitive. `"@name"` refers to a regex in
  the `filters` section at the top of `sources.json`, so one list of inference keywords serves many sources.

## Running it by hand

```bash
python3 digest/collect.py --dry-run       # fetch everything, print what is new, change nothing
python3 digest/collect.py                 # write today's candidates
python3 digest/verify.py work/digest.json
python3 digest/render.py work/digest.json
python3 tests/test_digest.py
```

Python standard library only.

## Layout

```
ROUTINE.md        the editor's instructions
preferences.md    what counts as noteworthy
sources.json      where to look, and the keyword filters for busy sources
digest/           collect.py, verify.py, render.py
data/seen.json    every item already offered
tests/
```

X/Twitter has no free feed, so it is not a source. The editor may run a few web searches each day to catch
what the sources miss.
