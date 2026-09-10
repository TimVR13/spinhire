import unittest

from fastapi.testclient import TestClient

from server.app import (Base, Order, PLANS, PLAN_CV_CREDITS, ResumeCreditLedger, SessionLocal,
                        User, app, engine, hash_pw, migrate, signer)


class PricingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            migrate(db)

    def setUp(self):
        with SessionLocal() as db:
            employer = User(email="pricing-employer@test.invalid", password_hash=hash_pw("test"),
                            name="Pricing Employer", role="employer", cv_credits=0)
            admin = User(email="pricing-admin@test.invalid", password_hash=hash_pw("test"),
                         name="Pricing Admin", role="admin")
            db.add_all([employer, admin])
            db.commit()
            self.employer_id = employer.id
            self.admin_id = admin.id

    def tearDown(self):
        with SessionLocal() as db:
            order_ids = [row[0] for row in db.query(Order.id).filter_by(user_id=self.employer_id).all()]
            if order_ids:
                db.query(ResumeCreditLedger).filter(
                    ResumeCreditLedger.order_id.in_(order_ids)).delete(synchronize_session=False)
                db.query(Order).filter(Order.id.in_(order_ids)).delete(synchronize_session=False)
            db.query(User).filter(User.id.in_([self.employer_id, self.admin_id])).delete(
                synchronize_session=False)
            db.commit()

    def test_prices_and_contact_rate(self):
        """Цены выровнены по рынку, а пакеты дешевле поштучной покупки — иначе они бессмысленны."""
        self.assertEqual(PLANS["single"][1], 49)
        self.assertEqual(PLANS["featured"][1], 99)
        self.assertEqual(PLANS["cv1"][1], 5)
        self.assertEqual(PLANS["cv10"][1], 45)
        self.assertEqual(PLANS["cv30"][1], 120)
        self.assertNotIn("cv40", PLANS)   # пакет cv40 заменили на cv30

    def test_contact_packs_get_cheaper_per_opening(self):
        """Чем больше пакет, тем дешевле одно открытие — и для обычных, и для C-level."""
        per_credit = [PLANS[key][1] / PLAN_CV_CREDITS[key]
                      for key in ("cv1", "cv10", "cvc5", "cv30", "cvc10")]
        self.assertEqual(per_credit, sorted(per_credit, reverse=True))
        self.assertEqual(PLAN_CV_CREDITS["cvc1"], 5)      # один C-level контакт = 5 открытий
        self.assertEqual(PLANS["cvc1"][1], PLANS["cv1"][1] * 5)
        for pack, single in (("cvc5", 5), ("cvc10", 10)):
            self.assertLess(PLANS[pack][1], PLANS["cvc1"][1] * single)

    def test_one_contact_order_grants_one_credit_once(self):
        # один TestClient на тест: MCP-сессия поднимается один раз за процесс
        with TestClient(app) as client:
            client.cookies.set("sh_session", signer.dumps({"uid": self.employer_id}))
            response = client.post("/checkout/cv1", follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            with SessionLocal() as db:
                order = db.query(Order).filter_by(user_id=self.employer_id, plan="cv1").one()
                self.assertEqual(order.amount, 5)
                order_id = order.id
            client.cookies.set("sh_session", signer.dumps({"uid": self.admin_id}))
            self.assertEqual(client.post(
                f"/admin/order/{order_id}/paid", follow_redirects=False).status_code, 303)
            self.assertEqual(client.post(
                f"/admin/order/{order_id}/paid", follow_redirects=False).status_code, 303)
        with SessionLocal() as db:
            self.assertEqual(db.get(User, self.employer_id).cv_credits, 1)
            ledger = db.query(ResumeCreditLedger).filter_by(order_id=order_id).one()
            self.assertEqual(ledger.delta, 1)

    def test_pending_order_can_be_cancelled_by_owner_and_only_once(self):
        """Отмена закрывает счёт, повторная отмена и отмена чужого заказа невозможны."""
        with TestClient(app) as client:
            client.cookies.set("sh_session", signer.dumps({"uid": self.employer_id}))
            self.assertEqual(client.post("/checkout/cv10", follow_redirects=False).status_code, 303)
            with SessionLocal() as db:
                order_id = db.query(Order).filter_by(user_id=self.employer_id, plan="cv10").one().id
            self.assertEqual(client.post(f"/checkout/order/{order_id}/cancel", data={"back": "cabinet"},
                                         follow_redirects=False).status_code, 303)
            with SessionLocal() as db:
                self.assertEqual(db.get(Order, order_id).status, "cancelled")
            self.assertEqual(client.post(f"/checkout/order/{order_id}/cancel",
                                         follow_redirects=False).status_code, 409)
            client.cookies.delete("sh_session")
            self.assertEqual(client.post(f"/checkout/order/{order_id}/cancel",
                                         follow_redirects=False).status_code, 403)


if __name__ == "__main__":
    unittest.main()
