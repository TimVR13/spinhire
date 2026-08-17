import os
import unittest

from fastapi.testclient import TestClient

from server.app import (Application, Base, CompanyInvite, CompanyMember, CV_UPLOAD_DIR, Job,
                        Notification, Resume, ResumeUnlock, SessionLocal, User,
                        anonymize_resume_text, app, engine, hash_pw, migrate, signer)


class ResumePrivacyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            migrate(db)

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
                            status="approved",
                            consent_at="2026-08-17T00:00:00Z")
            db.add(resume)
            db.commit()
            self.candidate_id = candidate.id
            self.employer_id = employer.id
            self.resume_id = resume.id

    def tearDown(self):
        with SessionLocal() as db:
            resume = db.get(Resume, self.resume_id)
            if resume and resume.cv_file_path:
                try:
                    os.remove(resume.cv_file_path)
                except FileNotFoundError:
                    pass
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
            repeated = client.post(f"/resume/{self.resume_id}/unlock", follow_redirects=True)
            self.assertEqual(repeated.status_code, 200)
        with SessionLocal() as db:
            employer = db.get(User, self.employer_id)
            self.assertEqual(employer.cv_credits, 0)
            self.assertEqual(db.query(ResumeUnlock).filter_by(
                employer_id=self.employer_id, resume_id=self.resume_id).count(), 1)

    def test_pending_resume_is_not_public(self):
        with SessionLocal() as db:
            resume = db.get(Resume, self.resume_id)
            resume.status = "pending"
            db.commit()
        with TestClient(app) as client:
            listing = client.get("/resumes")
            detail = client.get(f"/resume/{self.resume_id}")
            self.assertNotIn("CRM Manager", listing.text)
            self.assertEqual(detail.status_code, 404)

    def test_contacts_are_removed_from_public_description(self):
        public = anonymize_resume_text(
            "Write to private@test.invalid, @private_handle or +48 555 111 222. "
            "Portfolio https://example.com/me")
        self.assertNotIn("private@test.invalid", public)
        self.assertNotIn("@private_handle", public)
        self.assertNotIn("555 111 222", public)
        self.assertNotIn("example.com", public)

    def test_uploaded_cv_requires_paid_access(self):
        os.makedirs(CV_UPLOAD_DIR, exist_ok=True)
        path = os.path.join(CV_UPLOAD_DIR, f"test-{self.resume_id}.pdf")
        with open(path, "wb") as handle:
            handle.write(b"%PDF-1.4 private candidate document")
        with SessionLocal() as db:
            resume = db.get(Resume, self.resume_id)
            resume.cv_file_name = "candidate.pdf"
            resume.cv_file_path = path
            db.commit()

        with TestClient(app) as client:
            self.assertEqual(client.get(f"/resume/{self.resume_id}/file").status_code, 404)
            client.cookies.set("sh_session", signer.dumps({"uid": self.employer_id}))
            self.assertEqual(client.get(f"/resume/{self.resume_id}/file").status_code, 404)
            client.post(f"/resume/{self.resume_id}/unlock")
            downloaded = client.get(f"/resume/{self.resume_id}/file")
            self.assertEqual(downloaded.status_code, 200)
            self.assertEqual(downloaded.content, b"%PDF-1.4 private candidate document")

    def test_paused_candidate_disappears_from_catalog(self):
        with SessionLocal() as db:
            candidate = db.get(User, self.candidate_id)
            candidate.job_search_status = "paused"
            db.commit()
        with TestClient(app) as client:
            self.assertNotIn("CRM Manager", client.get("/resumes").text)
            self.assertEqual(client.get(f"/resume/{self.resume_id}").status_code, 404)


class EmployerWorkflowTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            employer = User(email="workflow-employer@test.invalid", password_hash=hash_pw("test"),
                            role="employer", company_name="Test Casino")
            candidate = User(email="workflow-candidate@test.invalid", password_hash=hash_pw("test"),
                             role="talent", name="Candidate")
            outsider = User(email="workflow-outsider@test.invalid", password_hash=hash_pw("test"),
                            role="employer", company_name="Other")
            recruiter = User(email="workflow-recruiter@test.invalid", password_hash=hash_pw("test"),
                             role="employer", name="Recruiter")
            viewer = User(email="workflow-viewer@test.invalid", password_hash=hash_pw("test"),
                          role="employer", name="Viewer")
            db.add_all([employer, candidate, outsider, recruiter, viewer])
            db.flush()
            db.add_all([CompanyMember(account_id=employer.id, user_id=recruiter.id, role="recruiter"),
                        CompanyMember(account_id=employer.id, user_id=viewer.id, role="viewer")])
            job = Job(title="CRM Lead", company_name="Test Casino", category="Маркетинг и CRM",
                      salary="€4000–5000 net", description="Full description", owner_id=employer.id,
                      status="approved")
            db.add(job)
            db.flush()
            application = Application(job_id=job.id, user_id=candidate.id)
            db.add(application)
            db.commit()
            self.employer_id, self.candidate_id, self.outsider_id = employer.id, candidate.id, outsider.id
            self.recruiter_id, self.viewer_id = recruiter.id, viewer.id
            self.job_id, self.application_id = job.id, application.id

    def tearDown(self):
        with SessionLocal() as db:
            db.query(CompanyInvite).filter_by(account_id=self.employer_id).delete()
            db.query(CompanyMember).filter_by(account_id=self.employer_id).delete()
            db.query(Notification).filter_by(user_id=self.candidate_id).delete()
            db.query(Application).filter_by(id=self.application_id).delete()
            db.query(Job).filter_by(id=self.job_id).delete()
            db.query(User).filter(User.id.in_([
                self.employer_id, self.candidate_id, self.outsider_id,
                self.recruiter_id, self.viewer_id])).delete(
                    synchronize_session=False)
            db.commit()

    def test_status_change_creates_candidate_notification(self):
        with TestClient(app) as client:
            client.cookies.set("sh_session", signer.dumps({"uid": self.employer_id}))
            response = client.post(f"/employer/app/{self.application_id}/status",
                                   data={"status": "offer"}, follow_redirects=False)
            self.assertEqual(response.status_code, 303)
        with SessionLocal() as db:
            application = db.get(Application, self.application_id)
            notice = db.query(Notification).filter_by(user_id=self.candidate_id).one()
            self.assertEqual(application.status, "offer")
            self.assertEqual(notice.title, "Вам сделали оффер")

    def test_only_owner_can_edit_and_archive_job(self):
        with TestClient(app) as client:
            client.cookies.set("sh_session", signer.dumps({"uid": self.outsider_id}))
            self.assertEqual(client.get(f"/employer/job/{self.job_id}/edit").status_code, 404)
            client.cookies.set("sh_session", signer.dumps({"uid": self.employer_id}))
            edited = client.post(f"/employer/job/{self.job_id}/edit", data={
                "title": "Senior CRM Lead", "category": "Маркетинг и CRM",
                "location": "Malta", "fmt": "гибрид", "salary": "€5000–6000 net",
                "tags": "CRM, retention", "description": "Updated full description",
            }, follow_redirects=False)
            self.assertEqual(edited.status_code, 303)
            archived = client.post(f"/employer/job/{self.job_id}/archive", follow_redirects=False)
            self.assertEqual(archived.status_code, 303)
        with SessionLocal() as db:
            job = db.get(Job, self.job_id)
            self.assertEqual(job.title, "Senior CRM Lead")
            self.assertEqual(job.status, "archived")
            self.assertTrue(job.closed_at)

    def test_recruiter_shares_jobs_but_viewer_cannot_mutate(self):
        with TestClient(app) as client:
            client.cookies.set("sh_session", signer.dumps({"uid": self.recruiter_id}))
            dashboard = client.get("/employer")
            self.assertEqual(dashboard.status_code, 200)
            self.assertIn("CRM Lead", dashboard.text)
            changed = client.post(f"/employer/app/{self.application_id}/status",
                                  data={"status": "invited"}, follow_redirects=False)
            self.assertEqual(changed.status_code, 303)
            client.cookies.set("sh_session", signer.dumps({"uid": self.viewer_id}))
            forbidden = client.post(f"/employer/app/{self.application_id}/status",
                                    data={"status": "rejected"}, follow_redirects=False)
            self.assertEqual(forbidden.status_code, 403)

    def test_invite_is_email_bound_and_accepts_existing_user(self):
        raw_token = "workflow-invite-token"
        with SessionLocal() as db:
            db.add(CompanyInvite(account_id=self.employer_id, invited_by=self.employer_id,
                                 email="workflow-outsider@test.invalid", role="viewer",
                                 token_hash=__import__("hashlib").sha256(raw_token.encode()).hexdigest(),
                                 expires_at="2099-01-01T00:00:00"))
            db.commit()
        with TestClient(app) as client:
            client.cookies.set("sh_session", signer.dumps({"uid": self.recruiter_id}))
            self.assertEqual(client.get(f"/employer/invite/{raw_token}/accept").status_code, 403)
            client.cookies.set("sh_session", signer.dumps({"uid": self.outsider_id}))
            accepted = client.get(f"/employer/invite/{raw_token}/accept", follow_redirects=False)
            self.assertEqual(accepted.status_code, 303)
        with SessionLocal() as db:
            membership = db.query(CompanyMember).filter_by(user_id=self.outsider_id).one()
            self.assertEqual(membership.account_id, self.employer_id)
            self.assertEqual(membership.role, "viewer")

    def test_recruiter_uses_shared_cv_balance_and_unlock(self):
        with SessionLocal() as db:
            owner = db.get(User, self.employer_id)
            owner.cv_credits = 1
            resume = Resume(user_id=self.candidate_id, title="VIP Manager", about="Casino CRM",
                            contact_email="shared-candidate@test.invalid", published=True,
                            status="approved", consent_at="2026-08-17T00:00:00Z")
            db.add(resume)
            db.commit()
            resume_id = resume.id
        try:
            with TestClient(app) as client:
                client.cookies.set("sh_session", signer.dumps({"uid": self.recruiter_id}))
                unlocked = client.post(f"/resume/{resume_id}/unlock", follow_redirects=False)
                self.assertEqual(unlocked.status_code, 303)
                detail = client.get(f"/resume/{resume_id}")
                self.assertIn("shared-candidate@test.invalid", detail.text)
            with SessionLocal() as db:
                self.assertEqual(db.get(User, self.employer_id).cv_credits, 0)
                self.assertEqual(db.query(ResumeUnlock).filter_by(
                    employer_id=self.employer_id, resume_id=resume_id).count(), 1)
        finally:
            with SessionLocal() as db:
                db.query(ResumeUnlock).filter_by(resume_id=resume_id).delete()
                db.query(Resume).filter_by(id=resume_id).delete()
                db.commit()


if __name__ == "__main__":
    unittest.main()
