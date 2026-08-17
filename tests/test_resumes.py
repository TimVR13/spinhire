import unittest

from fastapi.testclient import TestClient

from server.app import (Base, Resume, ResumeUnlock, SessionLocal, User,
                        anonymize_resume_text, app, engine, hash_pw, signer)


class ResumePrivacyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(engine)

    def setUp(self):
        with SessionLocal() as db:
            candidate = User(email="privacy-candidate@test.invalid", password_hash=hash_pw("test"),
                             name="Hidden Candidate", role="talent")
            employer = User(email="privacy-employer@test.invalid", password_hash=hash_pw("test"),
                            name="Recruiter", role="employer", cv_credits=1)
            db.add_all([candidate, employer])
            db.flush()
            resume = Resume(user_id=candidate.id, title="CRM Manager", location="Warsaw",
                            experience_years=6, skills="CRM, Retention", about="iGaming experience",
                            contact_email="private-address@test.invalid", published=True,
                            consent_at="2026-08-17T00:00:00Z")
            db.add(resume)
            db.commit()
            self.candidate_id = candidate.id
            self.employer_id = employer.id
            self.resume_id = resume.id

    def tearDown(self):
        with SessionLocal() as db:
            db.query(ResumeUnlock).filter_by(resume_id=self.resume_id).delete()
            db.query(Resume).filter_by(id=self.resume_id).delete()
            db.query(User).filter(User.id.in_([self.candidate_id, self.employer_id])).delete(
                synchronize_session=False)
            db.commit()

    def test_contact_is_not_rendered_before_unlock(self):
        with TestClient(app) as client:
            client.cookies.set("sh_session", signer.dumps({"uid": self.employer_id}))
            locked = client.get(f"/resume/{self.resume_id}")
            self.assertEqual(locked.status_code, 200)
            self.assertNotIn("private-address@test.invalid", locked.text)

            unlocked = client.post(f"/resume/{self.resume_id}/unlock", follow_redirects=True)
            self.assertEqual(unlocked.status_code, 200)
            self.assertIn("private-address@test.invalid", unlocked.text)
        with SessionLocal() as db:
            employer = db.get(User, self.employer_id)
            self.assertEqual(employer.cv_credits, 0)
            self.assertEqual(db.query(ResumeUnlock).filter_by(
                employer_id=self.employer_id, resume_id=self.resume_id).count(), 1)

    def test_contacts_are_removed_from_public_description(self):
        public = anonymize_resume_text(
            "Write to private@test.invalid, @private_handle or +48 555 111 222. "
            "Portfolio https://example.com/me")
        self.assertNotIn("private@test.invalid", public)
        self.assertNotIn("@private_handle", public)
        self.assertNotIn("555 111 222", public)
        self.assertNotIn("example.com", public)


if __name__ == "__main__":
    unittest.main()
