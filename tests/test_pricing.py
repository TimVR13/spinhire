import unittest

from fastapi.testclient import TestClient

from server.app import (Base, Order, PLANS, ResumeCreditLedger, SessionLocal, User,
                        app, engine, hash_pw, migrate, signer)


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

    def test_discounted_prices_and_contact_rate(self):
        self.assertEqual(PLANS["single"][1], 99)
        self.assertEqual(PLANS["featured"][1], 199)
        self.assertEqual(PLANS["cv1"][1], 5)
        self.assertEqual(PLANS["cv10"][1], 50)
        self.assertEqual(PLANS["cv40"][1], 200)

    def test_one_contact_order_grants_one_credit_once(self):
        with TestClient(app) as client:
            client.cookies.set("sh_session", signer.dumps({"uid": self.employer_id}))
            response = client.post("/checkout/cv1", follow_redirects=False)
            self.assertEqual(response.status_code, 303)
        with SessionLocal() as db:
            order = db.query(Order).filter_by(user_id=self.employer_id, plan="cv1").one()
            self.assertEqual(order.amount, 5)
            order_id = order.id
        with TestClient(app) as client:
            client.cookies.set("sh_session", signer.dumps({"uid": self.admin_id}))
            self.assertEqual(client.post(
                f"/admin/order/{order_id}/paid", follow_redirects=False).status_code, 303)
            self.assertEqual(client.post(
                f"/admin/order/{order_id}/paid", follow_redirects=False).status_code, 303)
        with SessionLocal() as db:
            self.assertEqual(db.get(User, self.employer_id).cv_credits, 1)
            ledger = db.query(ResumeCreditLedger).filter_by(order_id=order_id).one()
            self.assertEqual(ledger.delta, 1)


if __name__ == "__main__":
    unittest.main()
