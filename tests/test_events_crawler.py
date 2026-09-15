import json
import os
import unittest
import unittest.mock
from datetime import date

from server import event_covers, events_crawler as ec

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "thegamblest-sbc-summit-lisbon.html")
SOURCE_URL = "https://www.thegamblest.com/event/sbc-summit-lisbon/"


class ParseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE, encoding="utf-8") as fh:
            cls.data = ec.parse_event_page(fh.read(), SOURCE_URL)

    def test_core_fields(self):
        d = self.data
        self.assertEqual(d["title"], "SBC Summit Lisbon 2026")
        self.assertEqual((d["date_from"], d["date_to"]), ("2026-09-29", "2026-10-01"))
        self.assertEqual((d["city_en"], d["country_en"]), ("Lisbon", "Portugal"))
        self.assertIn("Rossio dos Olivais", d["venue"])
        self.assertEqual(d["organizer"], "SBC Events")
        self.assertEqual(d["url"], "https://sbcevents.com/sbc-summit/")
        self.assertIn("https://www.linkedin.com/company/sbcevents/", d["socials"])
        self.assertTrue(d["cover_src"].endswith("sbc-summit-2026-lisbon.jpg"))
        self.assertEqual(d["category"], "Конференция")
        self.assertEqual(d["src_slug"], "sbc-summit-lisbon")

    def test_description_is_full_text_not_truncated_ld(self):
        self.assertIn("Join the summit", self.data["description_en"])
        self.assertNotIn("&hellip;", self.data["description_en"])
        self.assertNotIn("<", self.data["description_en"])
        self.assertGreaterEqual(self.data["description_en"].count("\n\n"), 2)

    def test_side_events_merge_html_status_with_ld_dates(self):
        subs = self.data["sub_events"]
        self.assertEqual(len(subs), 10)
        by_name = {s["name"]: s for s in subs}
        club = by_name["iGaming Club Lisbon"]
        self.assertEqual(club["date"], "2026-09-28")
        self.assertEqual(club["time"], "19:00")
        self.assertEqual(club["venue"], "Ferroviário")
        self.assertEqual(club["access"], "public")
        self.assertTrue(club["recommended"])
        vip = by_name["C-Level & Operator VIP Dinner & Party"]
        self.assertEqual(vip["access"], "invite")
        self.assertEqual(vip["date"], "2026-09-30")
        self.assertEqual([s["date"] for s in subs], sorted(s["date"] for s in subs))

    def test_page_without_event_ld_is_skipped(self):
        self.assertIsNone(ec.parse_event_page("<html><body>nothing</body></html>", SOURCE_URL))


class HelpersTests(unittest.TestCase):
    def test_slug_gets_year_once(self):
        self.assertEqual(ec.make_slug("sbc-summit-lisbon", "2026-09-29"), "sbc-summit-lisbon-2026")
        self.assertEqual(ec.make_slug("gat-expo-bogota-2026", "2026-10-15"), "gat-expo-bogota-2026")
        self.assertEqual(ec.make_slug("sbc-summit-lisbon", "2027-09-21"), "sbc-summit-lisbon-2027")

    def test_city_label_ru_with_flag(self):
        self.assertEqual(ec.city_label_ru("Lisbon", "Portugal"), "🇵🇹 Лиссабон, Португалия")
        self.assertEqual(ec.city_label_ru("Gaborone", "Botswana"), "🇧🇼 Габороне, Ботсвана")
        self.assertEqual(ec.city_label_ru("Prague", "Czech"), "🇨🇿 Прага, Чехия")
        self.assertEqual(ec.city_label_ru("Savannah", "USA"), "🇺🇸 Саванна, США")

    def test_clean_city(self):
        self.assertEqual(ec.clean_city("Georgia, Savannah", "USA"), "Savannah")
        self.assertEqual(ec.clean_city("Mexico", "Mexico"), "Mexico City")
        self.assertEqual(ec.ascii_slug("São Paulo"), "sao-paulo")

    def test_category_guess(self):
        self.assertEqual(ec.guess_category("EGR Operator Awards 2026"), "Награды")
        self.assertEqual(ec.guess_category("iGB Affiliate Barcelona 2027"), "Аффилейт")
        self.assertEqual(ec.guess_category("G2E 2026: Global Gaming Expo"), "Выставка")
        self.assertEqual(ec.guess_category("iGaming Club Lisbon 2026"), "Нетворкинг")
        self.assertEqual(ec.guess_category("SPiCE Central Asia 2026"), "Конференция")

    def test_same_event_matches_seed_rows(self):
        self.assertTrue(ec.same_event("SBC Summit Lisbon", "2026-09-29", "SBC Summit Lisbon 2026", "2026-09-29"))
        self.assertTrue(ec.same_event("SiGMA World Rome ★", "2026-11-02", "SiGMA World Summit 2026", "2026-11-02"))
        self.assertTrue(ec.same_event("ICE Barcelona", "2027-01-18", "ICE Barcelona 2027", "2027-01-19"))
        self.assertFalse(ec.same_event("SiGMA Central Europe", "2026-11-23", "SiGMA World Summit 2026", "2026-11-02"))
        self.assertFalse(ec.same_event("iGaming Club Lisbon", "2026-09-28", "SBC Summit Lisbon 2026", "2026-09-29"))

    def test_sitemap_entries(self):
        xml = ('<urlset><url><loc>https://www.thegamblest.com/event/</loc></url>'
               '<url><loc>https://www.thegamblest.com/event/sbc-summit-lisbon/</loc><lastmod>2026-09-07T10:58:00+00:00</lastmod></url>'
               '<url><loc>https://www.thegamblest.com/other/</loc></url></urlset>')
        self.assertEqual(ec.sitemap_entries(xml),
                         [("https://www.thegamblest.com/event/sbc-summit-lisbon/", "2026-09-07T10:58:00+00:00")])

    def test_format_dates(self):
        self.assertEqual(event_covers.format_dates("2026-09-29", "2026-10-01"), "29 сен – 1 окт 2026")
        self.assertEqual(event_covers.format_dates("2026-09-24", "2026-09-25"), "24–25 сен 2026")
        self.assertEqual(event_covers.format_dates("2026-10-15", "2026-10-15"), "15 окт 2026")
        self.assertEqual(event_covers.format_dates("2026-09-29", "2026-10-01", "en", with_year=False), "29 Sep – 1 Oct")
        self.assertEqual(event_covers.day_title("2026-09-28"), "28 сентября")
        self.assertEqual(event_covers.month_title("2026-09", "en"), "September")


