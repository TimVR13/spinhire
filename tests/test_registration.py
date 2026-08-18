import unittest
import uuid

from fastapi.testclient import TestClient

from server.app import Base, SIGNUP_COIN_BONUS, SessionLocal, User, app, engine, migrate


class RegistrationBonusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            migrate(db)

    def test_new_account_receives_signup_coins(self):
        email = f"signup-{uuid.uuid4().hex}@test.invalid"
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/register",
                    data={"email": email, "password": "test-pass", "name": "New Talent",
                          "role": "talent"},
                    follow_redirects=False,
                )
            self.assertEqual(response.status_code, 303)
            with SessionLocal() as db:
                user = db.query(User).filter_by(email=email).one()
                self.assertEqual(user.coins, SIGNUP_COIN_BONUS)
        finally:
            with SessionLocal() as db:
                db.query(User).filter_by(email=email).delete()
                db.commit()


if __name__ == "__main__":
    unittest.main()
