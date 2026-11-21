#!/usr/bin/env python3
"""verify.py: refuse a digest that breaks the rules. Exit 0 only if every check passes.

  python3 digest/verify.py work/digest.json

The rule that matters most: every quote must appear word for word in the source text
(data/texts/<id>.txt from the collector, or work/texts/<id>.txt saved by the editor). Links to collected
items must match the collector's link exactly, so a link cannot be mistyped or invented.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_ITEMS, MAX_SUMMARY_WORDS, MAX_QUOTE_WORDS, MIN_QUOTE_WORDS = 5, 55, 70, 6
REQUIRED = ("id", "title", "source", "url", "summary", "quote")
_MAP = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
                      "−": "-", " ": " ", "…": "..."})


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.translate(_MAP)).strip()


def source_text(item_id: str, root: Path = ROOT):
    for p in (root / "work" / "texts" / f"{item_id}.txt", root / "data" / "texts" / f"{item_id}.txt"):
        if p.exists():
            return p.read_text(errors="replace")
    return None


def collected(root: Path = ROOT) -> dict:
    """id -> candidate, for every candidates file still in the tree."""
    out = {}
    for p in sorted((root / "data" / "candidates").glob("*.json")):
        out.update({c["id"]: c for c in json.loads(p.read_text())["candidates"]})
    return out


def check(doc: dict, root: Path = ROOT) -> list[str]:
    errs, items, known = [], doc.get("items"), collected(root)
    if not isinstance(items, list):
        return ["digest has no 'items' list"]
    if len(items) > MAX_ITEMS:
        errs.append(f"{len(items)} items; the limit is {MAX_ITEMS}. Cut the weakest.")
    urls = set()
    for n, it in enumerate(items, 1):
        tag = f"item {n} ({str(it.get('title', ''))[:40]!r})"
        missing = [k for k in REQUIRED if not str(it.get(k) or "").strip()]
        if missing:
            errs.append(f"{tag}: missing {', '.join(missing)}")
            continue
        if not re.match(r"^https?://\S+$", it["url"]):
            errs.append(f"{tag}: url is not a link")
        cand = known.get(it["id"])
        if cand and it["url"] != cand["url"]:
            errs.append(f"{tag}: url differs from the collected one. Use exactly {cand['url']}")
        if cand and it.get("comments_url") not in (None, "", cand.get("comments_url")):
            errs.append(f"{tag}: comments_url differs from the collected one")
        if it["url"] in urls:
            errs.append(f"{tag}: same url as an earlier item")
        urls.add(it["url"])
        if len(it["summary"].split()) > MAX_SUMMARY_WORDS:
            errs.append(f"{tag}: summary is {len(it['summary'].split())} words; the limit is {MAX_SUMMARY_WORDS}")
        qw = len(it["quote"].split())
        if not MIN_QUOTE_WORDS <= qw <= MAX_QUOTE_WORDS:
            errs.append(f"{tag}: quote is {qw} words; keep it between {MIN_QUOTE_WORDS} and {MAX_QUOTE_WORDS}")
        text = source_text(it["id"], root)
        if text is None:
            errs.append(f"{tag}: no source text at data/texts/{it['id']}.txt or work/texts/{it['id']}.txt; "
                        f"fetch the page and save its text before quoting")
        elif norm(it["quote"]) not in norm(text):
            errs.append(f"{tag}: quote is not word for word in the source text. Copy one contiguous passage; "
                        f"no ellipses, no paraphrase")
    return errs


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    errs = check(json.loads(Path(sys.argv[1]).read_text()))
    for e in errs:
        print("FAIL", e)
    if errs:
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()
