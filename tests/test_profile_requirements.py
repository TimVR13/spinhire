import os
import unittest
import uuid

from fastapi.testclient import TestClient

from server.app import (AVATAR_UPLOAD_DIR, Base, Resume, SessionLocal, User, app, engine,
                        hash_pw, migrate, signer, valid_avatar_payload)


class ProfileRequirementsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            migrate(db)

    def setUp(self):
        self.email = f"profile-{uuid.uuid4().hex}@test.invalid"
        with SessionLocal() as db:
            user = User(email=self.email, password_hash=hash_pw("test-pass"),
                        name="Profile Test", role="talent")
            db.add(user)
            db.commit()
            self.user_id = user.id

    def tearDown(self):
        with SessionLocal() as db:
            db.query(Resume).filter_by(user_id=self.user_id).delete()
            db.query(User).filter_by(id=self.user_id).delete()
            db.commit()

    def client(self):
        client = TestClient(app)
        client.cookies.set("sh_session", signer.dumps({"uid": self.user_id}))
        return client

    def test_publish_and_consent_are_required_by_server(self):
        with self.client() as client:
            response = client.post("/profile/resume", data={"title": "CRM Lead", "about": "Опыт"},
                                   follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn("cv_error=consent", response.headers["location"])

    def test_avatar_is_required_before_resume_can_be_saved(self):
        with self.client() as client:
            response = client.post("/profile/resume", data={"title": "CRM Lead", "about": "Опыт",
                                   "publish": "1", "consent": "1"}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn("cv_error=avatar", response.headers["location"])

    def test_avatar_magic_bytes_are_checked(self):
        self.assertTrue(valid_avatar_payload(b"\x89PNG\r\n\x1a\nrest", ".png"))
        self.assertTrue(valid_avatar_payload(b"\xff\xd8\xffrest", ".jpg"))
        self.assertFalse(valid_avatar_payload(b"not an image", ".png"))

    def test_avatar_is_hidden_until_contact_access(self):
        os.makedirs(AVATAR_UPLOAD_DIR, exist_ok=True)
        path = os.path.join(AVATAR_UPLOAD_DIR, f"test-{self.user_id}.png")
        try:
            with open(path, "wb") as handle:
                handle.write(b"\x89PNG\r\n\x1a\nrest")
            with SessionLocal() as db:
                user = db.get(User, self.user_id)
                user.avatar_file_name = "avatar.png"
                user.avatar_file_path = path
                resume = Resume(user_id=self.user_id, title="CRM Lead", about="Опыт",
                                published=True, status="approved")
                db.add(resume)
                db.commit()
                resume_id = resume.id
            with TestClient(app) as anonymous:
                self.assertEqual(anonymous.get(f"/resume/{resume_id}/avatar").status_code, 404)
            with self.client() as owner:
                self.assertEqual(owner.get(f"/resume/{resume_id}/avatar").status_code, 200)
        finally:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    unittest.main()
