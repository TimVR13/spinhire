# -*- coding: utf-8 -*-
"""Бот подбора вакансий: поиск, резюме из чата, отклик, подписка."""
import os
import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ.setdefault("SPINHIRE_JOBBOT_TOKEN", "test:token")

from server.app import (Application, Base, Job, Resume, SessionLocal, User,  # noqa: E402
                        engine, migrate, resend_send)
from server import jobbot  # noqa: E402 — только после server.app (циклический импорт)


def _job(title, company, salary="", location="Limassol", tags="", created=None):
    return Job(title=title, company_name=company, category="Маркетинг и CRM",
               location=location, salary=salary or "по запросу", tags=tags,
               description="Описание вакансии", status="approved", owner_id=None,
               created_at=created or datetime.utcnow())


class Sent(list):
    """Перехват вызовов Telegram: в тестах наружу не ходим."""

    def api(self, method, payload):
        self.append((method, payload))
        return {"ok": True, "result": {"message_id": len(self)}}

    def texts(self):
        return [p.get("text", "") for m, p in self if m == "sendMessage"]

    def buttons(self):
        out = []
        for _m, payload in self:
            for row in (payload.get("reply_markup") or {}).get("inline_keyboard", []):
                out.extend(row)
        return out


class JobbotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            migrate(db)

    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.chat_id = f"9{int(uuid.uuid4().int % 10**8)}"
        self.company = f"Bot Test {self.suffix} Ltd"
        jobbot._index_cache.update(at=0.0, rows=[])
        jobbot._seen_updates.clear()
        with SessionLocal() as db:
            rows = [
                _job("Business Development Manager", self.company, "€4 000 – 6 000",
                     tags="BizDev, Sales"),
                _job("Head of Business Development", self.company, "€9 000",
                     tags="BizDev"),
                _job("Customer Support Agent", self.company, "€2 000",
                     tags="Support"),
            ]
            db.add_all(rows)
            db.commit()
            self.job_ids = [r.id for r in rows]
            self.bd_id, self.head_id = rows[0].id, rows[1].id

    def tearDown(self):
        with SessionLocal() as db:
            chat = db.query(jobbot.BotChat).filter_by(chat_id=self.chat_id).first()
            if chat and chat.user_id:
                db.query(Application).filter_by(user_id=chat.user_id).delete()
                db.query(Resume).filter_by(user_id=chat.user_id).delete()
                db.query(jobbot.BotLogin).filter_by(user_id=chat.user_id).delete()
                db.query(User).filter_by(id=chat.user_id).delete()
            if chat:
                db.delete(chat)
            db.query(Application).filter(Application.job_id.in_(self.job_ids)).delete(
                synchronize_session=False)
            db.query(Job).filter(Job.id.in_(self.job_ids)).delete(synchronize_session=False)
            db.commit()

    # ---------- поиск ----------

    def test_synonym_finds_role(self):
        """«биздев» — это Business Development, а не пустая выдача."""
        with SessionLocal() as db:
            found, exact = jobbot.search(db, "биздев")
        self.assertTrue(exact)
        ids = [row["id"] for row in found]
        self.assertIn(self.bd_id, ids)
        self.assertNotIn(self.job_ids[2], ids[:2])

    def test_money_sorts_inside_relevance(self):
        """Внутри одного уровня релевантности сверху — деньги."""
        with SessionLocal() as db:
            rows, _exact = jobbot.search(db, "business development")
            found = [r for r in rows if r["id"] in (self.bd_id, self.head_id)]
        self.assertEqual(found[0]["id"], self.head_id)

    def test_unrelated_query_returns_nothing(self):
        """Честный ноль лучше случайной выдачи: обещание «10 вакансий» не врёт."""
        with SessionLocal() as db:
            self.assertEqual(jobbot.search(db, "тракторист комбайнёр"), ([], True))

    def test_role_word_is_not_matched_inside_another_word(self):
        """«unity» внутри «opportunity» — не Unity: обещание «нашёл N» должно быть правдой."""
        with SessionLocal() as db:
            rows, _exact = jobbot.search(db, "unity")
        self.assertFalse(any("opportunity" in r["title_low"] and "unity" not in r["meta_low"]
                             for r in rows))

    def test_country_narrows_the_role(self):
        """«саппорт польша» — это про Польшу, а не про любой саппорт."""
        with SessionLocal() as db:
            db.add(_job("Customer Support Agent", self.company, location="Warsaw, Poland"))
            db.commit()
            polish = db.query(Job).filter_by(company_name=self.company,
                                             location="Warsaw, Poland").first()
            self.job_ids.append(polish.id)
            jobbot._index_cache.update(at=0.0, rows=[])
            rows, exact = jobbot.search(db, "саппорт польша")
        self.assertTrue(exact)
        self.assertIn(polish.id, [r["id"] for r in rows[:20]])
        self.assertNotIn(self.job_ids[2], [r["id"] for r in rows])

    def test_us_jobs_stay_out_unless_asked(self):
        """Правило каналов «США не постим» работает и в чате — пока не спросили прямо."""
        with SessionLocal() as db:
            db.add(_job("Affiliate Manager", self.company, salary="$120 000 в год",
                        location="Denver, Colorado, United States"))
            db.commit()
            us = db.query(Job).filter_by(company_name=self.company,
                                         title="Affiliate Manager").first()
            self.job_ids.append(us.id)
            jobbot._index_cache.update(at=0.0, rows=[])
            hidden, _e1 = jobbot.search(db, "affiliate manager")
            asked, _e2 = jobbot.search(db, "affiliate manager usa")
        self.assertNotIn(us.id, [r["id"] for r in hidden])
        self.assertIn(us.id, [r["id"] for r in asked])

    # ---------- диалог ----------

    def _update(self, text=None, data=None, document=None):
        sender = {"id": int(self.chat_id), "username": f"user{self.suffix}",
                  "first_name": "Тест", "language_code": "ru"}
        chat = {"id": int(self.chat_id)}
        if data:
            return {"update_id": len(jobbot._seen_updates) + 1,
                    "callback_query": {"id": "cb", "from": sender,
                                       "message": {"chat": chat}, "data": data}}
        message = {"chat": chat, "from": sender}
        if document:
            message["document"] = document
        else:
            message["text"] = text
        return {"update_id": len(jobbot._seen_updates) + 1, "message": message}

    def _run(self, update, sent=None):
        sent = sent if sent is not None else Sent()
        with patch.object(jobbot, "api", sent.api), SessionLocal() as db:
            jobbot.handle_update(db, update)
        return sent

    def test_start_greets_and_shows_menu(self):
        """Первое сообщение — меню кнопок: писать что-то человек не обязан."""
        sent = self._run(self._update("/start igc-channel"))
        self.assertTrue(sent.texts())
        self.assertIn("SpinHire", sent.texts()[0])
        actions = {b.get("callback_data") for b in sent.buttons()}
        self.assertTrue({"cats", "geos", "top", "fresh", "cv"} <= actions)
        with SessionLocal() as db:
            chat = db.query(jobbot.BotChat).filter_by(chat_id=self.chat_id).first()
            self.assertEqual(chat.source, "igc-channel")
            self.assertEqual(chat.lang, "ru")

    def test_menu_walks_to_jobs_without_typing(self):
        """Кнопками: меню → направления → вакансии в направлении → отклик."""
        self._run(self._update("/start"))
        cats = self._run(self._update(data="cats"))
        picks = [b for b in cats.buttons() if b.get("callback_data", "").startswith("c:")]
        self.assertTrue(picks)
        self.assertTrue(any("(" in b["text"] for b in picks))   # с числом вакансий
        jobs = self._run(self._update(data=picks[0]["callback_data"]))
        self.assertTrue(any(b.get("callback_data", "").startswith("a:")
                            for b in jobs.buttons()))
        with SessionLocal() as db:
            chat = db.query(jobbot.BotChat).filter_by(chat_id=self.chat_id).first()
            self.assertTrue(chat.query.startswith("cat:"))

    def test_top_salaries_are_actually_paid(self):
        """«Топ зарплат» показывает только вакансии с вилкой, по убыванию."""
        with SessionLocal() as db:
            rows, exact, _spec = jobbot.slice_rows(db, "top")
        self.assertTrue(exact)
        self.assertTrue(all(r["usd"] for r in rows[:20]))
        self.assertGreaterEqual(rows[0]["usd"], rows[10]["usd"])

    def test_country_menu_offers_real_places(self):
        with SessionLocal() as db:
            pairs = jobbot.geo_counts(db)
        self.assertTrue(pairs)
        self.assertTrue(all(count > 0 for _name, count in pairs))
        self.assertNotIn("Не указана", [name for name, _c in pairs])

    def test_search_shows_cards_with_apply_button(self):
        """Карточки приходят с откликом в один тап и кнопкой подписки."""
        sent = self._run(self._update("биздев"))
        text = " ".join(sent.texts())
        self.assertIn("нашёл", text)
        buttons = sent.buttons()
        self.assertTrue(any(b.get("callback_data", "").startswith("a:") for b in buttons))
        self.assertTrue(any(b.get("callback_data") == "s:1" for b in buttons))
        self.assertTrue(any("/job/" in (b.get("url") or "") for b in buttons))

    def test_apply_without_cv_asks_for_it(self):
        self._run(self._update("биздев"))
        sent = self._run(self._update(data=f"a:{self.bd_id}"))
        self.assertIn("резюме", " ".join(sent.texts()).lower())
        with SessionLocal() as db:
            chat = db.query(jobbot.BotChat).filter_by(chat_id=self.chat_id).first()
            self.assertEqual(chat.state, "cv")
            self.assertEqual(chat.pending_job, self.bd_id)
            self.assertEqual(db.query(Application).filter_by(job_id=self.bd_id).count(), 0)

    def test_cv_text_completes_the_pending_application(self):
        """Резюме текстом → аккаунт, профиль и отклик без единого перехода на сайт."""
        self._run(self._update("биздев"))
        self._run(self._update(data=f"a:{self.bd_id}"))
        cv = ("Business Development Manager. " + "Опыт 7 лет в iGaming: " * 12 +
              "Sales, Affiliate, CRM, English, Russian.")
        sent = self._run(self._update(cv))
        with SessionLocal() as db:
            chat = db.query(jobbot.BotChat).filter_by(chat_id=self.chat_id).first()
            self.assertIsNotNone(chat.user_id)
            user = db.get(User, chat.user_id)
            self.assertTrue(user.email.endswith("@" + jobbot.TG_ACCOUNT_DOMAIN))
            self.assertEqual(user.signup_source, "telegram-bot")
            resume = db.query(Resume).filter_by(user_id=user.id).first()
            self.assertTrue(resume.title)
            self.assertEqual(resume.contact_telegram, f"@user{self.suffix}")
            application = db.query(Application).filter_by(job_id=self.bd_id,
                                                          user_id=user.id).first()
            self.assertIsNotNone(application)
            self.assertEqual(chat.state, "")
            self.assertIsNone(chat.pending_job)
        self.assertIn("Отклик отправлен", " ".join(sent.texts()))
        self.assertTrue(any("/tg/login/" in (b.get("url") or "") for b in sent.buttons()))

    def test_login_link_is_single_use(self):
        with SessionLocal() as db:
            user = User(email=f"tg{self.chat_id}@{jobbot.TG_ACCOUNT_DOMAIN}",
                        password_hash="x", role="talent")
            db.add(user)
            db.flush()
            link = jobbot.login_link(db, user)
            db.commit()
            token = link.rsplit("/", 1)[-1]
            row = db.query(jobbot.BotLogin).filter_by(token=token).first()
            self.assertFalse(row.used)
            row.used = True
            db.commit()
            db.query(jobbot.BotLogin).filter_by(token=token).delete()
            db.query(User).filter_by(id=user.id).delete()
            db.commit()

    def test_no_mail_to_telegram_accounts(self):
        """Служебный ящик не должен получать писем: bounce бьёт по домену отправителя."""
        self.assertFalse(resend_send(f"tg1@{jobbot.TG_ACCOUNT_DOMAIN}", "x", "<p>x</p>"))

    # ---------- подписка ----------

    def test_subscription_pushes_only_fresh_jobs(self):
        self._run(self._update("биздев"))
        self._run(self._update(data="s:1"))
        with SessionLocal() as db:
            chat = db.query(jobbot.BotChat).filter_by(chat_id=self.chat_id).first()
            self.assertEqual(chat.sub, 1)
            self.assertEqual(chat.sub_query, "биздев")
            # подписка только что оформлена — свежего ещё нет
            chat.sub_last = (datetime.utcnow() - timedelta(days=2)).isoformat()
            db.commit()
        jobbot._index_cache.update(at=0.0, rows=[])
        sent = Sent()
        with patch.object(jobbot, "api", sent.api), SessionLocal() as db:
            stats = jobbot.push_pending(db)
        self.assertEqual(stats["sent"], 1)
        self.assertIn("Новое по", " ".join(sent.texts()))

    # ---------- вебхук ----------

    def test_webhook_rejects_wrong_secret(self):
        from fastapi.testclient import TestClient
        from server.app import app
        with patch.object(jobbot, "TOKEN", "test:token"), \
                patch.object(jobbot, "SECRET", "s" * 32), TestClient(app) as client:
            resp = client.post("/tg/jobbot/nonsense", json={"update_id": 1})
        self.assertEqual(resp.status_code, 404)

    def test_webhook_accepts_update_and_opens_chat(self):
        from fastapi.testclient import TestClient
        from server.app import app
        # токен читается из окружения при импорте: в общем прогоне server.app
        # мог подняться раньше нашего модуля, поэтому задаём его явно
        secret, sent = "s" * 32, Sent()
        with patch.object(jobbot, "api", sent.api), patch.object(jobbot, "TOKEN", "test:token"), \
                patch.object(jobbot, "SECRET", secret), TestClient(app) as client:
            resp = client.post(f"/tg/jobbot/{secret}", json=self._update("/start"),
                               headers={"X-Telegram-Bot-Api-Secret-Token": secret})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"ok": True})
        with SessionLocal() as db:
            self.assertIsNotNone(db.query(jobbot.BotChat).filter_by(chat_id=self.chat_id).first())

    def test_push_skips_quiet_subscriber(self):
        self._run(self._update("биздев"))
        self._run(self._update(data="s:1"))
        sent = Sent()
        with patch.object(jobbot, "api", sent.api), SessionLocal() as db:
            stats = jobbot.push_pending(db)
        self.assertEqual(stats["sent"], 0)


if __name__ == "__main__":
    unittest.main()
