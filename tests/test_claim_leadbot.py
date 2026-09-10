import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from server.app import (Application, Base, Job, Resume, SessionLocal, User, app,
                        engine, migrate)
from server import claim, leadbot  # noqa: E402 — только после server.app (циклический импорт)


def _job(company="Test Casino Ltd", title="VIP Manager", description="Great role"):
    return Job(title=title, company_name=company, description=description,
               location="Limassol", status="approved", category="VIP", owner_id=None)


class ClaimFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            migrate(db)

    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.company = f"Claim Test {self.suffix} Ltd"
        with SessionLocal() as db:
            job = _job(company=self.company)
            talent = User(email=f"talent-{self.suffix}@test.invalid", role="talent",
                          name="Кандидат Тестов", password_hash="x")
            db.add_all([job, talent])
            db.flush()
            db.add(Resume(user_id=talent.id, title="VIP Manager", about="a" * 120,
                          skills="VIP, CRM", experience_years=5, status="approved",
                          published=True))
            db.add(Application(job_id=job.id, user_id=talent.id, cover="hi"))
            db.commit()
            self.job_id, self.talent_id = job.id, talent.id

    def tearDown(self):
        with SessionLocal() as db:
            db.query(Application).filter_by(job_id=self.job_id).delete()
            db.query(Job).filter_by(id=self.job_id).delete()
            db.query(Resume).filter_by(user_id=self.talent_id).delete()
            db.query(User).filter_by(id=self.talent_id).delete()
            row = db.query(claim.CompanyClaim).filter_by(
                company_slug=claim.slugify_company(self.company)).first()
            if row:
                db.query(User).filter_by(id=row.user_id).delete()
                db.delete(row)
            db.commit()

    def test_claim_page_and_registration_hand_over_jobs(self):
        with SessionLocal() as db:
            row = claim.get_or_create_claim(db, self.company, "ru")
            db.commit()
            token = row.token
        email = f"hr-{self.suffix}@test.invalid"
        with TestClient(app) as client:
            page = client.get(f"/claim/{token}")
            self.assertEqual(page.status_code, 200)
            self.assertIn(self.company, page.text)
            done = client.post(f"/claim/{token}",
                               data={"email": email, "password": "secret-pass", "name": "HR"},
                               follow_redirects=False)
            self.assertEqual(done.status_code, 303)
            # кабинет компании: вакансия своя, а кандидат — под замком
            cabinet = client.get("/employer")
            self.assertIn("VIP Manager", cabinet.text)
            self.assertIn("Открыть контакт", cabinet.text)
            self.assertNotIn(f"talent-{self.suffix}@test.invalid", cabinet.text)
            with SessionLocal() as db:
                app_id = db.query(Application).filter_by(job_id=self.job_id).one().id
            card = client.get(f"/employer/application/{app_id}")
            self.assertIn("Резюме без контактов", card.text)
            self.assertNotIn(f"talent-{self.suffix}@test.invalid", card.text)
            paid = client.post(f"/employer/app/{app_id}/unlock", follow_redirects=False)
            self.assertEqual(paid.status_code, 303)
            self.assertIn("need_plan", paid.headers["location"])   # нет открытий — не отдали
        with SessionLocal() as db:
            owner = db.query(User).filter_by(email=email).one()
            self.assertEqual(owner.role, "employer")
            job = db.get(Job, self.job_id)
            self.assertEqual(job.owner_id, owner.id)          # вакансия отдана бесплатно
            application = db.query(Application).filter_by(job_id=self.job_id).one()
            self.assertEqual(application.lead_locked, 1)      # контакт остаётся платным
            self.assertIsNotNone(db.query(claim.CompanyClaim).filter_by(
                company_slug=claim.slugify_company(self.company)).one().used_at)

    def test_claim_link_is_stable_for_the_same_company(self):
        with SessionLocal() as db:
            first = claim.get_or_create_claim(db, self.company, "en")
            db.commit()
            again = claim.get_or_create_claim(db, self.company, "en")
            self.assertEqual(first.token, again.token)


class LeadbotTextTests(unittest.TestCase):
    def test_company_lang_follows_cyrillic_and_offices(self):
        self.assertEqual(leadbot.company_lang(
            [SimpleNamespace(title="VIP-менеджер", company_name="X", description="",
                             location="Remote")]), "ru")
        self.assertEqual(leadbot.company_lang(
            [SimpleNamespace(title="VIP Manager", company_name="X", description="",
                             location="Limassol, Cyprus")]), "ru")
        self.assertEqual(leadbot.company_lang(
            [SimpleNamespace(title="VIP Manager", company_name="X", description="",
                             location="Malta")]), "en")

    def test_hr_text_matches_the_agreed_script(self):
        items = [{"card": {"title": "VIP Manager", "facts": ["5 yrs"], "skills": ["CRM"],
                           "about": "about"},
                  "job": SimpleNamespace(title="VIP Manager")}]
        ru = leadbot.build_hr_text("Test Ltd", items, "ru")
        self.assertIn("Добрый день", ru)
        self.assertIn("SpinHire", ru)
        self.assertIn("пройти регистрацию", ru)
        self.assertIn("VIP Manager", ru)
        en = leadbot.build_hr_text("Test Ltd", items, "en")
        self.assertIn("applied to your job", en)

    def test_link_text_carries_link_and_price(self):
        text = leadbot.build_link_text("Test Ltd", "https://spinhire.io/claim/abc", 12, "ru")
        self.assertIn("https://spinhire.io/claim/abc", text)
        self.assertIn("12", text)
        self.assertIn("€5", text)

    def test_emails_are_filtered_to_the_company_domain(self):
        page = ('hello hr@acme.com, sales@acme.com, spam@example.com, '
                'noreply@sentry.io, logo@2x.png')
        self.assertEqual(leadbot._emails_from(page, "acme.com"),
                         ["hr@acme.com", "sales@acme.com"])

    def test_find_hr_caches_and_prefers_site_emails(self):
        with SessionLocal() as db:
            slug = "hrsearch-" + uuid.uuid4().hex[:8]
            name = slug.replace("-", " ")
            job = SimpleNamespace(source_url="https://boards.greenhouse.io/x/jobs/1")
            with patch.object(leadbot, "_get", return_value="write to careers@acme.io"), \
                 patch.object(leadbot, "company_domain", return_value="acme.io"):
                found = leadbot.find_hr(db, name, [job])
            self.assertIn("careers@acme.io", found["emails"])
            self.assertIn("linkedin.com", found["linkedin"])
            db.query(leadbot.CompanyHr).filter_by(
                company_slug=leadbot.slugify_company(name)).delete()
            db.commit()


if __name__ == "__main__":
    unittest.main()
