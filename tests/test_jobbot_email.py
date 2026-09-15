# -*- coding: utf-8 -*-
"""Бот: привязка рабочей почты к ТГ-аккаунту кодом из письма (15.09.2026)."""
import re
import unittest
import uuid

from server.app import AnalyticsEvent, Base, SessionLocal, User, engine, migrate
from server import app as web  # noqa: E402
from server import jobbot  # noqa: E402  — только после server.app (циклический импорт)


class TgEmailLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            migrate(db)

    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.chat_id = f"t{self.suffix}"
        self.sent, self.mails = [], []
        self._send, self._resend = jobbot.send, web.resend_send
        jobbot.send = lambda chat_id, text, keyboard=None: self.sent.append((text, keyboard or [])) or {"ok": True}
        web.resend_send = lambda to, subject, html: self.mails.append((to, subject)) or True

    def tearDown(self):
        jobbot.send, web.resend_send = self._send, self._resend
        with SessionLocal() as db:
            chat = db.query(jobbot.BotChat).filter_by(chat_id=self.chat_id).first()
            if chat and chat.user_id:
                db.query(jobbot.BotLogin).filter_by(user_id=chat.user_id).delete()
                db.query(AnalyticsEvent).filter_by(user_id=chat.user_id).delete()
                db.query(User).filter_by(id=chat.user_id).delete()
            db.query(jobbot.BotEvent).filter_by(chat_id=self.chat_id).delete()
            db.query(jobbot.BotChat).filter_by(chat_id=self.chat_id).delete()
            db.commit()

    def _chat(self, db):
        return db.query(jobbot.BotChat).filter_by(chat_id=self.chat_id).first()

    def test_email_confirmed_turns_tg_account_into_site_user(self):
        email = f"tg-link-{self.suffix}@test.invalid"
        with SessionLocal() as db:
            chat = jobbot.BotChat(chat_id=self.chat_id, lang="ru", first_name="Тест")
            db.add(chat)
            db.flush()
            # в меню есть кнопка почты, пока она не подтверждена
            self.assertTrue(any(b["callback_data"] == "email" for row in jobbot.menu_keyboard(chat) for b in row))
            jobbot.handle_callback(db, chat, "email")
            self.assertEqual(chat.state, "email")
            self.assertIn("рабочую почту", self.sent[-1][0])
            user = db.get(User, chat.user_id)
            self.assertTrue(user.email.endswith("@" + web.TG_ACCOUNT_DOMAIN))

            jobbot.handle_text(db, chat, "это не почта")
            self.assertIn("не похоже", self.sent[-1][0])
            self.assertEqual(self.mails, [])

            jobbot.handle_text(db, chat, email.upper())
            self.assertEqual(chat.state, "email_code")
            self.assertEqual(chat.pending_email, email)
            self.assertEqual(self.mails[-1][0], email)
            code = re.search(r"\d{6}", self.mails[-1][1]).group(0)

            wrong = "000000" if code != "000000" else "111111"
            jobbot.handle_text(db, chat, wrong)
            self.assertIn("Неверный код", self.sent[-1][0])
            self.assertTrue(user.email.endswith("@" + web.TG_ACCOUNT_DOMAIN))

            jobbot.handle_text(db, chat, f"код {code[:3]} {code[3:]}")
            db.commit()
            user = db.get(User, chat.user_id)
            self.assertEqual(user.email, email)
            self.assertEqual(user.verified, 1)
            self.assertEqual(chat.pending_email, "ok")
            self.assertEqual(chat.state, "")
            self.assertIn("подтверждена", self.sent[-1][0])
            self.assertFalse(any(b["callback_data"] == "email" for row in jobbot.menu_keyboard(chat) for b in row))
            # с обычной почтой аккаунт — пользователь сайта, не ТГ
            self.assertFalse(db.query(User).filter(User.id == user.id, User.email.like(web.TG_EMAIL_LIKE)).first())

    def test_taken_email_is_refused(self):
        taken = f"taken-{self.suffix}@test.invalid"
        with SessionLocal() as db:
            other = User(email=taken, role="talent", name="Занято", password_hash="x", verified=1)
            chat = jobbot.BotChat(chat_id=self.chat_id, lang="en")
            db.add_all([other, chat])
            db.flush()
            try:
                jobbot.handle_callback(db, chat, "email")
                jobbot.handle_text(db, chat, taken)
                self.assertIn("already registered", self.sent[-1][0])
                self.assertEqual(self.mails, [])
                self.assertEqual(chat.state, "email")
            finally:
                db.query(User).filter_by(id=other.id).delete()
                db.commit()


if __name__ == "__main__":
    unittest.main()
