"""Письма о вакансиях под резюме и поднятие резюме в топ выдачи."""
import unittest
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from server.app import (BOOST_COST_SC, Base, Job, Notification, Order, Resume, SessionLocal,
                        User, app, engine, hash_pw, mark_order_paid, migrate, signer)
from server import alerts  # noqa: E402  (после app: модуль подключается из его хвоста)


class _Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            migrate(db)

    def setUp(self):
        with SessionLocal() as db:
            user = User(email="boost-candidate@test.invalid", password_hash=hash_pw("test"),
                        name="Boost Candidate", role="talent", coins=BOOST_COST_SC + 100)
            db.add(user)
            db.flush()
            cv = Resume(user_id=user.id, title="CRM Manager", location="Warsaw", experience_years=6,
                        skills="CRM, Retention", about="iGaming experience with casino retention flows",
                        employment_history="Retention Lead — 4 years", published=True, status="approved",
                        consent_at="2026-09-01T00:00:00Z")
            job = Job(title="CRM Manager", company_name="Test Casino", category="Маркетинг и CRM",
                      location="Warsaw, Польша", fmt="удалёнка", tags="CRM, retention, casino",
                      description="We need a CRM manager with retention experience in an iGaming casino. "
                                  "Own the lifecycle, bonuses and reactivation. Remote from Poland. " * 3,
                      status="approved", source="test")
            db.add_all([cv, job])
            db.commit()
            self.user_id, self.resume_id, self.job_id = user.id, cv.id, job.id

    def tearDown(self):
        with SessionLocal() as db:
            db.query(alerts.JobAlertSent).filter_by(user_id=self.user_id).delete()
            db.query(Notification).filter_by(user_id=self.user_id).delete()
            db.query(Order).filter_by(user_id=self.user_id).delete()
            db.query(Resume).filter_by(id=self.resume_id).delete()
            db.query(Job).filter_by(id=self.job_id).delete()
            db.query(User).filter_by(id=self.user_id).delete()
            db.commit()

    def client(self):
        c = TestClient(app, follow_redirects=False)
        c.cookies.set("sh_session", signer.dumps({"uid": self.user_id}))
        return c


class BoostTests(_Fixture):
    def test_boost_for_coins_puts_resume_first(self):
        r = self.client().post("/profile/boost")
        self.assertEqual(r.status_code, 303)
        self.assertIn("boost=ok", r.headers["location"])
        with SessionLocal() as db:
            cv, user = db.get(Resume, self.resume_id), db.get(User, self.user_id)
            self.assertTrue(cv.is_boosted)
            self.assertEqual(user.coins, 100)
            self.assertTrue(db.query(Notification).filter_by(user_id=self.user_id, kind="boost").first())
        page = TestClient(app).get("/resumes").text
        self.assertIn("⚡ В топе", page)
        # поднятое резюме — первое в списке (класс .cv-list раньше встречается в CSS, якорь — сам div)
        self.assertLess(page.index(f"/resume/{self.resume_id}"), page.index('<div class="cv-list">') + 400)
        # английская версия: бейдж переведён, а не утёк по-русски
        self.assertIn("⚡ Top", TestClient(app).get("/en/resumes").text)

    def test_boost_needs_coins_and_published_resume(self):
        with SessionLocal() as db:
            db.get(User, self.user_id).coins = 5
            db.commit()
        self.assertIn("boost=nocoins", self.client().post("/profile/boost").headers["location"])
        with SessionLocal() as db:
            db.get(Resume, self.resume_id).status = "pending"
            db.commit()
        self.assertIn("boost=notready", self.client().post("/profile/boost").headers["location"])

    def test_paid_order_boosts_once(self):
        r = self.client().post("/checkout/boost30")
        self.assertEqual(r.status_code, 303)
        order_id = int(r.headers["location"].rsplit("/", 1)[1])
        with SessionLocal() as db:
            order = db.get(Order, order_id)
            self.assertEqual((order.plan, order.amount), ("boost30", 10))
            self.assertTrue(mark_order_paid(db, order))
            db.commit()
            first = db.get(Resume, self.resume_id).boosted_until
            self.assertTrue(first > (datetime.utcnow() + timedelta(days=29)).isoformat())
            self.assertFalse(mark_order_paid(db, order))   # повтор не продлевает
            db.commit()
            self.assertEqual(db.get(Resume, self.resume_id).boosted_until, first)

    def test_profile_renders_boost_card(self):
        page = self.client().get("/profile").text
        self.assertIn("Резюме в топе поиска", page)
        self.assertIn(f"За {BOOST_COST_SC} SC", page)


class AlertTests(_Fixture):
    def test_settings_toggle(self):
        c = self.client()
        c.post("/profile", data={"name": "Boost Candidate", "job_search_status": "active"})
        with SessionLocal() as db:
            self.assertFalse(db.get(User, self.user_id).alerts_enabled)
        c.post("/profile", data={"name": "Boost Candidate", "job_search_status": "active", "alerts": "on"})
        with SessionLocal() as db:
            self.assertTrue(db.get(User, self.user_id).alerts_enabled)

    def test_digest_goes_once_a_day_with_matching_jobs(self):
        outbox = []
        real = alerts.resend_send
        alerts.resend_send = lambda to, subject, body: outbox.append((to, subject, body)) or True
        try:
            with SessionLocal() as db:
                user, cv = db.get(User, self.user_id), db.get(Resume, self.resume_id)
                picks = alerts.pick_jobs(db, user, cv)
                # база общая с dev-данными: рядом могут быть настоящие CRM-вакансии, это нормально
                self.assertIn(self.job_id, [job.id for _, job in picks])
                self.assertLessEqual(len(picks), alerts.MAX_JOBS)
                self.assertTrue(all(percent >= alerts.MIN_SCORE for percent, _ in picks))
                first_job_id, n_picks = picks[0][1].id, len(picks)
                self.assertEqual(alerts.send_job_alerts(db), 1)
                self.assertEqual(alerts.send_job_alerts(db), 0)   # второй раз в тот же день — тишина
                self.assertTrue(db.query(alerts.JobAlertSent).filter_by(user_id=self.user_id,
                                                                        job_id=self.job_id).first())
                self.assertTrue(db.get(User, self.user_id).alerts_last_sent)
        finally:
            alerts.resend_send = real
        to, subject, body = outbox[0]
        self.assertEqual(to, "boost-candidate@test.invalid")
        self.assertIn(str(n_picks), subject)   # «N new jobs…» — на языке пользователя (пусто → en)
        self.assertIn(f"/job/{first_job_id}?utm_source=alerts", body)
        self.assertIn("/alerts/unsubscribe?t=", body)

    def test_unsubscribe_link(self):
        with SessionLocal() as db:
            token = alerts.unsubscribe_token(db.get(User, self.user_id))
        c = TestClient(app)
        self.assertEqual(c.get("/alerts/unsubscribe", params={"t": "garbage"}).status_code, 404)
        self.assertEqual(c.get("/alerts/unsubscribe", params={"t": token}).status_code, 200)
        with SessionLocal() as db:
            self.assertFalse(db.get(User, self.user_id).alerts_enabled)
        # токен отписки не годится как сессия
        c.cookies.set("sh_session", token)
        self.assertEqual(c.get("/profile", follow_redirects=False).status_code, 303)


if __name__ == "__main__":
    unittest.main()
