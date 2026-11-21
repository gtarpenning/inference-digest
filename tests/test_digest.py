import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "digest"))
import collect  # noqa: E402
import render  # noqa: E402
import verify  # noqa: E402

RSS = b"""<?xml version="1.0"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"
 xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><title>t</title>
<item><title>A &amp; B</title><link>https://www.lesswrong.com/posts/abcdefghij1234567/a-and-b?utm_source=x</link>
<pubDate>Sun, 15 Nov 2026 10:00:00 GMT</pubDate><dc:creator>Ann</dc:creator>
<content:encoded><![CDATA[<p>First para.</p><script>x()</script><p>Second &ldquo;para&rdquo;.</p>]]></content:encoded></item>
</channel></rss>"""
ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Atom post</title>
<link rel="alternate" href="https://example.org/p/1"/><published>2026-11-15T09:00:00Z</published>
<author><name>Bo</name></author><summary>Short.</summary></entry></feed>"""


class Collect(unittest.TestCase):
    def test_rss(self):
        (f,) = collect.parse_feed(RSS)
        self.assertEqual((f["title"], f["author"]), ("A & B", "Ann"))
        self.assertEqual(f["published"], datetime(2026, 11, 15, 10, tzinfo=timezone.utc))
        self.assertEqual(collect.to_text(f["html"]), "First para.\nSecond “para”.")

    def test_atom(self):
        (f,) = collect.parse_feed(ATOM)
        self.assertEqual((f["title"], f["url"], f["author"]), ("Atom post", "https://example.org/p/1", "Bo"))

    def test_one_arxiv_paper_is_one_key_across_versions_and_formats(self):
        a = collect.canon("https://arxiv.org/abs/2611.01234v2")
        self.assertEqual(a, collect.canon("https://www.arxiv.org/pdf/2611.01234"))
        self.assertEqual(a, "arxiv:2611.01234")

    def test_canon_strips_tracking_and_trailing_slash(self):
        self.assertEqual(collect.canon("https://www.Example.org/a/?utm_medium=y&id=3#frag"), "https://example.org/a?id=3")


class Filters(unittest.TestCase):
    """The keyword filters in the real sources.json."""
    @classmethod
    def setUpClass(cls):
        cls.src = {s["name"]: s for s in collect.load_sources(Path(collect.ROOT) / "sources.json")}

    def keeps(self, source, title, text=""):
        return collect.wanted(self.src[source], {"title": title, "text": text})

    def test_company_blog_titles(self):
        self.assertTrue(self.keeps("NVIDIA Technical Blog", "Co-Designing Sparse Attention for Efficient Long-Context Inference"))
        self.assertTrue(self.keeps("Hugging Face", "Speculative decoding with EAGLE-4 in Transformers"))
        self.assertFalse(self.keeps("NVIDIA Technical Blog", "Integrating QPUs into Supercomputing Centers Using Slurm HRES Plugins"))
        self.assertFalse(self.keeps("Google Research", "A game you cannot win unless you have a quantum computer"))

    def test_hacker_news_titles(self):
        self.assertTrue(self.keeps("Hacker News", "vLLM 0.26 makes KV-cache tiering the default"))
        self.assertTrue(self.keeps("Hacker News", "Running Kimi K3 at 400 tokens/s on a single node"))
        self.assertFalse(self.keeps("Hacker News", "Show HN: I built a paint mixer"))
        self.assertFalse(self.keeps("Hacker News", "The Linux kernel drops support for i486"))

    def test_arxiv_titles(self):
        self.assertTrue(self.keeps("arXiv", "EAGLE-4: Faster Speculative Decoding for Large Language Models"))
        self.assertTrue(self.keeps("arXiv", "Prefill-Decode Disaggregation for MoE Serving at Scale"))
        self.assertTrue(self.keeps("arXiv", "FP4 KV Cache Quantization with Negligible Accuracy Loss"))
        self.assertFalse(self.keeps("arXiv", "Variational Inference for Gaussian Process Models with Efficient Sparse Features"))
        self.assertFalse(self.keeps("arXiv", "Efficient Scheduling of Batch Jobs in Cloud Clusters"))
        self.assertFalse(self.keeps("arXiv", "Large Language Models as Moral Judges"))

    def test_only_minor_releases(self):
        for title in ("v0.26.0", "Dynamo v0.7.0", "v0.6"):
            self.assertTrue(self.keeps("vLLM releases", title), title)
        for title in ("v0.26.1", "v1.2.0rc3", "v0.5.23", "nightly"):
            self.assertFalse(self.keeps("vLLM releases", title), title)

    def test_named_and_inline_filters_and_match_on_text(self):
        f = Path(tempfile.mkdtemp()) / "sources.json"
        f.write_text(json.dumps({"filters": {"k": "kernel"}, "sources": [
            {"name": "A", "type": "feed", "url": "u", "match_title": "@k"},
            {"name": "B", "type": "feed", "url": "u", "match": "FP4"}]}))
        a, b = collect.load_sources(f)
        self.assertTrue(collect.wanted(a, {"title": "A new KERNEL", "text": ""}))
        self.assertFalse(collect.wanted(a, {"title": "Nothing", "text": "kernel"}))
        self.assertTrue(collect.wanted(b, {"title": "Nothing", "text": "an fp4 format"}))
        self.assertFalse(collect.wanted(b, {"title": "Nothing", "text": "x" * 3001 + "FP4"}))


class Pages(unittest.TestCase):
    def test_page_date_from_meta_json_ld_or_time(self):
        self.assertEqual(collect.page_date('<meta content="2026-11-19T08:00:00Z" property="article:published_time">'),
                         datetime(2026, 11, 19, 8, tzinfo=timezone.utc))
        self.assertEqual(collect.page_date('<script>{"@type":"BlogPosting","datePublished":"2026-11-18"}</script>'),
                         datetime(2026, 11, 18, tzinfo=timezone.utc))
        self.assertEqual(collect.page_date('<p>Posted <time datetime="2026-11-17">Nov 17</time></p>'),
                         datetime(2026, 11, 17, tzinfo=timezone.utc))
        self.assertIsNone(collect.page_date("<p>No date here</p>"))

    def test_links_from_anchors_and_from_embedded_json(self):
        src = {"name": "B", "url": "https://www.example.com/blog", "pattern": r"^https://www\.example\.com/blog/[a-z0-9-]+/?$"}
        real = collect.fetch
        try:
            collect.fetch = lambda url, timeout=30: (b"<a href='/blog/fast-decode'>Fast <b>decode</b></a>"
                                                     b'<a href="/about">About</a>')
            (it,) = collect.from_links(src, None)
            self.assertEqual((it["url"], it["title"]), ("https://www.example.com/blog/fast-decode", "Fast decode"))
            collect.fetch = lambda url, timeout=30: b'<script>{"posts":[{"href":"/blog/kv-tiering"},{"href":"/pricing"}]}</script>'
            (it,) = collect.from_links(src, None)
            self.assertEqual((it["url"], it["title"]), ("https://www.example.com/blog/kv-tiering", "kv tiering"))
        finally:
            collect.fetch = real

    def test_first_sight_of_a_page_reports_only_recent_articles(self):
        now = datetime(2026, 11, 21, 20, tzinfo=timezone.utc)
        recent = {"published": "2026-11-20T09:00:00+00:00"}
        old = {"published": "2026-09-01T00:00:00+00:00"}
        undated = {"published": None}
        self.assertTrue(collect.in_window(recent, now, False))
        self.assertFalse(collect.in_window(old, now, False))
        self.assertFalse(collect.in_window(undated, now, False))
        self.assertTrue(collect.in_window(undated, now, True))    # --no-baseline keeps undated ones

    def test_hacker_news_pages_through_results(self):
        calls, real = [], collect.fetch
        def fake(url, timeout=30):
            page = int(collect.urllib.parse.parse_qs(collect.urllib.parse.urlsplit(url).query)["page"][0])
            calls.append(page)
            hits = [{"objectID": f"{page}{i}", "title": "t", "points": 50, "created_at": "2026-11-20T00:00:00Z"} for i in range(2)]
            return json.dumps({"hits": hits, "nbPages": 3}).encode()
        try:
            collect.fetch = fake
            items = collect.from_hn({"name": "Hacker News", "min_points": 30}, datetime(2026, 11, 21, tzinfo=timezone.utc))
        finally:
            collect.fetch = real
        self.assertEqual(calls, [0, 1, 2])
        self.assertEqual(len(items), 6)


class Verify(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "data" / "texts").mkdir(parents=True)
        (self.root / "data" / "texts" / "x1.txt").write_text(
            "Intro. The monitor caught 93% of attacks at a 1% false positive rate — far above baseline. End.")
        self.item = {"id": "x1", "title": "T", "source": "S", "url": "https://example.org/t",
                     "summary": "A monitor result.", "quote": "The monitor caught 93% of attacks at a 1% false positive rate"}

    def test_verbatim_quote_passes_despite_spacing_and_dash_variants(self):
        self.item["quote"] += " - far above baseline."
        self.assertEqual(verify.check({"items": [self.item]}, self.root), [])

    def test_paraphrase_fails(self):
        self.item["quote"] = "The monitor caught nearly all attacks at a low false positive rate"
        self.assertIn("not word for word", verify.check({"items": [self.item]}, self.root)[0])

    def test_missing_text_fails(self):
        self.item["id"] = "nope"
        self.assertIn("no source text", verify.check({"items": [self.item]}, self.root)[0])

    def test_too_many_items_and_long_summary_fail(self):
        self.item["summary"] = "word " * 80
        errs = verify.check({"items": [dict(self.item, url=f"https://example.org/{i}") for i in range(6)]}, self.root)
        self.assertTrue(any("limit is 5" in e for e in errs) and any("summary is 80 words" in e for e in errs))

    def test_link_must_match_the_collected_link(self):
        (self.root / "data" / "candidates").mkdir()
        (self.root / "data" / "candidates" / "2026-11-15.json").write_text(json.dumps(
            {"candidates": [{"id": "x1", "url": "https://example.org/t-1", "comments_url": None}]}))
        self.assertIn("Use exactly https://example.org/t-1", verify.check({"items": [self.item]}, self.root)[0])
        self.item["url"] = "https://example.org/t-1"
        self.assertEqual(verify.check({"items": [self.item]}, self.root), [])

    def test_empty_digest_is_valid(self):
        self.assertEqual(verify.check({"items": []}, self.root), [])


class Render(unittest.TestCase):
    def test_subject_and_escaping(self):
        doc = {"date": "2026-11-15", "considered": 40, "items": [{
            "id": "x", "title": "A <b> title", "source": "LessWrong", "author": "Ann", "url": "https://example.org/a?x=1&y=2",
            "comments_url": None, "summary": "S.", "quote": "Q & A"}]}
        subject, body, text = render.render(doc)
        self.assertEqual(subject, "Inference Digest · Sun Nov 15 · 1 item")
        self.assertIn("A &lt;b&gt; title", body)
        self.assertIn("x=1&amp;y=2", body)
        self.assertIn("Picked from 40 new items.", text)
        self.assertIn("Feedback is encouraged", text)
        self.assertIn("Feedback is encouraged", body)
        self.assertNotIn("Sources:", text)

    def test_footer_lists_sources(self):
        doc = {"date": "2026-11-15", "sources": ["LessWrong", "Palisade Research"], "items": [{
            "id": "x", "title": "T", "source": "LessWrong", "url": "https://example.org/a", "summary": "S.", "quote": "Q"}]}
        _, body, text = render.render(doc)
        self.assertTrue(text.endswith("Sources: LessWrong, Palisade Research."))
        self.assertIn("Sources: LessWrong, Palisade Research.", body)
        self.assertTrue(body.endswith("</div>"))

    def test_footer_counts_come_from_the_collector(self):
        root = Path(tempfile.mkdtemp())
        (root / "data" / "candidates").mkdir(parents=True)
        (root / "data" / "candidates" / "2026-11-15.json").write_text(json.dumps({
            "candidates": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
            "sources": [{"source": "LessWrong", "ok": True}, {"source": "Import AI", "ok": False}]}))
        doc = render.with_collector_stats({"date": "2026-11-15", "considered": 36, "sources_failed": [], "items": []}, root)
        self.assertEqual(doc["considered"], 3)
        self.assertEqual(doc["sources_failed"], ["Import AI"])
        self.assertEqual(doc["sources"], ["LessWrong", "Import AI"])
        same = {"date": "2026-11-14", "considered": 7, "items": []}
        self.assertEqual(render.with_collector_stats(same, root), same)

    def test_publication_time_on_top_line(self):
        D = render.date(2026, 11, 17)
        self.assertEqual(render.when("2026-11-17T14:49:51+00:00", D), "Tue Nov 17 · 14:49 UTC")
        self.assertEqual(render.when("2026-11-17T19:08:45Z", D), "Tue Nov 17 · 19:08 UTC")
        self.assertEqual(render.when("2026-11-16T09:30:00-08:00", D), "Mon Nov 16 · 17:30 UTC")
        self.assertEqual(render.when("2026-11-16T00:00:00-08:00", D), "Mon Nov 16")   # date only: no fake time
        self.assertEqual(render.when("2025-12-31T00:00:00+00:00", D), "Wed Dec 31, 2025 · 10 months old")
        self.assertEqual(render.when("2026-10-24T23:57:07.505Z", D), "Sat Oct 24 · 3 weeks old")
        self.assertEqual(render.when("2026-11-08T12:00:00Z", D), "Sun Nov 8 · 9 days old")
        self.assertEqual(render.when("2026-11-10T12:00:00Z", D), "Tue Nov 10 · 12:00 UTC")
        self.assertEqual(render.when(None, D), "")
        self.assertEqual(render.when("not a date", D), "")
        doc = {"date": "2026-11-17", "items": [
            {"id": "a", "title": "T1", "source": "S", "url": "https://e.org/1", "summary": "S.", "quote": "Q",
             "published": "2026-11-17T14:49:51+00:00"},
            {"id": "b", "title": "T2", "source": "S", "url": "https://e.org/2", "summary": "S.", "quote": "Q"}]}
        _, body, text = render.render(doc)
        self.assertIn("   Tue Nov 17 · 14:49 UTC\n1. T1", text)
        self.assertIn("\n2. T2", text)
        self.assertLess(body.index("Tue Nov 17 · 14:49 UTC"), body.index("1. "))

    def test_publication_time_comes_from_the_collector(self):
        root = Path(tempfile.mkdtemp())
        (root / "data" / "candidates").mkdir(parents=True)
        (root / "data" / "candidates" / "2026-11-17.json").write_text(json.dumps({
            "candidates": [{"id": "a", "published": "2026-11-17T09:00:00+00:00"}, {"id": "b", "published": None}]}))
        doc = render.with_published({"items": [{"id": "a"}, {"id": "b"},
                                               {"id": "c", "published": "2026-11-17T10:00:00Z"}]}, root)
        self.assertEqual([i["published"] for i in doc["items"]], ["2026-11-17T09:00:00+00:00", None, "2026-11-17T10:00:00Z"])

    def test_publisher_time_beats_hacker_news_time(self):
        root = Path(tempfile.mkdtemp())
        (root / "data" / "candidates").mkdir(parents=True)
        (root / "data" / "candidates" / "2026-11-16.json").write_text(json.dumps({"candidates": [
            {"id": "feed", "source": "OpenAI", "url": "https://openai.com/index/post", "published": "2026-11-16T12:00:00+00:00"}]}))
        (root / "data" / "candidates" / "2026-11-17.json").write_text(json.dumps({"candidates": [
            {"id": "hn", "source": "Hacker News", "url": "https://openai.com/index/post/", "published": "2026-11-16T16:07:00Z"}]}))
        doc = render.with_published({"items": [{"id": "hn", "url": "https://openai.com/index/post/"}]}, root)
        self.assertEqual(doc["items"][0]["published"], "2026-11-16T12:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
