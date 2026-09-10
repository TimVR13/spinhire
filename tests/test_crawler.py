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


class RelevanceFilterTests(unittest.TestCase):
    """Борд — про iGaming. Проверяем, что мимо не проезжает логистика,
    ресторан наземного казино и аутсорс с универсального борда."""

    def test_offtopic_roles_are_irrelevant(self):
        for title in ("Global Logistics Lead", "Director of Supply Chain Accounting",
                      "Logistics Coordinator", "Shipping Specialist I", "Material Handler I",
                      "Dishwasher Brew Brothers", "Beverage Server (Harrah's)",
                      "Server - Part Time (New Haven Winners Circle)", "Brew Brothers Server",
                      "GUEST ROOM ATTENDANT", "Spa Attendant", "Lifeguard (Citywide LV)",
                      "Concierge - Villas", "Retail Sales Associate - Full Time",
                      "Cashier - Cross Street Grill", "Restaurant Manager - Brew Brothers",
                      "Security Supervisor - Full Time", "Mechanic General Maint A",
                      "Engineer I (Maintenance)", "Assembly and Handling Technician",
                      "Quantity Surveyor", "Administrator - Real Estate",
                      "UAV Pilot and Technician", "Адіністратор рецепції"):
            with self.subTest(title=title):
                self.assertTrue(crawler.job_is_irrelevant(title))

    def test_igaming_roles_survive_the_filter(self):
        for title in ("Table Games Dealer", "WSOP Dealer", "ASSISTANT PIT MANAGER",
                      "Cage Cashier", "Casino Cashier-Full-Time(Bettendorf)",
                      "Count Room Team Member", "Slot Attendant | Part Time",
                      "Slot Technician", "Surveillance Operator", "Executive Casino Host",
                      "Sportsbook Ticket Writer", "Shift Manager VLT",
                      "Cashier? Earn Up to $23/hr (Tips) On Camera – No Register",
                      "Data Warehouse Modelling Engineer", "SQL Server Administrator",
                      "Information Security Manager", "Production Operator Part Time",
                      "Senior Software Supply Chain Security Researcher",
                      "VIP Manager", "Head of Affiliates", "AML Officer"):
            with self.subTest(title=title):
                self.assertFalse(crawler.job_is_irrelevant(title))

    def test_catalog_trusts_only_niche_sources(self):
        # каталог компаний собран из тех же вакансий: доверять его строкам с
        # универсальных бордов нельзя, иначе он сам себя одобряет
        entries = [{"name": "Upwind", "sources": ["djinni"]},
                   {"name": "Bank Pivdenny", "sources": ["djinni", "work.ua"]},
                   {"name": "Betsson Group", "sources": ["greenhouse:betsson", "djinni"]},
                   {"name": "SOFTSWISS", "sources": ["softswiss"]},
                   {"name": "Без источников", "sources": []}]
        self.assertEqual(crawler.catalog_igaming_companies(entries),
                         {"betsson group", "softswiss"})

    def test_company_proves_profile_by_its_own_flow(self):
        rows = [
            # аутсорс: один гемблинг-заказ среди чужих отраслей — доверия нет
            ("Sigma Software", "djinni", "Casino platform developer", ""),
            ("Sigma Software", "djinni", "SAP Consultant", ""),
            ("Sigma Software", "djinni", "Amazon PPC Specialist", ""),
            ("Sigma Software", "djinni", "Shopify Developer", ""),
            # аффилиат: отрасль в большинстве вакансий
            ("RedCore", "djinni", "Affiliate Manager", "iGaming traffic"),
            ("RedCore", "djinni", "Senior SEO Specialist", "casino brands"),
            ("RedCore", "djinni", "Product Manager", ""),
            # профильный источник в вайтлист через эту функцию не попадает
            ("Betsson Group", "greenhouse:betsson", "Backend Engineer", ""),
        ]

        class Query:
            def filter(self, *args, **kwargs):
                return self

            def distinct(self):
                return self

            def all(self):
                return rows

        class DB:
            def query(self, *args):
                return Query()

        job = SimpleNamespace(company_name="", source="", title="", description="")
        self.assertEqual(crawler.companies_proven_by_signal(DB(), job), {"redcore"})

    def test_signal_ignores_words_from_other_industries(self):
        for text in ("Google Ads is the channel we're betting on",
                     "A/B (dual-slot) update schemes and OTA frameworks",
                     "integrations with third-party providers for KYC, payments and compliance"):
            with self.subTest(text=text):
                self.assertIsNone(crawler.IGAMING_SIGNAL_RE.search(text))
        for text in ("experience in sports betting", "iGaming affiliate marketing",
                     "slots content roadmap", "live dealer studio", "MGA licence"):
            with self.subTest(text=text):
                self.assertIsNotNone(crawler.IGAMING_SIGNAL_RE.search(text))
