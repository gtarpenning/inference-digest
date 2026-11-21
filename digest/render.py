#!/usr/bin/env python3
"""render.py: turn a verified digest into the email.

  python3 digest/render.py work/digest.json

Writes work/subject.txt, work/email.html and work/email.txt. With no items it writes nothing and prints
EMPTY: on a day with nothing noteworthy, no email goes out.
"""
import html
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUBJECT = "Inference Digest"


def with_collector_stats(doc: dict, root: Path = ROOT) -> dict:
    """Take the footer's counts from the collector's file for that date, not from the editor's own tally."""
    f = root / "data" / "candidates" / f"{doc.get('date')}.json"
    if not f.exists():
        return doc
    day = json.loads(f.read_text())
    return {**doc, "considered": len(day.get("candidates", [])),
            "sources": [s["source"] for s in day.get("sources", [])],
            "sources_failed": [s["source"] for s in day.get("sources", []) if not s.get("ok")]}


def with_published(doc: dict, root: Path = ROOT) -> dict:
    """Give each item the collector's publication time, unless the editor already set one (e.g. an Exa find)."""
    by_id, by_url = {}, {}
    key = lambda u: str(u or "").split("#")[0].rstrip("/").replace("://www.", "://")
    for f in sorted((root / "data" / "candidates").glob("*.json")) if (root / "data" / "candidates").exists() else []:
        for c in json.loads(f.read_text()).get("candidates", []):
            by_id[c["id"]] = c.get("published")
            if c.get("published") and c.get("url") and c.get("source") != "Hacker News":   # HN's time is when it was posted there
                by_url.setdefault(key(c.get("url")), c["published"])
    items = [{**it, "published": it.get("published") or (it.get("url") and by_url.get(key(it["url"]))) or by_id.get(it.get("id"))}
             for it in doc.get("items", [])]
    return {**doc, "items": items}


OLD_AFTER_DAYS = 7


def age(days: int) -> str:
    return f"{days} days old" if days < 14 else f"{days // 7} weeks old" if days < 60 else f"{days // 30} months old"


def when(published, today: date) -> str:
    """'Tue Nov 17 · 14:49 UTC', or just 'Tue Nov 17' when the source gives a date with no time. '' if unknown.
    An article first published more than a week before the digest says so: 'Sat Oct 24 · 3 weeks old'."""
    if not published:
        return ""
    try:
        t = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
    except ValueError:
        return ""
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    date_only = (t.hour, t.minute, t.second) == (0, 0, 0)   # feeds that give a day, not a time
    if not date_only:
        t = t.astimezone(timezone.utc)
    out = f"{t:%a %b} {t.day}" + (f", {t.year}" if t.year != today.year else "")
    days = (today - t.date()).days
    if days > OLD_AFTER_DAYS:
        return f"{out} · {age(days)}"
    return out if date_only else f"{out} · {t:%H:%M} UTC"


def render(doc: dict):
    items = doc["items"]
    d = date.fromisoformat(doc["date"])
    day = f"{d:%a %b} {d.day}"
    subject = f"{SUBJECT} · {day} · {len(items)} item{'s' if len(items) != 1 else ''}"
    e = html.escape
    H = ['<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.5;'
         'color:#1a1a1a;max-width:640px">']
    T = []
    for n, it in enumerate(items, 1):
        by = " · ".join(x for x in (it["source"], it.get("author") or "") if x)
        stamp = when(it.get("published"), d)
        links = [("Source", it["url"])] + ([("Discussion", it["comments_url"])] if it.get("comments_url") else [])
        if stamp:
            H.append(f'<p style="margin:0 0 2px;color:#8a8a8a;font-size:12px;letter-spacing:0.02em">{e(stamp)}</p>')
        H.append(f'<p style="margin:0 0 4px"><b>{n}. <a href="{e(it["url"])}" style="color:#1a1a1a">{e(it["title"])}</a></b>'
                 f'<br><span style="color:#6b6b6b;font-size:13px">{e(by)}</span></p>')
        H.append(f'<p style="margin:0 0 6px">{e(it["summary"])}</p>')
        H.append(f'<blockquote style="margin:0 0 6px;padding:2px 0 2px 12px;border-left:3px solid #d9822b;color:#333">'
                 f'“{e(it["quote"])}”</blockquote>')
        H.append('<p style="margin:0 0 22px;font-size:13px">'
                 + " · ".join(f'<a href="{e(u)}">{e(t)}</a>' for t, u in links) + "</p>")
        T += [f"   {stamp}"] * bool(stamp) + [f"{n}. {it['title']}", f"   {by}", "", f"   {it['summary']}", "", f"   \"{it['quote']}\"", ""]
        T += [f"   {t}: {u}" for t, u in links] + [""]
    foot = []
    if doc.get("considered"):
        foot.append(f"Picked from {doc['considered']} new items.")
    if doc.get("sources_failed"):
        foot.append("Not checked today: " + ", ".join(doc["sources_failed"]) + ".")
    if doc.get("feedback_applied"):
        foot.append("Your feedback: " + doc["feedback_applied"])
    ask = ('Feedback is encouraged: it is what makes this report better. Reply with "2 wasn\'t worth it", '
           '"more like 1", or "missed: <link>".')
    H.append('<p style="margin:8px 0 0;padding-top:10px;border-top:1px solid #e5e5e5;color:#6b6b6b;font-size:12px">'
             + (e(" ".join(foot)) + "<br>" if foot else "") + e(ask) + "</p>")
    T += [" ".join(foot)] * bool(foot) + [ask]
    if doc.get("sources"):
        src = "Sources: " + ", ".join(doc["sources"]) + "."
        H.append(f'<p style="margin:6px 0 0;color:#8a8a8a;font-size:11px">{e(src)}</p>')
        T += ["", src]
    H.append("</div>")
    return subject, "\n".join(H), "\n".join(T)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    src = Path(sys.argv[1])
    doc = with_published(with_collector_stats(json.loads(src.read_text())))
    if not doc.get("items"):
        print("EMPTY")
        return
    subject, body_html, body_text = render(doc)
    out = src.parent
    (out / "subject.txt").write_text(subject + "\n")
    (out / "email.html").write_text(body_html + "\n")
    (out / "email.txt").write_text(body_text + "\n")
    print(subject)


if __name__ == "__main__":
    main()
