import json
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from server import crawler


class CrawlerTests(unittest.TestCase):
    def test_softswiss_uses_full_rest_content(self):
        payload = [{
            "id": 42,
            "date": "2026-08-17T08:41:44",
            "link": "https://careers.softswiss.com/vacancies/test-role/",
            "title": {"rendered": "Test &amp; Role"},
            "content": {"rendered": "<h2>Overview</h2><p>Full description</p>"},
            "yoast_head_json": {"title": "Test Role Job - Vacancy in Poland & Remote | SOFTSWISS Careers"},
        }]
        with patch.object(crawler, "_fetch", return_value=json.dumps(payload)):
            jobs = crawler.crawl_softswiss()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company_name"], "SOFTSWISS")
        self.assertEqual(jobs[0]["location"], "Poland, Remote")
        self.assertIn("Full description", jobs[0]["description"])

    def test_jsonld_supports_graph(self):
        page = '''<script type="application/ld+json">{
          "@context":"https://schema.org", "@graph":[{
            "@type":"JobPosting", "title":"CRM Manager", "description":"<p>Complete role</p>",
            "url":"https://example.com/jobs/123", "datePosted":"2026-08-10",
            "hiringOrganization":{"name":"Example Casino"}
          }]}</script>'''
        with patch.object(crawler, "_fetch_html", return_value=page):
            jobs = crawler.crawl_jsonld("https://example.com/careers", "test")
        self.assertEqual([job["title"] for job in jobs], ["CRM Manager"])
        self.assertEqual(jobs[0]["ext_id"], "123")

    def test_official_homepage_rejects_aggregator(self):
        page = '''
          <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fcasino.guru%2Fsupergra">Review</a>
          <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fsupergra.ua%2Fen">Official</a>
        '''
        with patch.object(crawler, "_fetch_html", return_value=page):
            homepage = crawler.discover_official_homepage("SuperGra", "Ukraine")
        self.assertEqual(homepage, "https://supergra.ua/")

    def test_daily_crawl_due_without_status(self):
        with patch.object(crawler, "last_successful_run", return_value=None):
            self.assertTrue(crawler.crawl_is_due())

    def test_daily_crawl_waits_for_interval(self):
        with patch.object(crawler, "last_successful_run", return_value=datetime.utcnow() - timedelta(hours=2)):
            self.assertFalse(crawler.crawl_is_due(interval_hours=24))

    def test_country_registry_is_interleaved_by_rank(self):
        rows = [
            {"country": "Big", "rank": 2}, {"country": "Big", "rank": 1},
            {"country": "Small", "rank": 1},
        ]
        ordered = sorted(rows, key=lambda row: (row.get("rank") or 10**9, row.get("country") or ""))
        self.assertEqual([(row["rank"], row["country"]) for row in ordered],
                         [(1, "Big"), (1, "Small"), (2, "Big")])

    def test_missing_job_is_archived_only_for_complete_source(self):
        class Query:
            def filter(self, *args): return self
            def all(self): return [row]

        class DB:
            def query(self, model): return Query()
            def flush(self): pass
            def commit(self): pass
            def add(self, item): pass

        class Field:
            def __eq__(self, other): return True
            def __ne__(self, other): return True
            def in_(self, values): return True
            def __invert__(self): return True

        class Job:
            source = status = ext_id = Field()

        row = SimpleNamespace(id=7, status="approved", closed_at="", source="softswiss", ext_id="gone")
        added, updated, closed, changed, removed = crawler.upsert(
            DB(), Job, lambda *_: "Operations", [], complete_sources={"softswiss"})
        self.assertEqual((added, updated, closed), (0, 0, 1))
        self.assertEqual((changed, removed), ([], [7]))
        self.assertEqual(row.status, "archived")
        self.assertTrue(row.closed_at)

    def test_collect_retries_failed_source_and_reports_health(self):
        with patch.object(crawler, "crawl_softswiss", side_effect=[RuntimeError("temporary"), []]), \
             patch.object(crawler, "GREENHOUSE_BOARDS", {}), \
             patch.object(crawler, "JSONLD_LISTINGS", {}), \
             patch.object(crawler, "LEVER_SITES", {}), \
             patch.object(crawler, "SMARTRECRUITERS_COMPANIES", {}), \
             patch.object(crawler, "PARTNER_FEEDS", {}), \
             patch.object(crawler, "crawl_casino_seed_registry", return_value=[]):
            items, complete, health = crawler.collect(with_metadata=True)
        self.assertEqual(items, [])
        softswiss = next(row for row in health if row["key"] == "softswiss")
        self.assertTrue(softswiss["ok"])
        self.assertEqual(softswiss["attempts"], 2)
        self.assertIn("softswiss", complete)

    def test_collect_keeps_failed_source_out_of_complete_set(self):
        with patch.object(crawler, "crawl_softswiss", side_effect=RuntimeError("offline")), \
             patch.object(crawler, "GREENHOUSE_BOARDS", {}), \
             patch.object(crawler, "JSONLD_LISTINGS", {}), \
             patch.object(crawler, "LEVER_SITES", {}), \
             patch.object(crawler, "SMARTRECRUITERS_COMPANIES", {}), \
             patch.object(crawler, "PARTNER_FEEDS", {}), \
             patch.object(crawler, "crawl_casino_seed_registry", return_value=[]):
            _, complete, health = crawler.collect(with_metadata=True)
        self.assertNotIn("softswiss", complete)
        self.assertFalse(next(row for row in health if row["key"] == "softswiss")["ok"])


if __name__ == "__main__":
    unittest.main()
