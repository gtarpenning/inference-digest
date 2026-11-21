#!/usr/bin/env python3
"""collect.py: fetch every source in sources.json and write today's new candidates.

  python3 digest/collect.py [--date YYYY-MM-DD] [--dry-run]

Writes data/candidates/<date>.json (items not seen before), data/texts/<id>.txt (article text where the
source gives it), and updates data/seen.json. Standard library only. Makes no judgment about relevance,
except cheap keyword filters on busy sources (arXiv, Hacker News, big company blogs): a source's
`match_title` must match its title and its `match` must match its title or text. A value starting with "@"
names a regex in the `filters` section of sources.json.
"""
import argparse
import gzip
import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
MAX_AGE_H = 72          # dated items older than this are ignored
TEXT_CAP = 12000        # characters of article text kept per item
EXCERPT = 400
KEEP_DAYS = 7           # candidates and texts older than this are pruned from the working tree
MATCH_TEXT = 3000       # characters of text, after the title, that `match` looks at


def fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/json, text/html;q=0.9, */*;q=0.5",
        "Accept-Language": "en-US,en;q=0.9"})
    for attempt in (1, 2, 3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read(8_000_000)
            return gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw   # some servers gzip unasked
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 * attempt)


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "header", "footer", "form", "button", "iframe"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "blockquote", "tr", "section", "article"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def to_text(markup: str) -> str:
    p = _Text()
    try:
        p.feed(markup)
    except Exception:
        return re.sub(r"<[^>]+>", " ", markup)
    t = "".join(p.out)
    t = re.sub(r"[ \t\r\f\v ]+", " ", t)
    return re.sub(r"\s*\n\s*", "\n", t).strip()


def item_id(key: str) -> str:
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def canon(url: str) -> str:
    u = urllib.parse.urlsplit(url.strip())
    q = [(k, v) for k, v in urllib.parse.parse_qsl(u.query) if not k.lower().startswith(("utm_", "ref"))]
    path = u.path.rstrip("/") or "/"
    m = re.match(r"^/(?:abs|pdf|html)/(\d{4}\.\d{4,5})(?:v\d+)?", path)   # one arXiv paper, any version or format
    if m and u.netloc.endswith("arxiv.org"):
        return "arxiv:" + m.group(1)
    return urllib.parse.urlunsplit((u.scheme, u.netloc.lower().removeprefix("www."), path, urllib.parse.urlencode(q), ""))


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_feed(raw: bytes) -> list[dict]:
    """RSS 2.0 and Atom. Returns dicts with title, url, author, published, html."""
    root = ET.fromstring(raw.lstrip())
    out = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        f = {"title": "", "url": "", "author": "", "published": None, "html": ""}
        best = ""
        for c in el:
            name, text = _local(c.tag), (c.text or "").strip()
            if name == "title":
                f["title"] = to_text(text)
            elif name == "link":
                href = c.attrib.get("href")
                if href and c.attrib.get("rel", "alternate") == "alternate":
                    f["url"] = href
                elif text and not f["url"]:
                    f["url"] = text
            elif name in ("pubdate", "published", "date") or (name == "updated" and not f["published"]):
                f["published"] = parse_date(text) or f["published"]
            elif name in ("creator", "author"):
                f["author"] = text or " ".join((x.text or "").strip() for x in c if _local(x.tag) == "name")
            elif name in ("encoded", "content", "description", "summary") and len(text) > len(best):
                best = text
        f["html"] = best
        if f["title"] and f["url"]:
            out.append(f)
    return out


def from_feed(src, now):
    items = []
    for f in parse_feed(fetch(src["url"])):
        if f["published"] and now - f["published"] > timedelta(hours=MAX_AGE_H):
            continue
        text = to_text(f["html"]) if f["html"] else ""
        items.append({"key": canon(f["url"]), "source": src["name"], "title": f["title"], "url": f["url"],
                      "author": f["author"], "published": f["published"].isoformat() if f["published"] else None,
                      "score": None, "comments_url": None, "text": text})
    return items


def from_hn(src, now):
    since = int((now - timedelta(hours=MAX_AGE_H)).timestamp())
    q = urllib.parse.urlencode({"tags": "story", "hitsPerPage": 300,
                                "numericFilters": f"created_at_i>{since},points>={src.get('min_points', 40)}"})
    hits = json.loads(fetch("https://hn.algolia.com/api/v1/search_by_date?" + q))["hits"]
    items = []
    for h in hits:
        title = h.get("title") or ""
        hn_url = f"https://news.ycombinator.com/item?id={h['objectID']}"
        items.append({"key": "hn:" + h["objectID"], "source": src["name"], "title": title, "url": h.get("url") or hn_url,
                      "author": h.get("author") or "", "published": h.get("created_at"), "score": h.get("points"),
                      "comments_url": hn_url, "text": to_text(h.get("story_text") or "")})
    return items


def from_links(src, now):
    """Pages with no feed: every link matching the pattern is an item. No dates, so 'new' means unseen."""
    page = fetch(src["url"]).decode("utf-8", "replace")
    pat, seen, items = re.compile(src["pattern"]), set(), []
    for m in re.finditer(r'<a\b[^>]*?href="([^"#?]+)[^"]*"[^>]*>(.*?)</a>', page, re.S | re.I):
        url = urllib.parse.urljoin(src["url"], html.unescape(m.group(1)))
        if not pat.match(url) or canon(url) in seen:
            continue
        seen.add(canon(url))
        title = to_text(m.group(2)).replace("\n", " · ")[:200]
        items.append({"key": canon(url), "source": src["name"], "title": title or url.rstrip("/").rsplit("/", 1)[-1],
                      "url": url, "author": "", "published": None, "score": None, "comments_url": None, "text": ""})
    return items


FETCHERS = {"feed": from_feed, "hn": from_hn, "links": from_links}


def load_sources(path: Path) -> list[dict]:
    """sources.json is {"filters": {name: regex}, "sources": [...]}. "@name" in a source's `match_title` or
    `match` stands for that named regex; anything else is a regex itself. Both are case-insensitive."""
    doc = json.loads(path.read_text())
    filters = doc.get("filters", {})
    out = []
    for src in doc["sources"]:
        src = dict(src)
        for k in ("match_title", "match"):
            v = src.get(k)
            if v:
                src[k] = re.compile(filters[v[1:]] if v.startswith("@") else v, re.I)
        out.append(src)
    return out


def wanted(src: dict, it: dict) -> bool:
    if src.get("match_title") and not src["match_title"].search(it["title"]):
        return False
    if src.get("match") and not src["match"].search(it["title"] + "\n" + it["text"][:MATCH_TEXT]):
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    ap.add_argument("--dry-run", action="store_true", help="print what would be written; change nothing")
    args = ap.parse_args()
    now = datetime.now(timezone.utc)
    sources = load_sources(ROOT / "sources.json")
    seen_p = DATA / "seen.json"
    seen = json.loads(seen_p.read_text()) if seen_p.exists() else {"items": {}, "baselined": []}

    status, new = [], []
    for i, src in enumerate(sources, 1):
        t0 = time.time()
        try:
            items = [it for it in FETCHERS[src["type"]](src, now) if wanted(src, it)]
        except Exception as e:
            status.append({"source": src["name"], "ok": False, "error": f"{type(e).__name__}: {e}"[:160]})
            print(f"[{i}/{len(sources)}] {src['name']}: FAILED {type(e).__name__}: {e}"[:200], flush=True)
            continue
        # A source with undated items is baselined on first sight: everything already there is old, not news.
        first_time = src["type"] == "links" and src["name"] not in seen["baselined"]
        fresh = [it for it in items if it["key"] not in seen["items"]]
        for it in fresh:
            seen["items"][it["key"]] = args.date
        if first_time:
            seen["baselined"].append(src["name"])
            fresh = []
        new += fresh
        status.append({"source": src["name"], "ok": True, "found": len(items), "new": len(fresh)})
        print(f"[{i}/{len(sources)}] {src['name']}: {len(items)} in window, {len(fresh)} new"
              f"{' (baseline)' if first_time else ''} ({time.time() - t0:.1f}s)", flush=True)

    # Undated pages give a title only: fetch the article so the editor has something to quote.
    for it in new:
        if not it["text"] and it["source"] != "Hacker News":
            try:
                it["text"] = to_text(fetch(it["url"]).decode("utf-8", "replace"))
            except Exception as e:
                print(f"  text fetch failed for {it['url']}: {e}"[:160], flush=True)

    # One story, one candidate: the same post often arrives from two sources.
    by_key, out = {}, []
    for it in new:
        k = canon(it["url"])
        if k in by_key:
            keep = by_key[k]
            keep["also"] = sorted(set(keep.get("also", []) + [it["source"]]))
            keep["score"] = keep["score"] or it["score"]
            keep["comments_url"] = keep["comments_url"] or it["comments_url"]
            keep["text"] = keep["text"] or it["text"]
            continue
        by_key[k] = it
        out.append(it)

    cands = []
    for it in out:
        iid, text = item_id(it["key"]), it.pop("text")
        it.pop("key")
        cands.append({"id": iid, **it, "excerpt": text[:EXCERPT].replace("\n", " "), "has_text": bool(text)})
        if text and not args.dry_run:
            (DATA / "texts").mkdir(parents=True, exist_ok=True)
            (DATA / "texts" / f"{iid}.txt").write_text(text[:TEXT_CAP])

    doc = {"date": args.date, "collected_at": now.isoformat(timespec="seconds"), "sources": status, "candidates": cands}
    failed = [s["source"] for s in status if not s["ok"]]
    print(f"{len(cands)} new candidates from {len(status) - len(failed)}/{len(status)} sources"
          f"{'; failed: ' + ', '.join(failed) if failed else ''}", flush=True)
    if args.dry_run:
        for c in cands:
            print(f"  {c['source'][:18]:18} {str(c['score'] or ''):>4} {c['title'][:90]}")
        return
    (DATA / "candidates").mkdir(parents=True, exist_ok=True)
    day = DATA / "candidates" / f"{args.date}.json"
    if day.exists():   # a second run on the same day adds to the first; it never replaces it
        doc["candidates"] = json.loads(day.read_text())["candidates"] + cands
    day.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    cutoff = (now - timedelta(days=120)).strftime("%Y-%m-%d")
    seen["items"] = {k: d for k, d in seen["items"].items() if d >= cutoff or not k.startswith(("hn:", "arxiv:"))}
    seen_p.write_text(json.dumps(seen, indent=0, sort_keys=True) + "\n")
    keep_from = (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    live = set()
    for p in sorted((DATA / "candidates").glob("*.json")):
        if p.stem < keep_from:
            p.unlink()
        else:
            live |= {c["id"] for c in json.loads(p.read_text())["candidates"]}
    for p in (DATA / "texts").glob("*.txt") if (DATA / "texts").exists() else []:
        if p.stem not in live:
            p.unlink()
    if len(failed) == len(status):
        sys.exit("every source failed")


if __name__ == "__main__":
    main()
