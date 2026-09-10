"""Что должно работать к запуску на Product Hunt и в каталогах:

пресс-кит с живыми цифрами и английский открытый API без кириллицы в значениях.
"""
import os
import re
import unittest
from html import unescape

from fastapi.testclient import TestClient

from server.app import Base, Job, SessionLocal, app, engine, migrate, translate_generated

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

    def test_featured_jobs_api_is_localized(self):
        # карточки «Вакансии дня» рисует JS, языковой слой их не видит
        ru = client.get("/api/featured-jobs").json()
        de = client.get("/api/featured-jobs?lang=de").json()
        self.assertTrue(ru and de)
        self.assertIn("офис", [row["fmt"] for row in ru])
        self.assertIn("Büro", [row["fmt"] for row in de])
        self.assertTrue(any("Monat" in (row["salary"] or "") for row in de))
        self.assertFalse(any("Мальта" in (row["location"] or "") for row in de))

    def test_client_dictionary_is_served_for_every_language(self):
        for lang in ("de", "pl", "es", "fr", "it", "pt", "ro", "el", "bg", "uk", "en"):
            payload = client.get(f"/js/i18n-{lang}.js").json()
            self.assertGreater(len(payload), 100, lang)
            self.assertIn("Вакансии", payload, lang)
        self.assertEqual(client.get("/js/i18n-xx.js").status_code, 404)

    def test_product_hunt_badge_appears_only_when_configured(self):
        # до запуска id поста не существует: без переменной в разметке не должно быть
        # ни ссылки на PH, ни запроса к api.producthunt.com
        self.assertNotIn("ph-badge", client.get("/en/jobs").text)
        os.environ["SPINHIRE_PH_POST_ID"] = "123456"
        try:
            body = client.get("/en/jobs").text
            self.assertIn('class="ph-badge"', body)
            self.assertIn("post_id=123456", body)
            self.assertIn("producthunt.com/posts/spinhire", body)
            # бейдж один и на языковых версиях тоже
            self.assertEqual(client.get("/de/press.html").text.count("ph-badge"), 1)
        finally:
            os.environ.pop("SPINHIRE_PH_POST_ID")
        self.assertNotIn("ph-badge", client.get("/en/jobs").text)

    def test_market_stats_translate_directions_for_english(self):
        ru = client.get("/api/market-stats").json()
        en = client.get("/api/market-stats?lang=en").json()
        self.assertEqual(ru["live_jobs"], en["live_jobs"])
        self.assertIn("Операции казино", [row["name"] for row in ru["directions"]])
        self.assertIn("Casino operations", [row["name"] for row in en["directions"]])



class LanguageCleanlinessTests(unittest.TestCase):
    """Ни одной русской строки на языковых версиях страниц без данных источников.

    Берём страницы, которые целиком собираются из наших текстов (тарифы и
    пресс-кит): вакансии и компании приходят от работодателей и могут быть
    на любом языке, а вот интерфейс обязан быть переведён полностью.
    """

    LANGS = ("en", "de", "pl", "es", "fr", "it", "pt", "ro", "el")
    PAGES = ("/post-job", "/press.html", "/resumes", "/blog.html")
    # переключатель языков специально остаётся на языке оригинала
    ALLOWED = {"Русский", "Українська", "Български"}
    CYRILLIC = re.compile(r"[А-Яа-яЁё]")

    def _text_nodes(self, path):
        body = client.get(path).text
        body = re.sub(r"<script.*?</script>", "", body, flags=re.S)
        body = re.sub(r"<style.*?</style>", "", body, flags=re.S)
        return [unescape(" ".join(node.split())) for node in re.findall(r">([^<>]+)<", body)]

    def test_interface_pages_have_no_russian_left(self):
        for lang in self.LANGS:
            for page in self.PAGES:
                left = [text for text in self._text_nodes(f"/{lang}{page}")
                        if text and text not in self.ALLOWED and self.CYRILLIC.search(text)]
                self.assertEqual(left, [], f"/{lang}{page}: {left[:5]}")

    def test_ukrainian_and_bulgarian_have_no_russian_words(self):
        # кириллица тут законна, поэтому ищем буквы и слова, которых в языке не бывает
        checks = {
            "uk": re.compile(r"[ыъэЫЪЭ]|(?<![А-Яа-яЁёІіЇїЄєҐґ])(и|или|что|это|Работа|работа|"
                             r"вакансии|вакансий|зарплаты|нет|можно)(?![А-Яа-яЁёІіЇїЄєҐґ])"),
            "bg": re.compile(r"[ыэёЫЭЁ]|(?<![А-Яа-яЁё])(что|это|если|чтобы|который|вакансии|"
                             r"вакансий|зарплаты|нужно|можно|только|всё|ещё)(?![А-Яа-яЁё])"),
        }
        for lang, russian in checks.items():
            for page in self.PAGES:
                left = [text for text in self._text_nodes(f"/{lang}{page}")
                        if text not in self.ALLOWED and russian.search(text)]
                self.assertEqual(left, [], f"/{lang}{page}: {left[:5]}")

    def test_language_prefix_survives_blog_redirects(self):
        # /de/blog вёл на русский блог: префикс терялся вместе с читателем
        response = client.get("/de/blog", follow_redirects=False)
        self.assertEqual(response.headers["location"], "/de/blog.html")
        legacy = client.get("/uk/post-aml-officer-career.html", follow_redirects=False)
        self.assertEqual(legacy.headers["location"], "/uk/blog/aml-officer-career")

    def test_sentences_with_a_date_are_localized(self):
        # дата внутри фразы каждый день новая — в словаре она стоит как @
        body = client.get("/de/market").text
        self.assertIn("gibt es in der Branche", body)
        self.assertNotIn("в индустрии открыто", body)

    def test_generated_strings_are_localized(self):
        cases = {
            "en": ("17 jobs", "from €2 000/month"),
            "de": ("17 Stellen", "ab €2 000/Monat"),
            "pl": ("2 oferty", "od €2 000/mies."),
            "uk": ("5 вакансій", "від €2 000/міс"),
        }
        for lang, (count, salary) in cases.items():
            self.assertEqual(translate_generated("17 вакансий" if "17" in count else
                                                 ("2 вакансии" if "2 " in count else "5 вакансий"), lang), count)
            self.assertEqual(translate_generated("от €2 000 в месяц", lang), salary)

if __name__ == "__main__":
    unittest.main()
