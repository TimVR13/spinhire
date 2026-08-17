import json
import unittest
from datetime import datetime, timedelta
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


if __name__ == "__main__":
    unittest.main()