class DbTests(unittest.TestCase):
    """upsert/deactivate на временной SQLite с настоящей моделью Event."""

    def setUp(self):
        os.environ.setdefault("SPINHIRE_ROLE", "all")
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from server import app as web
        self.Event = web.Event
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
        web.Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        with open(FIXTURE, encoding="utf-8") as fh:
            self.data = ec.parse_event_page(fh.read(), SOURCE_URL)
        # фото города — сеть (Википедия); в тестах не ходим
        patcher = unittest.mock.patch.object(ec, "ensure_city_photo", lambda *a, **k: "")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_upsert_adopts_manual_row_and_updates_in_place(self):
        with self.Session() as db:
            db.add(self.Event(title="SBC Summit Lisbon", city="🇵🇹 Лиссабон, Португалия",
                              date_from="2026-09-29", date_to="2026-10-01", url="https://sbcevents.com/sbc-summit/"))
            db.commit()
            status = {}
            ev, action = ec.upsert(db, self.Event, self.data, status, translate=lambda t: "перевод: " + t[:20])
            db.commit()
            self.assertEqual(action, "adopted")
            self.assertEqual(ev.slug, "sbc-summit-lisbon-2026")
            self.assertEqual(ev.source, "thegamblest")
            self.assertEqual(ev.city, "🇵🇹 Лиссабон, Португалия")
            self.assertEqual(ev.country_iso, "PT")
            self.assertTrue(ev.description.startswith("перевод: "))
            self.assertEqual(len(json.loads(ev.sub_events)), 10)
            self.assertEqual(db.query(self.Event).count(), 1)
            # повторный прогон: описание не изменилось → перевод не дёргаем
            ev2, action2 = ec.upsert(db, self.Event, self.data, status, translate=lambda t: "НЕ ДОЛЖНО ВЫЗВАТЬСЯ")
            db.commit()
            self.assertEqual((action2, ev2.id), ("updated", ev.id))
            self.assertTrue(ev2.description.startswith("перевод: "))

    def test_deactivate_past_keeps_admin_hidden_hidden(self):
        with self.Session() as db:
            db.add(self.Event(title="Old", date_from="2026-01-10", date_to="2026-01-12", slug="old-2026", active=True))
            db.add(self.Event(title="Hidden future", date_from="2027-05-01", date_to="2027-05-02", slug="hidden-2027", active=False))
            db.add(self.Event(title="Future", date_from="2027-05-01", date_to="2027-05-02", slug="future-2027", active=True))
            db.commit()
            self.assertEqual(ec.deactivate_past(db, self.Event, today=date(2026, 9, 15)), 1)
            db.commit()
            states = {e.slug: e.active for e in db.query(self.Event).all()}
            self.assertEqual(states, {"old-2026": False, "hidden-2027": False, "future-2027": True})


if __name__ == "__main__":
    unittest.main()
