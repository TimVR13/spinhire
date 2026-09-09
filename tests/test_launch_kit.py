"""Что должно работать к запуску на Product Hunt и в каталогах:

пресс-кит с живыми цифрами и английский открытый API без кириллицы в значениях.
"""
import unittest

from fastapi.testclient import TestClient

from server.app import Base, Job, SessionLocal, app, engine, migrate

client = TestClient(app)


class LaunchKitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            migrate(db)
            job = Job(title="VIP Manager", company_name="Launch Casino",
                      category="Операции казино", location="Limassol, Кипр", fmt="офис",
                      salary="от €3 000 в месяц", status="approved",
                      source_url="https://example.invalid/vip", description="Launch kit fixture")
            db.add(job)
            db.commit()
            cls.job_id = job.id

    @classmethod
    def tearDownClass(cls):
        with SessionLocal() as db:
            job = db.get(Job, cls.job_id)
            if job:
                db.delete(job)
                db.commit()

    # ---------- пресс-кит ----------

    def test_press_kit_is_served_with_live_numbers(self):
        response = client.get("/press.html")
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn("Пресс-кит SpinHire", body)
        # цифры подставляются из базы, а не остаются заглушкой вёрстки
        self.assertNotIn('data-press-stat="live_jobs">6 000+', body)
        self.assertRegex(body, r'data-press-stat="live_jobs">[\d\s]+\+')
        self.assertRegex(body, r'data-press-stat="companies">[\d\s]+\+')

    def test_clean_press_url_redirects_to_page(self):
        response = client.get("/press", follow_redirects=False)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.headers["location"], "/press.html")

    def test_clean_press_url_keeps_language_prefix(self):
        response = client.get("/en/press", follow_redirects=False)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.headers["location"], "/en/press.html")

    def test_press_kit_has_english_version(self):
        body = client.get("/en/press.html").text
        self.assertIn("SpinHire press kit", body)
        self.assertIn("Ready-made descriptions", body)
        self.assertNotIn("Пресс-кит SpinHire", body)

    def test_press_kit_is_in_sitemap_and_llms(self):
        self.assertIn("https://spinhire.io/press.html", client.get("/sitemap.xml").text)
        self.assertIn("/press.html", client.get("/llms.txt").text)
        self.assertIn("/press.html", client.get("/en/llms.txt").text)

    # ---------- открытый API ----------

    def _job(self, payload):
        return next(row for row in payload["jobs"] if row["id"] == self.job_id)

    def test_api_keeps_russian_values_by_default(self):
        payload = client.get("/api/jobs?limit=100").json()
        self.assertEqual(payload["lang"], "ru")
        job = self._job(payload)
        self.assertEqual(job["category"], "Операции казино")
        self.assertEqual(job["format"], "офис")
        self.assertEqual(job["country"], "Кипр")
        self.assertIn("в месяц", job["salary"])
        self.assertIn("использование свободно", payload["license"])

    def test_api_lang_en_returns_english_values(self):
        payload = client.get("/api/jobs?limit=100&lang=en").json()
        self.assertEqual(payload["lang"], "en")
        job = self._job(payload)
        self.assertEqual(job["category"], "Casino operations")
        self.assertEqual(job["format"], "office")
        self.assertEqual(job["country"], "Cyprus")
        self.assertEqual(job["salary"], "from €3 000/month")
        self.assertIn("attribution", payload["license"])

    def test_english_path_prefix_switches_api_language(self):
        payload = client.get("/en/api/jobs?limit=100").json()
        self.assertEqual(payload["lang"], "en")
        self.assertEqual(self._job(payload)["country"], "Cyprus")

    def test_market_stats_translate_directions_for_english(self):
        ru = client.get("/api/market-stats").json()
        en = client.get("/api/market-stats?lang=en").json()
        self.assertEqual(ru["live_jobs"], en["live_jobs"])
        self.assertIn("Операции казино", [row["name"] for row in ru["directions"]])
        self.assertIn("Casino operations", [row["name"] for row in en["directions"]])


if __name__ == "__main__":
    unittest.main()
