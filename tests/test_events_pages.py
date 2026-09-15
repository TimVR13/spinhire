"""Публичная форма «Добавить событие»: заявка ждёт проверки, страница до одобрения скрыта."""
import os
import unittest
import uuid

os.environ.setdefault("SPINHIRE_ROLE", "all")
os.environ.setdefault("EVENTS_CRAWLER_ENABLED", "0")
os.environ.setdefault("CRAWLER_DAILY_ENABLED", "0")

from fastapi.testclient import TestClient  # noqa: E402

from server.app import Event, SessionLocal, app  # noqa: E402


class SubmitEventTests(unittest.TestCase):
    def setUp(self):
        self.title = f"Test Summit {uuid.uuid4().hex[:6]}"

    def tearDown(self):
        with SessionLocal() as db:
            for ev in db.query(Event).filter(Event.title == self.title).all():
                db.delete(ev)
            db.commit()

    def test_submission_is_pending_and_hidden_until_approved(self):
        with TestClient(app) as client:
            page = client.get("/events/submit")
            self.assertEqual(page.status_code, 200)
            self.assertIn("Добавить событие", page.text)
            resp = client.post("/events/submit", data={
                "title": self.title, "date_from": "2027-03-10", "date_to": "2027-03-11",
                "category": "Выставка", "city": "Лиссабон, Португалия", "url": "example.com/summit",
                "description": "Тестовая заявка", "contact": "qa@example.com", "website": "",
            }, follow_redirects=False)
            self.assertEqual(resp.status_code, 303)
            self.assertEqual(resp.headers["location"], "/events/submit?ok=1")
            with SessionLocal() as db:
                ev = db.query(Event).filter(Event.title == self.title).first()
                self.assertIsNotNone(ev)
                self.assertEqual((ev.source, ev.active), ("user", False))
                self.assertEqual(ev.url, "https://example.com/summit")
                self.assertEqual(ev.category, "Выставка")
                self.assertEqual(ev.city_en, "Lisbon")
                self.assertTrue(ev.slug.startswith("test-summit-") and ev.slug.endswith("-2027"))
                slug = ev.slug
            # до одобрения страницы нет ни в календаре, ни по адресу, ни в API
            self.assertEqual(client.get(f"/event/{slug}").status_code, 404)
            self.assertNotIn(self.title, client.get("/events").text)
            self.assertNotIn(self.title, client.get("/api/events").text)
            with SessionLocal() as db:
                ev = db.query(Event).filter(Event.slug == slug).first()
                ev.active = True
                db.commit()
            self.assertEqual(client.get(f"/event/{slug}").status_code, 200)
            self.assertIn(self.title, client.get("/api/events").text)

    def test_honeypot_and_validation(self):
        with TestClient(app) as client:
            bot = client.post("/events/submit", data={"title": self.title, "date_from": "2027-03-10",
                                                     "city": "Лиссабон", "website": "http://spam"},
                              follow_redirects=False)
            self.assertEqual(bot.status_code, 303)
            with SessionLocal() as db:
                self.assertIsNone(db.query(Event).filter(Event.title == self.title).first())
            bad = client.post("/events/submit", data={"title": "ab", "date_from": "10.03.2027", "city": ""})
            self.assertEqual(bad.status_code, 200)
            self.assertIn("Укажите название события", bad.text)
            self.assertIn("Укажите дату начала", bad.text)
            self.assertIn("Укажите город", bad.text)


if __name__ == "__main__":
    unittest.main()
