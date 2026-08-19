# -*- coding: utf-8 -*-
"""SpinHire backend: вакансии, отклики, кабинеты, админка.

Запуск:  uvicorn server.app:app --reload --port 8000
Сид:     при пустой базе создаёт админа и импортирует data/jobs.csv
"""
import csv
import hashlib
import html
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import bcrypt as _bcrypt
from itsdangerous import BadSignature, URLSafeSerializer
from starlette.exceptions import HTTPException as StarletteHTTPException


def hash_pw(pw: str) -> str:
    return _bcrypt.hashpw(pw.encode()[:72], _bcrypt.gensalt()).decode()


def check_pw(pw: str, h: str) -> bool:
    try:
        return _bcrypt.checkpw(pw.encode()[:72], h.encode())
    except ValueError:
        return False
from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer,
                        String, Text, UniqueConstraint, create_engine, func, or_)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "spinhire.db")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower()
SECRET = os.environ.get("SPINHIRE_SECRET", "spinhire-dev-secret-change-me")
ADMIN_EMAIL = os.environ.get("SPINHIRE_ADMIN_EMAIL", "admin@spinhire.io")
ADMIN_PASSWORD = os.environ.get("SPINHIRE_ADMIN_PASSWORD", "")
if ENVIRONMENT == "production" and (SECRET == "spinhire-dev-secret-change-me" or not ADMIN_PASSWORD):
    raise RuntimeError("Production requires SPINHIRE_SECRET and SPINHIRE_ADMIN_PASSWORD")

# ---- внешние интеграции (секреты только из окружения; пустые дефолты для локали) ----
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM = os.environ.get("RESEND_FROM", "")
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")
CV_UPLOAD_DIR = os.environ.get("CV_UPLOAD_DIR", os.path.join(ROOT, "data", "cv_uploads"))
CV_MAX_BYTES = 5 * 1024 * 1024
AVATAR_UPLOAD_DIR = os.environ.get("AVATAR_UPLOAD_DIR", os.path.join(ROOT, "data", "avatars"))
COMPANY_LOGO_DIR = os.environ.get("COMPANY_LOGO_DIR", os.path.join(ROOT, "data", "company-logos"))
AVATAR_MAX_BYTES = 3 * 1024 * 1024
SIGNUP_COIN_BONUS = 20
# Подтверждение почты включается автоматически, когда настроен Resend.
REQUIRE_VERIFY = bool(RESEND_API_KEY)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()
signer = URLSafeSerializer(SECRET, salt="session")

CATEGORIES = ["Операции казино", "Беттинг и трейдинг", "Разработка игр",
              "Аффилейты и медиабаинг", "Комплаенс и AML", "Платежи и антифрод",
              "Поддержка игроков", "Маркетинг и CRM", "Данные и BI", "Топ-менеджмент"]
FORMATS = ["офис", "гибрид", "удалёнка"]



def script_language(text: str):
    """Определить язык текста вакансии по алфавиту: украинский → русский → английский."""
    sample = (text or "")[:4000].lower()
    if re.search(r"[іїєґ]", sample):
        return ("uk", "Українська")
    if re.search(r"[а-яё]", sample):
        return ("ru", "Русский")
    return ("en", "English")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    name = Column(String, default="")
    role = Column(String, default="talent")  # talent | employer | admin
    company_name = Column(String, default="")
    headline = Column(String, default="")
    salary_expect = Column(String, default="")
    languages = Column(String, default="")
    location = Column(String, default="")
    job_search_status = Column(String, default="active")  # active | open | paused
    incognito = Column(Boolean, default=True)
    company_website = Column(String, default="")
    company_logo_path = Column(String, default="")
    company_description = Column(Text, default="")
    company_location = Column(String, default="")
    company_size = Column(String, default="")
    cv_credits = Column(Integer, default=0)         # оплаченные открытия контактов
    cv_access_until = Column(String, default="")   # ISO-дата безлимитного доступа
    job_credits = Column(Integer, default=0)        # оплаченные размещения вакансий
    job_access_until = Column(String, default="")  # ISO-дата безлимитного размещения
    coins = Column(Integer, default=0)              # SpinCoins на аккаунте
    avatar_file_name = Column(String, default="")
    avatar_file_path = Column(String, default="")
    last_spin = Column(DateTime, nullable=True)     # последний ежедневный фриспин
    verified = Column(Integer, default=1)           # 0 — ждём подтверждения почты; старые = 1
    otp_hash = Column(String, default="")           # хэш текущего кода подтверждения
    otp_expires = Column(String, default="")        # ISO-время истечения кода
    otp_attempts = Column(Integer, default=0)       # попыток ввода текущего кода
    created_at = Column(DateTime, default=datetime.utcnow)
    jobs = relationship("Job", back_populates="owner")
    applications = relationship("Application", back_populates="user",
                                foreign_keys="Application.user_id")


class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    company_name = Column(String, default="")
    category = Column(String, default="")
    location = Column(String, default="")
    fmt = Column(String, default="удалёнка")
    salary = Column(String, default="по запросу")
    tags = Column(String, default="")  # comma-separated
    description = Column(Text, default="")
    source_url = Column(String, default="")  # ссылка на первоисточник
    source = Column(String, default="")       # провенанс: '', 'greenhouse:betsson', 'csv'…
    ext_id = Column(String, default="")       # id вакансии в источнике — для дедупликации
    posted_at = Column(String, default="")    # реальная дата публикации в источнике (YYYY-MM-DD)
    deadline = Column(String, default="")     # дедлайн приёма (YYYY-MM-DD)
    closed_at = Column(String, default="")    # когда источник подтвердил исчезновение вакансии
    status = Column(String, default="pending")  # pending | approved | rejected | archived
    featured = Column(Boolean, default=False)
    views = Column(Integer, default=0)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User", back_populates="jobs")
    applications = relationship("Application", back_populates="job", cascade="all, delete-orphan")

    @property
    def language_list(self):
        """Языки работы из явных тегов и текста вакансии.

        Если язык нигде не назван, показываем язык, на котором написана сама
        вакансия: для кандидата это тоже сигнал, на каком языке идёт общение.
        """
        text_value = f"{self.title} {self.tags} {self.description}".lower()
        found = []
        for code, label, aliases in JOB_LANGUAGES:
            if any((re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", text_value)
                    if alias.isascii() else alias in text_value) for alias in aliases):
                found.append((code, label))
        return found or [script_language(f"{self.title} {self.description}")]

    @property
    def tag_list(self):
        """Обычные теги вакансии.

        Языки выводятся отдельными чипами через language_list, поэтому любой тег,
        который на самом деле является названием языка («Украинский», «English»,
        «Українська»), отсюда выбрасываем — иначе язык дублируется в карточке.
        """
        language_words = {label.lower() for _, label, _ in JOB_LANGUAGES}
        for _, _, aliases in JOB_LANGUAGES:
            language_words.update(alias.lower() for alias in aliases)
        out = []
        for tag in self.tags.split(","):
            tag = tag.strip()
            if not tag:
                continue
            low = tag.lower()
            if low in language_words or any(low.startswith(w) for w in language_words if len(w) > 4):
                continue
            out.append(tag)
        return out[:3]

    @property
    def has_salary(self):
        return any(c.isdigit() for c in (self.salary or ""))

    @property
    def _sal_nums(self):
        """Числа из строки вилки. Часовые ставки бывают дробными («18,25»)."""
        import re as _re
        nums = []
        for raw in _re.findall(r"\d[\d\u00a0\u202f ]*(?:,\d{1,2})?", self.salary or ""):
            cleaned = _re.sub(r"[^\d,]", "", raw).replace(",", ".")
            try:
                value = float(cleaned)
            except ValueError:
                continue
            if value > 0:
                nums.append(int(value) if value == int(value) else value)
        return nums

    @property
    def sal_min(self):
        n = self._sal_nums
        return min(n) if n else None

    @property
    def sal_max(self):
        n = self._sal_nums
        return max(n) if n else None

    @property
    def sal_unit(self):
        """Период вилки для JobPosting, либо None, если период не определить.

        Часть источников отдаёт вилку без периода («€50 000 – €85 000»).
        Считать такое месячным нельзя — в разметку уйдёт заведомая ложь,
        поэтому действует то же правило, что и в парсере описаний: до 10 000
        это месяц, от 20 000 — год, а промежуток честнее оставить без ответа.
        """
        text_value = self.salary or ""
        if "в час" in text_value:
            return "HOUR"
        if "в год" in text_value:
            return "YEAR"
        if "в месяц" in text_value:
            return "MONTH"
        nums = self._sal_nums
        if not nums:
            return "MONTH"
        if max(nums) < 10_000:
            return "MONTH"
        if min(nums) >= 20_000:
            return "YEAR"
        return None

    @property
    def sal_currency(self):
        s = self.salary or ""
        if "USDT" in s:
            return "USDT"
        if "$" in s:
            return "USD"
        return "EUR"

    @property
    def valid_through(self):
        """Дата, до которой вакансия считается актуальной — для JobPosting.

        Без validThrough Google Jobs держит объявление вечно и со временем
        понижает доверие ко всему фиду. Явный дедлайн есть редко, поэтому
        по умолчанию даём скользящее окно: краулер проверяет источники каждые
        6 часов и архивирует исчезнувшие, значит «живо ещё 30 дней» — честно.
        """
        if self.deadline:
            return self.deadline
        return (datetime.utcnow().date() + timedelta(days=30)).isoformat()

    @property
    def employment_type(self):
        """Тип занятости в терминах schema.org (enum Google Jobs)."""
        text_value = f"{self.title} {self.tags}".lower()
        if re.search(r"intern|стажёр|стажер|стажировк", text_value):
            return "INTERN"
        if re.search(r"part[- ]time|part_time|частичн", text_value):
            return "PART_TIME"
        if re.search(r"contract|freelance|b2b|фриланс|подряд", text_value):
            return "CONTRACTOR"
        if re.search(r"tempor|времен", text_value):
            return "TEMPORARY"
        return "FULL_TIME"

    @property
    def preview_description(self):
        """Описание для карточки ссылки — на языке самой вакансии.

        Карточку в ленте рисует робот соцсети: он приходит без браузера, и
        клиентский переключатель языка до него не доходит. Англоязычную
        вакансию с подписью «в год · офис» в англоязычной ленте принимают
        за чужой сайт, поэтому язык превью берём из текста самой вакансии.
        """
        lang, _ = script_language(f"{self.title} {self.description}")
        salary, fmt = self.salary or "", self.fmt or ""
        if lang == "en":
            for russian, english in ((" в год", "/year"), (" в час", "/hour"),
                                     (" в месяц", "/month"), ("по запросу", "on request"),
                                     ("от ", "from ")):
                salary = salary.replace(russian, english)
            fmt = {"удалёнка": "remote", "офис": "on-site",
                   "гибрид": "hybrid"}.get(fmt, fmt)
        return " · ".join(part for part in (salary, self.location, fmt) if part)

    @property
    def logo_url(self):
        """Фото/логотип компании через favicon-сервис по домену (если известен)."""
        if self.owner_id and self.owner and self.owner.company_logo_path:
            return f"/company-logo/{self.owner_id}"
        normalized = " ".join((self.company_name or "").lower().replace("_", " ").split())
        if normalized == "gr8 tech":
            return "/img/company-logos/gr8tech.png"
        dom = company_domain(self.company_name, self.source_url)
        return f"https://icons.duckduckgo.com/ip3/{dom}.ico" if dom else ""

    @property
    def company_slug(self):
        import re as _re
        s = _re.sub(r"[^a-zа-я0-9]+", "-", (self.company_name or "").lower()).strip("-")
        return s or "company"

    @property
    def company_site(self):
        domain = company_domain(self.company_name)
        return f"https://{domain}" if domain else ""

    @property
    def initials(self):
        import re as _re
        stop = {"оператор", "через", "для", "компания", "nda", "и", "the", "via",
                "под", "igaming", "оператора", "group", "ltd", "inc", "tech"}
        words = [w for w in _re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", self.company_name)
                 if w.lower() not in stop]
        if not words:
            words = _re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", self.company_name)
        if not words:
            return "SH"
        w = words[0]
        return (w[:2] if len(w) >= 2 else w[0]).upper()


class Application(Base):
    __tablename__ = "applications"
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    cover = Column(Text, default="")
    status = Column(String, default="new")  # new | viewed | invited | offer | hired | rejected
    employer_note = Column(Text, default="")
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    interview_at = Column(String, default="")
    next_action_at = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    job = relationship("Job", back_populates="applications")
    user = relationship("User", back_populates="applications", foreign_keys=[user_id])


class Resume(Base):
    __tablename__ = "resumes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    title = Column(String, default="")
    location = Column(String, default="")
    experience_years = Column(Integer, default=0)
    skills = Column(Text, default="")
    about = Column(Text, default="")
    desired_format = Column(String, default="удалёнка")
    salary_expect = Column(String, default="")
    languages = Column(String, default="")
    contact_email = Column(String, default="")
    contact_telegram = Column(String, default="")
    cv_file_name = Column(String, default="")
    cv_file_path = Column(String, default="")
    employment_history = Column(Text, default="")
    education = Column(Text, default="")
    preferred_locations = Column(String, default="")
    relocation = Column(Boolean, default=False)
    availability = Column(String, default="")
    portfolio_url = Column(String, default="")
    linkedin_url = Column(String, default="")
    published = Column(Boolean, default=False)
    status = Column(String, default="draft")  # draft | pending | approved | rejected | paused
    moderation_note = Column(String, default="")
    consent_at = Column(String, default="")
    submitted_at = Column(String, default="")
    views = Column(Integer, default=0)
    unlock_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User")

    @property
    def public_code(self):
        return f"CV-{self.id:06d}"

    @property
    def skill_list(self):
        return [s.strip() for s in self.skills.split(",") if s.strip()][:8]


class ResumeUnlock(Base):
    __tablename__ = "resume_unlocks"
    __table_args__ = (UniqueConstraint("employer_id", "resume_id", name="uq_resume_unlock"),)
    id = Column(Integer, primary_key=True)
    employer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    resume_id = Column(Integer, ForeignKey("resumes.id"), nullable=False)
    access_kind = Column(String, default="credit")  # credit | unlimited | admin
    created_at = Column(DateTime, default=datetime.utcnow)


class ResumeCreditLedger(Base):
    __tablename__ = "resume_credit_ledger"
    id = Column(Integer, primary_key=True)
    employer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    resume_id = Column(Integer, ForeignKey("resumes.id"), nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    delta = Column(Integer, default=0)
    balance_after = Column(Integer, default=0)
    action = Column(String, default="")  # purchase | unlock | unlimited
    created_at = Column(DateTime, default=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    kind = Column(String, default="info")
    title = Column(String, default="")
    body = Column(Text, default="")
    link = Column(String, default="")
    read_at = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class CompanyMember(Base):
    __tablename__ = "company_members"
    __table_args__ = (UniqueConstraint("user_id", name="uq_company_member_user"),)
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String, default="recruiter")  # recruiter | viewer
    created_at = Column(DateTime, default=datetime.utcnow)


class CompanyInvite(Base):
    __tablename__ = "company_invites"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    invited_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    email = Column(String, nullable=False)
    role = Column(String, default="recruiter")
    token_hash = Column(String, unique=True, nullable=False)
    status = Column(String, default="pending")  # pending | accepted | revoked
    expires_at = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class ApplicationEvent(Base):
    __tablename__ = "application_events"
    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    kind = Column(String, default="note")
    body = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)



class CompanyProfile(Base):
    """Публичная карточка работодателя: описание, сайт, карьерная страница, HQ.

    Заполняется краулером из открытых профилей агрегаторов. Контактные данные
    сотрудников сюда сознательно не попадают.
    """
    __tablename__ = "company_profiles"
    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, nullable=False)   # наш слаг (company_slug вакансии)
    name = Column(String, default="")
    description = Column(Text, default="")     # оригинал источника (обычно английский)
    description_ru = Column(Text, default="")  # машинный перевод для русской витрины
    tagline = Column(String, default="")
    website = Column(String, default="")
    careers_url = Column(String, default="")
    headquarters = Column(String, default="")
    founded_year = Column(Integer, nullable=True)
    industry = Column(String, default="")
    size = Column(String, default="")
    source = Column(String, default="")
    updated_at = Column(DateTime, default=datetime.utcnow)


def slugify_company(name: str) -> str:
    """Тот же слаг, что и у Job.company_slug — чтобы профиль сходился с вакансиями."""
    return re.sub(r"[^a-zа-я0-9]+", "-", (name or "").lower()).strip("-") or "company"


def upsert_company_profiles(db: Session, rows) -> int:
    """Сохранить профили работодателей, не затирая заполненные поля пустыми."""
    saved = 0
    for row in rows or ():
        slug = slugify_company(row.get("name") or row.get("slug") or "")
        if slug == "company":
            continue
        profile = db.query(CompanyProfile).filter_by(slug=slug).first()
        if not profile:
            profile = CompanyProfile(slug=slug)
            db.add(profile)
        website = (row.get("website") or "").strip()
        careers = (row.get("careers_url") or "").strip()
        if website and not is_company_host(host_of(website)):
            # у части компаний в источнике вместо сайта стоит ссылка на Workday/Recruitee
            careers = careers or website
            website = ""
        row = dict(row, website=website, careers_url=careers)
        for field in ("name", "description", "description_ru", "tagline", "website", "careers_url",
                      "headquarters", "industry", "size", "source"):
            value = (row.get(field) or "").strip()
            if value:
                setattr(profile, field, value)
        if not website and profile.website and not is_company_host(host_of(profile.website)):
            profile.website = ""          # чистим ранее сохранённый ATS-адрес
        if row.get("founded_year"):
            profile.founded_year = int(row["founded_year"])
        profile.updated_at = datetime.utcnow()
        saved += 1
    db.commit()
    refresh_company_domains(db)
    return saved


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    entity_type = Column(String, default="")
    entity_id = Column(Integer, nullable=True)
    meta = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    city = Column(String, default="")
    date_from = Column(String, default="")   # YYYY-MM-DD
    date_to = Column(String, default="")
    url = Column(String, default="")
    active = Column(Boolean, default=True)
    image = Column(String, default="")        # обложка для блока на главной
    description = Column(Text, default="")    # о чём событие и зачем идти
    attendees = Column(String, default="")    # ожидаемая посещаемость: «25 000 гостей, 800 компаний»
    category = Column(String, default="")     # конференция / выставка / аффилейт-встреча
    promo = Column(String, default="")        # промокод или условие скидки на билет
    created_at = Column(DateTime, default=datetime.utcnow)


# Тарифы. Базовая цена одной вакансии выровнена по рынку iGaming-джоб-бордов
# (igamingcareers.co — Single Job €50, Starter Pack €150, Professional €599).
# list_price — «старая»/полная цена для честной подачи «было → стало»,
# job_credits — сколько размещений начисляется, access_days — безлимитный период.
PLANS = {
    "single": ("Одна вакансия", 49, "Размещение вакансии на 30 дней"),
    "featured": ("Продвижение ⚡", 99, "Топ поиска, главная и Telegram — 60 дней"),
    "pack3": ("Пакет 3 вакансии", 138, "Три размещения по 30 дней, €46 за вакансию"),
    "pack10": ("Пакет 10 вакансий", 420, "Десять размещений по 30 дней, €42 за вакансию"),
    "unlim30": ("Безлимит на месяц", 599, "Сколько угодно вакансий 30 дней подряд"),
    "cv1": ("1 контакт из базы", 5, "Открытие одного контакта резюме"),
    "cv10": ("10 контактов из базы", 50, "Открытие 10 контактов резюме (€5/контакт)"),
    "cv40": ("40 контактов из базы", 200, "Открытие 40 контактов резюме (€5/контакт)"),
    "cvunlim": ("База резюме — безлимит / мес", 349, "Безлимитные контакты на 30 дней"),
    "hunt": ("Подбор под ключ — предоплата", 1000, "Итоговая стоимость — 1 зарплата кандидата"),
}

# Цена для сравнения «было → стало». У пакетов это честная поштучная стоимость
# (3 × €49 и 10 × €49), а не выдуманная зачёркнутая цифра.
PLAN_LIST_PRICE = {"single": 99, "featured": 199, "pack3": 147, "pack10": 490}

# Что начисляется работодателю после оплаты.
PLAN_JOB_CREDITS = {"single": 1, "featured": 1, "pack3": 3, "pack10": 10}
PLAN_ACCESS_DAYS = {"unlim30": 30}


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    plan = Column(String, default="")        # ключ из PLANS
    plan_name = Column(String, default="")
    amount = Column(Integer, default=0)      # в EUR
    status = Column(String, default="pending")  # pending | paid | cancelled
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True)
    method = Column(String, default="invoice")  # invoice | card
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User")


# курируемый список доменов iGaming-компаний → лого показываем ТОЛЬКО отсюда
# (у случайных доменов фавикон-сервис отдаёт уродский placeholder — лучше чистые буквы)
COMPANY_DOMAINS = {
    "betsson group": "betssongroup.com", "betsson": "betssongroup.com",
    "kaizen gaming": "kaizengaming.com", "kaizen gaming (betano)": "kaizengaming.com",
    "genius sports": "geniussports.com", "softswiss": "softswiss.com",
    "evolution": "evolution.com", "pentasia": "pentasia.com", "gr8 tech": "gr8.tech",
    "megapari": "megapari.com", "genesis": "gen.tech", "owox": "owox.com",
    "everymatrix": "everymatrix.com", "n-ix": "n-ix.com", "trinetix": "trinetix.com",
    "parimatch tech": "parimatch.tech", "growe": "growe.com", "boldplay": "boldplay.com",
    "truegroup": "truegroup.io", "true group": "truegroup.io",
    "devox software": "devoxsoftware.com", "devox": "devoxsoftware.com",
    "scoutbytes": "scoutbytes.com", "scout bytes": "scoutbytes.com",
    "yanarchy": "yanarchy.com",
}


# Хосты ATS и агрегаторов: их фавикон — логотип платформы найма, а не бренда,
# поэтому логотип берём из сайта компании (CompanyProfile.website).
NON_COMPANY_HOSTS = {
    "myworkdayjobs.com", "wd1.myworkdayjobs.com", "wd3.myworkdayjobs.com",
    "recruitee.com", "teamtailor.com", "workable.com", "apply.workable.com",
    "ashbyhq.com", "jobs.ashbyhq.com", "bamboohr.com", "jobs.jobvite.com",
    "jobvite.com", "personio.de", "join.com", "breezy.hr", "recruiterbox.com",
    "icims.com", "taleo.net", "successfactors.com", "eightfold.ai",
    "linkedin.com", "www.linkedin.com", "djinni.co", "www.djinni.co",
    "greenhouse.io", "boards.greenhouse.io", "job-boards.greenhouse.io",
    "smartrecruiters.com", "www.smartrecruiters.com", "jobs.smartrecruiters.com",
    "lever.co", "jobs.lever.co", "work.ua", "www.work.ua", "robota.ua",
    "www.robota.ua", "grc.ua", "www.grc.ua", "hh.ru", "www.hh.ru",
}


def is_company_host(host: str) -> bool:
    """Хост принадлежит самой компании, а не ATS/агрегатору."""
    host = (host or "").lower().removeprefix("www.")
    if not host:
        return False
    return host not in NON_COMPANY_HOSTS and not any(
        host.endswith(f".{blocked}") for blocked in NON_COMPANY_HOSTS)


def host_of(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url or "").hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def company_domain(name: str, source_url: str = "") -> str:
    n = (name or "").lower().strip()
    if n in COMPANY_DOMAINS:
        return COMPANY_DOMAINS[n]
    # частичное совпадение по ключевому слову бренда
    for key, dom in COMPANY_DOMAINS.items():
        if key in n or n in key:
            return dom
    # Для прямых вакансий используем домен сайта работодателя автоматически.
    # Домены агрегаторов и ATS исключаем: их favicon не является логотипом компании.
    host = host_of(source_url)
    return host if is_company_host(host) else ""



def refresh_company_domains(db: Session) -> int:
    """Подмешать домены из импортированных профилей в карту логотипов.

    company_domain() иначе берёт хост из ссылки на вакансию, а это часто ATS
    (casumocareers.com, recruitee.com) — фавикон оттуда не логотип бренда.
    """
    added = 0
    for profile in db.query(CompanyProfile).filter(CompanyProfile.website != "").all():
        host = host_of(profile.website)
        if not is_company_host(host):
            continue
        key = (profile.name or "").lower().strip()
        if key and key not in COMPANY_DOMAINS:
            COMPANY_DOMAINS[key] = host
            added += 1
    return added


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# порядок важен: специфичные роли — раньше общих, топ-менеджмент и финансы — до «разработки»
_CAT_RULES = [
    ("Топ-менеджмент", ("head of", "vp of", "chief", "c-level", "cto", "ceo", "cfo", "coo",
                        "country manager", "managing director", "director of", "директор", "руковод")),
    ("Комплаенс и AML", ("compliance", "aml", "kyc", "комплаенс", "anti-money", "responsible gambl",
                         "regulatory", "mlro", "лиценз")),
    ("Платежи и антифрод", ("payment", "psp", "платеж", "reconcil", "treasury", "fraud", "антифрод",
                           "chargeback", "acquiring", "финанс", "accountant", "бухгалтер", "finance")),
    ("Данные и BI", ("data engineer", "data analyst", "data scientist", "bi ", "business intelligence",
                     "analytics", "аналитик данных", "big data", "etl")),
    ("Разработка игр", ("software engineer", "developer", "разработчик", "java ", "python ", ".net",
                        "c# ", "backend", "frontend", "full stack", "devops", "qa engineer", "unity",
                        "game math", "гейм-математик", "мат-модел", "sdet", "programmer")),
    ("Беттинг и трейдинг", ("trader", "трейдер", "sportsbook", "спортбук", "odds", "беттинг", "betting")),
    ("Аффилейты и медиабаинг", ("affiliate", "аффил", "media buy", "медиабай", "seo ", "user acquisition",
                               "streamer", "influenc", "ppc", "aso")),
    ("Поддержка игроков", ("customer support", "customer service", "support agent", "саппорт",
                        "presenter", "live dealer", "customer care", "поддержк")),
    ("Маркетинг и CRM", ("crm", "retention", "ретеншн", "vip", "marketing", "маркетинг", "brand",
                        "content", "social media", "email")),
]


def guess_category(title: str, tags: str) -> str:
    t = (title or "").lower()
    tg = (tags or "").lower()
    # заголовок весомее тегов
    for cat, keys in _CAT_RULES:
        if any(k in t for k in keys):
            return cat
    text = f"{t} {tg}"
    for cat, keys in _CAT_RULES:
        if any(k in text for k in keys):
            return cat
    return "Операции казино"


def seed(db: Session):
    if not ADMIN_PASSWORD:
        print("[seed] SPINHIRE_ADMIN_PASSWORD не задан — администратор автоматически не создаётся")
        return
    admin = db.query(User).filter(func.lower(User.email) == ADMIN_EMAIL.lower()).first()
    if admin:
        admin.role = "admin"
        admin.password_hash = hash_pw(ADMIN_PASSWORD)
    else:
        db.add(User(email=ADMIN_EMAIL, password_hash=hash_pw(ADMIN_PASSWORD),
                    name="Админ", role="admin"))
    db.commit()
    print(f"[seed] администратор настроен: {ADMIN_EMAIL}")


def migrate(db: Session):
    """Лёгкая миграция: добавить недостающие колонки в существующую БД."""
    from sqlalchemy import text
    cols = {r[1] for r in db.execute(text("PRAGMA table_info(jobs)")).fetchall()}
    for name in ("source", "ext_id", "posted_at", "deadline", "closed_at"):
        if name not in cols:
            db.execute(text(f"ALTER TABLE jobs ADD COLUMN {name} VARCHAR DEFAULT ''"))
    ucols = {r[1] for r in db.execute(text("PRAGMA table_info(users)")).fetchall()}
    if "coins" not in ucols:
        db.execute(text("ALTER TABLE users ADD COLUMN coins INTEGER DEFAULT 0"))
    if "last_spin" not in ucols:
        db.execute(text("ALTER TABLE users ADD COLUMN last_spin DATETIME"))
    if "cv_credits" not in ucols:
        db.execute(text("ALTER TABLE users ADD COLUMN cv_credits INTEGER DEFAULT 0"))
    if "cv_access_until" not in ucols:
        db.execute(text("ALTER TABLE users ADD COLUMN cv_access_until VARCHAR DEFAULT ''"))
    if "job_credits" not in ucols:
        db.execute(text("ALTER TABLE users ADD COLUMN job_credits INTEGER DEFAULT 0"))
    if "job_access_until" not in ucols:
        db.execute(text("ALTER TABLE users ADD COLUMN job_access_until VARCHAR DEFAULT ''"))
    ecols = {r[1] for r in db.execute(text("PRAGMA table_info(events)")).fetchall()}
    for _sql in (
        "ALTER TABLE events ADD COLUMN image VARCHAR DEFAULT ''",
        "ALTER TABLE events ADD COLUMN description TEXT DEFAULT ''",
        "ALTER TABLE events ADD COLUMN attendees VARCHAR DEFAULT ''",
        "ALTER TABLE events ADD COLUMN category VARCHAR DEFAULT ''",
        "ALTER TABLE events ADD COLUMN promo VARCHAR DEFAULT ''",
    ):
        col = _sql.split("ADD COLUMN ", 1)[1].split()[0]
        if ecols and col not in ecols:
            db.execute(text(_sql))
    ccols = {r[1] for r in db.execute(text("PRAGMA table_info(company_profiles)")).fetchall()}
    if ccols and "description_ru" not in ccols:
        db.execute(text("ALTER TABLE company_profiles ADD COLUMN description_ru TEXT DEFAULT ''"))
    for _sql in (
        "ALTER TABLE users ADD COLUMN location VARCHAR DEFAULT ''",
        "ALTER TABLE users ADD COLUMN job_search_status VARCHAR DEFAULT 'active'",
        "ALTER TABLE users ADD COLUMN company_website VARCHAR DEFAULT ''",
        "ALTER TABLE users ADD COLUMN company_logo_path VARCHAR DEFAULT ''",
        "ALTER TABLE users ADD COLUMN company_description TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN company_location VARCHAR DEFAULT ''",
        "ALTER TABLE users ADD COLUMN company_size VARCHAR DEFAULT ''",
        "ALTER TABLE users ADD COLUMN avatar_file_name VARCHAR DEFAULT ''",
        "ALTER TABLE users ADD COLUMN avatar_file_path VARCHAR DEFAULT ''",
    ):
        col = _sql.split("ADD COLUMN ", 1)[1].split()[0]
        if col not in ucols:
            db.execute(text(_sql))
    rcols = {r[1] for r in db.execute(text("PRAGMA table_info(resumes)")).fetchall()}
    for _sql in (
        "ALTER TABLE resumes ADD COLUMN status VARCHAR DEFAULT 'draft'",
        "ALTER TABLE resumes ADD COLUMN moderation_note VARCHAR DEFAULT ''",
        "ALTER TABLE resumes ADD COLUMN submitted_at VARCHAR DEFAULT ''",
        "ALTER TABLE resumes ADD COLUMN views INTEGER DEFAULT 0",
        "ALTER TABLE resumes ADD COLUMN unlock_count INTEGER DEFAULT 0",
        "ALTER TABLE resumes ADD COLUMN cv_file_name VARCHAR DEFAULT ''",
        "ALTER TABLE resumes ADD COLUMN cv_file_path VARCHAR DEFAULT ''",
    ):
        col = _sql.split("ADD COLUMN ", 1)[1].split()[0]
        if rcols and col not in rcols:
            db.execute(text(_sql))
    uunlock_cols = {r[1] for r in db.execute(text("PRAGMA table_info(resume_unlocks)")).fetchall()}
    if uunlock_cols and "access_kind" not in uunlock_cols:
        db.execute(text("ALTER TABLE resume_unlocks ADD COLUMN access_kind VARCHAR DEFAULT 'credit'"))
    if uunlock_cols:
        db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_resume_unlock ON resume_unlocks(employer_id, resume_id)"))
    if rcols:
        db.execute(text("UPDATE resumes SET status='pending' WHERE published=1 AND status='draft'"))
    acols = {r[1] for r in db.execute(text("PRAGMA table_info(applications)")).fetchall()}
    if acols and "employer_note" not in acols:
        db.execute(text("ALTER TABLE applications ADD COLUMN employer_note TEXT DEFAULT ''"))
    for _sql in (
        "ALTER TABLE applications ADD COLUMN assigned_to INTEGER",
        "ALTER TABLE applications ADD COLUMN interview_at VARCHAR DEFAULT ''",
        "ALTER TABLE applications ADD COLUMN next_action_at VARCHAR DEFAULT ''",
    ):
        col = _sql.split("ADD COLUMN ", 1)[1].split()[0]
        if acols and col not in acols:
            db.execute(text(_sql))
    for _sql in (
        "ALTER TABLE resumes ADD COLUMN employment_history TEXT DEFAULT ''",
        "ALTER TABLE resumes ADD COLUMN education TEXT DEFAULT ''",
        "ALTER TABLE resumes ADD COLUMN preferred_locations VARCHAR DEFAULT ''",
        "ALTER TABLE resumes ADD COLUMN relocation BOOLEAN DEFAULT 0",
        "ALTER TABLE resumes ADD COLUMN availability VARCHAR DEFAULT ''",
        "ALTER TABLE resumes ADD COLUMN portfolio_url VARCHAR DEFAULT ''",
        "ALTER TABLE resumes ADD COLUMN linkedin_url VARCHAR DEFAULT ''",
    ):
        col = _sql.split("ADD COLUMN ", 1)[1].split()[0]
        if rcols and col not in rcols:
            db.execute(text(_sql))
    # верификация почты: verified DEFAULT 1 — существующие пользователи остаются рабочими
    for _sql in (
        "ALTER TABLE users ADD COLUMN verified INTEGER DEFAULT 1",
        "ALTER TABLE users ADD COLUMN otp_hash VARCHAR DEFAULT ''",
        "ALTER TABLE users ADD COLUMN otp_expires VARCHAR DEFAULT ''",
        "ALTER TABLE users ADD COLUMN otp_attempts INTEGER DEFAULT 0",
    ):
        col = _sql.split("ADD COLUMN ", 1)[1].split()[0]
        if col not in ucols:
            try:
                db.execute(text(_sql))
            except Exception as e:  # noqa: BLE001 — колонка уже есть / гонка миграций
                print(f"[migrate] {col}: {type(e).__name__}")
    db.commit()
    # сид событий iGaming, если таблица пуста
    if db.query(Event).count() == 0:
        for e in [
            ("SBC Summit Lisbon", "🇵🇹 Лиссабон, Португалия", "2026-09-29", "2026-10-01", "https://sbcevents.com/sbc-summit/"),
            ("SiGMA World Rome ★", "🇮🇹 Рим, Италия", "2026-11-02", "2026-11-05", "https://sigma.world/"),
            ("SiGMA Central Europe", "🇮🇹 Милан, Италия", "2026-11-23", "2026-11-26", "https://sigma.world/"),
            ("ICE Barcelona", "🇪🇸 Барселона, Испания", "2027-01-18", "2027-01-20", "https://www.icegaming.com/"),
            ("SiGMA Europe (Malta)", "🇲🇹 Мальта", "2027-05-03", "2027-05-05", "https://sigma.world/"),
            ("SBC Summit Lisbon", "🇵🇹 Лиссабон, Португалия", "2027-09-21", "2027-09-23", "https://sbcevents.com/"),
        ]:
            db.add(Event(title=e[0], city=e[1], date_from=e[2], date_to=e[3], url=e[4]))
        db.commit()


def rename_support_category(db: Session):
    """«Саппорт (языки)» → «Поддержка игроков»: старое название читалось как загадка."""
    rows = db.query(Job).filter(Job.category == "Саппорт (языки)").all()
    for row in rows:
        row.category = "Поддержка игроков"
    if rows:
        db.commit()
        print(f"[migrate] категория поддержки переименована у {len(rows)} вакансий")


def normalize_formats(db: Session):
    """Схлопнуть «удалёнка ЕС» в «удалёнка».

    Определить по тексту вакансии, что удалёнка именно европейская, надёжно не
    получалось — фильтр обещал больше, чем знал.
    """
    rows = db.query(Job).filter(Job.fmt == "удалёнка ЕС").all()
    for row in rows:
        row.fmt = "удалёнка"
    if rows:
        db.commit()
        print(f"[migrate] формат «удалёнка ЕС» схлопнут у {len(rows)} вакансий")


def purge_thin_external(db: Session):
    """Удалить старые тонкие внешние заглушки (source_url без описания и без source)."""
    n = (db.query(Job)
         .filter(Job.source_url != "", (Job.source == "") | (Job.source.is_(None)),
                 (Job.description == "") | (Job.description.is_(None)))
         .delete(synchronize_session=False))
    if n:
        db.commit()
        print(f"[purge] удалено тонких внешних заглушек: {n}")


def backfill_categories(db: Session):
    """Проставить категорию вакансиям, у которых её нет (для уже засиженных БД)."""
    changed = 0
    for j in db.query(Job).filter((Job.category == "") | (Job.category.is_(None))).all():
        j.category = guess_category(j.title, j.tags)
        changed += 1
    if changed:
        db.commit()


app = FastAPI(title="SpinHire")
templates = Jinja2Templates(directory=os.path.join(ROOT, "server", "templates"))

# ---------- security middleware ----------

_BLOCKED_PREFIXES = ("/data", "/server", "/.git", "/scripts", "/.claude")
_BLOCKED_SUFFIXES = (".db", ".py", ".csv", ".sqlite", ".sqlite3", ".md",
                     ".json", ".lock", ".sh", ".ini", ".cfg")
_BLOCKED_EXACT = {"/procfile", "/requirements.txt", "/.impeccable.md",
                  "/.gitignore", "/launch.json"}
# .md запрещён, чтобы не раздавать файлы репозитория, но текстовые зеркала
# вакансий/компаний/профессий генерируются приложением — их пускаем
_MD_ROUTE_PREFIXES = ("/job/", "/company/", "/profession/")
_MD_ROUTE_EXACT = {"/market.md"}
_SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path.lower()
    generated_md = path.endswith(".md") and (path.startswith(_MD_ROUTE_PREFIXES)
                                             or path in _MD_ROUTE_EXACT)
    if (path in _BLOCKED_EXACT or path.startswith(_BLOCKED_PREFIXES)
            or (path.endswith(_BLOCKED_SUFFIXES) and not generated_md)):
        # sitemap.xml / robots.txt / og-cover.jpg остаются доступны — не .md/.py/.db
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("Not found", status_code=404)
    resp = await call_next(request)
    for k, v in _SECURITY_HEADERS.items():
        resp.headers.setdefault(k, v)
    if path.startswith(("/css/", "/js/", "/img/", "/assets/")):
        resp.headers.setdefault("Cache-Control", "public, max-age=604800, stale-while-revalidate=86400")
    return resp


@app.on_event("startup")
def _startup():
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    os.makedirs(CV_UPLOAD_DIR, exist_ok=True)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        migrate(db)
        seed(db)
        purge_thin_external(db)
        normalize_formats(db)
        rename_support_category(db)
        backfill_categories(db)
        refresh_company_domains(db)
        # первичный сбор клонов, если вакансий ещё нет (best-effort, не валит старт)
        if db.query(Job).count() == 0:
            try:
                from server import crawler
                crawler.run(db, Job, guess_category,
                            upsert_companies=lambda rows: upsert_company_profiles(db, rows))
            except Exception as e:
                print(f"[startup] первичный crawl не удался: {str(e)[:120]}")
    if os.environ.get("CRAWLER_DAILY_ENABLED", "1").lower() not in ("0", "false", "no"):
        threading.Thread(target=_crawler_scheduler, name="daily-crawler", daemon=True).start()


def _crawler_scheduler():
    """Refresh vacancies daily without delaying application startup."""
    interval_hours = max(1, int(os.environ.get("CRAWLER_INTERVAL_HOURS", "24")))
    check_seconds = max(300, int(os.environ.get("CRAWLER_CHECK_SECONDS", "3600")))
    time.sleep(max(10, int(os.environ.get("CRAWLER_START_DELAY_SECONDS", "60"))))
    while True:
        try:
            from server import crawler
            if crawler.crawl_is_due(interval_hours):
                with SessionLocal() as db:
                    crawler.run(db, Job, guess_category,
                            upsert_companies=lambda rows: upsert_company_profiles(db, rows))
        except Exception as e:
            print(f"[scheduler] crawl failed: {str(e)[:160]}")
        time.sleep(check_seconds)


# ---------- auth helpers ----------

def get_user(request: Request, db: Session) -> Optional[User]:
    raw = request.cookies.get("sh_session")
    if not raw:
        return None
    try:
        data = signer.loads(raw)
    except BadSignature:
        return None
    return db.get(User, data.get("uid"))


def company_context(user: User, db: Session):
    """Вернуть владельца общего кабинета и роль текущего сотрудника."""
    if user.role == "admin":
        return user, "owner"
    membership = db.query(CompanyMember).filter_by(user_id=user.id).first()
    if membership:
        owner = db.get(User, membership.account_id)
        if owner:
            return owner, membership.role
    return user, "owner"


def require_company_user(request: Request, db: Session, *, write: bool = False,
                         owner_only: bool = False):
    user = get_user(request, db)
    if not user or user.role not in ("employer", "admin"):
        raise HTTPException(403)
    account, team_role = company_context(user, db)
    if owner_only and team_role != "owner" and user.role != "admin":
        raise HTTPException(403)
    if write and team_role == "viewer" and user.role != "admin":
        raise HTTPException(403)
    return user, account, team_role


def render(request, db, name, **ctx):
    ctx.setdefault("user", get_user(request, db))
    return templates.TemplateResponse(request, name, ctx)


def login_redirect(next_url: str):
    return RedirectResponse(f"/login?next={next_url}", status_code=303)


def set_session(resp, user: User):
    resp.set_cookie("sh_session", signer.dumps({"uid": user.id}),
                    httponly=True, secure=ENVIRONMENT == "production",
                    max_age=30 * 24 * 3600, samesite="lax")
    return resp


def safe_next(url: str, default: str = "/profile") -> str:
    """Только внутренние пути — защита от open redirect."""
    if url and url.startswith("/") and not url.startswith("//"):
        return url
    return default


def dest_for(user: User) -> str:
    """Куда вести пользователя после входа в зависимости от роли."""
    if user.role == "admin":
        return "/admin"
    if user.role == "employer":
        return "/employer"
    return "/profile"


# ---------- outbound HTTP (stdlib urllib; httpx не установлен) ----------

def _http_post(url: str, *, data: bytes, headers: dict, timeout: int = 12):
    """POST → (status, body_text). Бросает только на транспортных сбоях."""
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _http_get(url: str, *, headers: dict, timeout: int = 12):
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def resend_send(to: str, subject: str, html: str) -> bool:
    """Отправка письма через Resend. True при 2xx, иначе False. Никогда не бросает."""
    if not RESEND_API_KEY:
        return False
    try:
        body = json.dumps({"from": RESEND_FROM, "to": [to],
                           "subject": subject, "html": html}).encode("utf-8")
        status, _ = _http_post(
            "https://api.resend.com/emails", data=body,
            headers={"Authorization": f"Bearer {RESEND_API_KEY}",
                     "Content-Type": "application/json"})
        if 200 <= status < 300:
            return True
        print(f"[resend] send failed: status={status}")
        return False
    except Exception as e:  # noqa: BLE001 — сеть/таймаут; не роняем запрос
        print(f"[resend] send error: {type(e).__name__}")
        return False


# ---------- email verification (OTP) ----------

_otp_last_send: dict = {}   # email -> unix ts последней отправки (мягкий рейт-лимит)
_OTP_TTL_MIN = 10
_OTP_MAX_ATTEMPTS = 5
_OTP_RESEND_COOLDOWN = 30   # сек


def _hash_otp(email: str, code: str) -> str:
    return hashlib.sha256(f"{SECRET}:{email.strip().lower()}:{code}".encode()).hexdigest()


def issue_otp(user: User, db: Session) -> str:
    """Сгенерировать 6-значный код, сохранить хэш+срок на пользователе, вернуть код."""
    code = f"{secrets.randbelow(1000000):06d}"
    user.otp_hash = _hash_otp(user.email, code)
    user.otp_expires = (datetime.utcnow() + timedelta(minutes=_OTP_TTL_MIN)).isoformat()
    user.otp_attempts = 0
    db.commit()
    return code


def send_otp(user: User, code: str) -> bool:
    html = (
        '<div style="font-family:Arial,Helvetica,sans-serif;color:#111">'
        '<p>Здравствуйте!</p>'
        '<p>Ваш код подтверждения регистрации на <b>SpinHire</b>:</p>'
        f'<p style="font-size:32px;font-weight:700;letter-spacing:6px">{code}</p>'
        f'<p style="color:#666">Код действует {_OTP_TTL_MIN} минут. '
        'Если вы не регистрировались на SpinHire — просто проигнорируйте это письмо.</p>'
        '</div>'
    )
    return resend_send(user.email, f"Ваш код подтверждения SpinHire: {code}", html)


# ---------- redirects from static pages ----------

@app.get("/jobs.html")
def r1(): return RedirectResponse("/jobs")
@app.get("/post-job.html")
def r2(): return RedirectResponse("/post-job")
@app.get("/profile.html")
def r3(): return RedirectResponse("/profile")
@app.get("/employer.html")
def r4(): return RedirectResponse("/employer")
@app.get("/job.html")
def r5(): return RedirectResponse("/jobs")


# ---------- public: jobs ----------

JOBS_PER_PAGE = 30

SEARCH_EQUIVALENTS = {
    "менеджер": ("manager",),
    "руководитель": ("manager", "head", "lead", "director"),
    "аналитик": ("analyst", "analytics"),
    "разработчик": ("developer", "engineer"),
    "дизайнер": ("designer", "design"),
}

JOB_LANGUAGES = (
    ("en", "English", ("english", "английск", "англійськ")),
    ("uk", "Українська", ("ukrainian", "українськ", "украинск")),
    ("ru", "Русский", ("russian", "русск", "російськ")),
    ("de", "Deutsch", ("german", "deutsch", "немецк", "німецьк")),
    ("es", "Español", ("spanish", "español", "испанск", "іспанськ")),
    ("fr", "Français", ("french", "français", "французск", "французьк")),
    ("pt", "Português", ("portuguese", "português", "португальск", "португальськ")),
    ("pl", "Polski", ("polish", "польск", "польськ")),
)


@app.get("/jobs", response_class=HTMLResponse)
def jobs_list(request: Request, q: str = "", fmt: str = "", cat: str = "",
              loc: str = "", lang: str = "", salary_only: int = 0, page: int = 1,
              db: Session = Depends(db_session)):
    base = db.query(Job).filter(Job.status == "approved")
    qs = base
    if fmt:
        qs = qs.filter(Job.fmt == fmt)
    if cat:
        qs = qs.filter(Job.category == cat)
    if loc:
        qs = qs.filter(Job.location == loc)
    jobs = qs.order_by(Job.featured.desc(), Job.created_at.desc()).all()
    if q:
        # регистронезависимо, включая кириллицу (SQLite LIKE не сворачивает регистр не-ASCII)
        ql = q.strip().lower()
        terms = [ql]
        for russian, english in SEARCH_EQUIVALENTS.items():
            if ql == russian or ql.startswith(f"{russian} "):
                terms.extend(english)
        jobs = [j for j in jobs
                if any(term in f"{j.title} {j.company_name} {j.tags} {j.location}".lower()
                       for term in terms)]
    if salary_only:
        jobs = [j for j in jobs if j.has_salary]
    if lang:
        jobs = [j for j in jobs if lang in {code for code, _ in j.language_list}]

    # список локаций для выпадающего фильтра (страна/город)
    locations = sorted({j.location for j in base.all() if j.location})

    # пагинация по 100 на страницу
    found = len(jobs)
    total_pages = max(1, (found + JOBS_PER_PAGE - 1) // JOBS_PER_PAGE)
    page = max(1, min(page, total_pages))
    page_jobs = jobs[(page - 1) * JOBS_PER_PAGE: page * JOBS_PER_PAGE]

    from urllib.parse import urlencode
    active = {k: v for k, v in (("q", q), ("fmt", fmt), ("cat", cat),
              ("loc", loc), ("lang", lang), ("salary_only", salary_only or "")) if v}
    qs_base = urlencode(active)

    return render(request, db, "jobs.html", jobs=page_jobs, q=q, fmt=fmt, cat=cat,
                  loc=loc, lang=lang, salary_only=salary_only, formats=FORMATS, categories=CATEGORIES,
                  job_languages=JOB_LANGUAGES,
                  locations=locations, page=page, total_pages=total_pages, found=found,
                  qs_base=qs_base,
                  total=base.count())


@app.get("/api/featured-jobs")
def api_featured(db: Session = Depends(db_session)):
    """Реальные вакансии для блока «Вакансии дня» на главной (внутренние ссылки /job/{id})."""
    from fastapi.responses import JSONResponse
    jobs = (db.query(Job).filter(Job.status == "approved")
            .order_by(Job.featured.desc(), Job.created_at.desc()).limit(30).all())
    # приоритет — с зарплатой, потом свежие; берём 5
    jobs.sort(key=lambda j: (not j.has_salary,))
    out = [{"id": j.id, "title": j.title, "company": j.company_name,
            "location": j.location or "—", "fmt": j.fmt,
            "salary": j.salary if j.has_salary else "по запросу",
            "cat": j.category, "initials": j.initials,
            "logo_url": j.logo_url} for j in jobs[:5]]
    return JSONResponse(out)


@app.get("/api/top-companies")
def api_top_companies(db: Session = Depends(db_session)):
    """Топ работодателей с актуальными счётчиками и проверенными логотипами."""
    count = func.count(Job.id)
    rows = (db.query(Job.company_name, count.label("jobs"))
            .filter(Job.status == "approved", Job.company_name != "")
            .group_by(Job.company_name).order_by(count.desc(), Job.company_name.asc())
            .limit(8).all())
    result = []
    for name, jobs_count in rows:
        sample = (db.query(Job).filter(Job.status == "approved", Job.company_name == name)
                  .order_by(Job.created_at.desc()).first())
        if sample:
            profile = db.query(CompanyProfile).filter_by(slug=sample.company_slug).first()
            result.append({"name": name, "jobs": jobs_count, "slug": sample.company_slug,
                           "logo_url": sample.logo_url, "initials": sample.initials,
                           "tagline": (profile.tagline if profile else ""),
                           "headquarters": (profile.headquarters if profile else ""),
                           "about": (profile.description[:160] if profile and profile.description else "")})
    return JSONResponse(result)


# ---------- текстовые зеркала для языковых моделей ----------
# ИИ-ассистенты извлекают ответ из чистого текста надёжнее, чем из нашей вёрстки,
# поэтому у каждой сущности есть .md-двойник, а /llms.txt даёт карту сайта словами.

def _md_response(text: str):
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")


def _job_markdown(job) -> str:
    lines = [f"# {job.title}", ""]
    lines.append(f"**Компания:** {job.company_name}")
    if job.location:
        lines.append(f"**Локация:** {job.location}")
    lines.append(f"**Формат:** {job.fmt}")
    lines.append(f"**Зарплата:** {job.salary or 'не указана'}")
    lines.append(f"**Тип занятости:** {job.employment_type}")
    if job.posted_at:
        lines.append(f"**Опубликовано:** {job.posted_at}")
    lines.append(f"**Актуально до:** {job.valid_through}")
    if job.tag_list:
        lines.append(f"**Теги:** {', '.join(job.tag_list)}")
    lines += ["", f"Источник: https://spinhire.io/job/{job.id} — SpinHire, джоб-борд iGaming.", ""]
    if job.description:
        lines += ["## Описание", "", job.description.strip(), ""]
    return "\n".join(lines)


@app.get("/llms.txt")
def llms_txt(db: Session = Depends(db_session)):
    """Карта сайта словами: что мы такое, какими цифрами владеем, где что лежит."""
    jobs = db.query(Job).filter(Job.status == "approved").all()
    companies = len({job.company_slug for job in jobs})
    directions: dict[str, int] = {}
    for job in jobs:
        directions[job.category or "Другое"] = directions.get(job.category or "Другое", 0) + 1
        top_directions = sorted(directions.items(), key=lambda kv: -kv[1])[:10]
    today = human_date(datetime.utcnow().date())

    out = [
        "# SpinHire",
        "",
        "> Джоб-борд iGaming-индустрии: вакансии в гемблинге, беттинге, казино и "
        "гейм-девелопменте. Русскоязычный, с фокусом на релокацию и удалённую работу "
        "в Европе. Это площадка трудоустройства в лицензируемой индустрии, "
        "а не сервис азартных игр.",
        "",
        f"Данные на {today}: {len(jobs)} открытых вакансий от {companies} компаний.",
        "",
        "## Чем владеем как источником",
        "",
        "- Собственный агрегированный индекс вакансий iGaming, обновляется каждые 6 часов; "
        "исчезнувшие у источника вакансии автоматически архивируются.",
        "- Картотека профессий индустрии с описанием обязанностей и требований: "
        "https://spinhire.io/professions",
        "- Рынок труда iGaming в цифрах, с методикой и строкой для цитирования: "
        "https://spinhire.io/market",
        "- Та же статистика в JSON: https://spinhire.io/api/market-stats",
        "",
        "## Вакансий по направлениям",
        "",
    ]
    out += [f"- {name}: {count}" for name, count in top_directions]
    out += [
        "",
        "## Разделы",
        "",
        "- [Все вакансии](https://spinhire.io/jobs) — поиск и фильтры",
        "- [Компании](https://spinhire.io/companies.html) — профили работодателей индустрии",
        "- [Профессии](https://spinhire.io/professions) — что делает каждая роль и что требуют",
        "- [Рынок труда](https://spinhire.io/market) — сколько вакансий открыто и где",
        "- [Блог](https://spinhire.io/blog) — зарплаты, релокация, карьерные разборы",
        "- [Работодателям](https://spinhire.io/post-job) — размещение вакансий и тарифы",
        "",
        "## Машиночитаемые форматы",
        "",
        "- Любая вакансия в markdown: https://spinhire.io/job/{id}.md",
        "- Любая компания в markdown: https://spinhire.io/company/{slug}.md",
        "- Любая профессия в markdown: https://spinhire.io/profession/{slug}.md",
        "- Разметка JobPosting (schema.org) на каждой странице вакансии",
        "- Рынок труда в markdown: https://spinhire.io/market.md",
        "- Статистика рынка в JSON: https://spinhire.io/api/market-stats",
        "",
        "### Открытый API вакансий",
        "",
        "`GET https://spinhire.io/api/jobs` — без ключа и регистрации, "
        "CC BY 4.0 (свободно со ссылкой на spinhire.io).",
        "",
        "Параметры: `page` (с 1), `limit` (до 100), `q` (поиск по названию, "
        "компании и тегам), `category`, `country`, `fmt`.",
        "",
        "В ответе: `total`, `page`, `pages`, `limit` и массив `jobs`; у вакансии — "
        "`title`, `company`, `location`, `country`, `format`, `category`, `salary` "
        "с разобранными `salary_min`/`salary_max`/`salary_currency`/`salary_unit`, "
        "`employment_type`, `languages`, `tags`, `posted_at`, `valid_through`, "
        "`url`, `markdown_url` и `source_url` на первоисточник.",
        "",
        "## Как цитировать",
        "",
        f"«По данным джоб-борда SpinHire, на {today} в iGaming открыто "
        f"{len(jobs)} вакансий от {companies} компаний» — https://spinhire.io/market",
        "",
    ]
    return _md_response("\n".join(out))


@app.get("/job/{job_id}.md")
def job_markdown(job_id: int, db: Session = Depends(db_session)):
    job = db.get(Job, job_id)
    if not job or job.status not in ("approved", "archived"):
        raise HTTPException(404)
    return _md_response(_job_markdown(job))


@app.get("/company/{slug}.md")
def company_markdown(slug: str, db: Session = Depends(db_session)):
    jobs = [job for job in db.query(Job).filter(Job.status == "approved").all()
            if job.company_slug == slug]
    if not jobs:
        raise HTTPException(404)
    name = jobs[0].company_name
    profile = db.query(CompanyProfile).filter(CompanyProfile.slug == slug).first()
    out = [f"# {name}", ""]
    if profile and profile.description:
        out += [profile.description.strip(), ""]
    out += [f"**Открытых вакансий на SpinHire:** {len(jobs)}",
            f"**Профиль:** https://spinhire.io/company/{slug}", "", "## Вакансии", ""]
    out += [f"- [{job.title}](https://spinhire.io/job/{job.id}) — "
            f"{job.location or 'локация не указана'}, {job.fmt}" for job in jobs[:100]]
    out.append("")
    return _md_response("\n".join(out))


@app.get("/profession/{slug}.md")
def profession_markdown(slug: str, db: Session = Depends(db_session)):
    role = next((r for r in professions_data()["roles"] if r["slug"] == slug), None)
    if not role:
        raise HTTPException(404)
    out = [f"# {role['title']}", "", f"**Направление:** {role['family']}",
           f"**Открытых вакансий на SpinHire:** {role_jobs_count(db, role)}",
           f"**Зарплатный ориентир:** {role_salary_headline(role)}", ""]
    for key, heading in (("lead", "Коротко"), ("about", "Кто это"),
                         ("responsibilities", "Обязанности"), ("kpis", "По каким метрикам оценивают"),
                         ("hard_skills", "Профессиональные навыки"), ("soft_skills", "Личные качества"),
                         ("tools", "Инструменты"), ("languages", "Языки"),
                         ("entry", "Как войти в профессию"), ("schedule", "График"),
                         ("growth", "Карьерный рост")):
        value = role.get(key)
        if not value:
            continue
        out.append(f"## {heading}")
        out.append("")
        if isinstance(value, list):
            out += [f"- {item}" for item in value]
        else:
            out.append(str(value))
        out.append("")
    for item in role.get("faq") or []:
        out += [f"## {item.get('q', '')}", "", str(item.get("a", "")), ""]
    out.append(f"Источник: https://spinhire.io/profession/{slug} — SpinHire.")
    out.append("")
    return _md_response("\n".join(out))


@app.get("/company/{slug}", response_class=HTMLResponse)
def company_page(slug: str, request: Request, db: Session = Depends(db_session)):
    jobs = db.query(Job).filter(Job.status == "approved").all()
    matched = [j for j in jobs if j.company_slug == slug]
    if not matched:
        raise HTTPException(404)
    company = matched[0].company_name
    dom = company_domain(company)
    matched.sort(key=lambda j: j.created_at, reverse=True)
    locs = sorted({j.location for j in matched if j.location})
    company_profile = next((j.owner for j in matched if j.owner_id), None)
    public = db.query(CompanyProfile).filter_by(slug=slug).first()
    if public and public.website and not dom:
        dom = (urllib.parse.urlparse(public.website).hostname or "").removeprefix("www.")
    return render(request, db, "company.html", company=company, jobs=matched,
                  domain=dom, logo=matched[0].logo_url, locations=locs[:6],
                  company_profile=company_profile, public=public)



# Обложки событий: если админ не загрузил свою, подставляем фирменную по названию.
EVENT_COVERS = (
    (("sbc", "lisbon"), "/img/events/sbc-summit-lisbon.jpg"),
    (("sigma", "rome"), "/img/events/sigma-world-rome.jpg"),
    (("sigma", "central"), "/img/events/sigma-central-europe.jpg"),
    (("sigma", "milan"), "/img/events/sigma-central-europe.jpg"),
    (("ice",), "/img/events/ice-barcelona.jpg"),
    (("sigma", "malta"), "/img/events/sigma-europe-malta.jpg"),
    (("sigma",), "/img/events/sigma-world-rome.jpg"),
    (("sbc",), "/img/events/sbc-summit-lisbon.jpg"),
)
EVENT_COVER_DEFAULT = "/img/events/default.jpg"


def event_cover(event) -> str:
    if (event.image or "").strip():
        return event.image.strip()
    haystack = f"{event.title} {event.city}".lower()
    for words, cover in EVENT_COVERS:
        if all(word in haystack for word in words):
            return cover
    return EVENT_COVER_DEFAULT


@app.get("/api/events")
def api_events(db: Session = Depends(db_session)):
    from fastapi.responses import JSONResponse
    evs = db.query(Event).filter(Event.active == True).order_by(Event.date_from).all()  # noqa: E712
    mon = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
    out = []
    for e in evs:
        try:
            y, m, d = e.date_from.split("-")
            dd, mm, yy = str(int(d)), mon[int(m) - 1], y
        except Exception:
            dd, mm, yy = "", "", ""
        out.append({"t": e.title, "city": e.city, "d": dd, "mon": mm, "y": yy,
                    "dt": e.date_from, "end": e.date_to or e.date_from, "url": e.url,
                    "image": event_cover(e), "desc": e.description or "",
                    "attendees": e.attendees or "", "cat": e.category or "",
                    "promo": e.promo or ""})
    return JSONResponse(out)


# ---------- billing / оплата ----------

@app.post("/checkout/{plan}")
def checkout_create(plan: str, request: Request, job_id: int = Form(None),
                    db: Session = Depends(db_session)):
    user = get_user(request, db)
    if not user:
        return login_redirect(f"/post-job")
    if plan not in PLANS:
        raise HTTPException(404)
    if plan.startswith("cv") and user.role not in ("employer", "admin"):
        raise HTTPException(403)
    if user.role == "employer":
        _, account, team_role = require_company_user(request, db)
        if team_role != "owner":
            raise HTTPException(403)
        user = account
    name, amount, _ = PLANS[plan]
    o = Order(user_id=user.id, plan=plan, plan_name=name, amount=amount,
              job_id=job_id, status="pending")
    db.add(o)
    db.commit()
    return RedirectResponse(f"/checkout/order/{o.id}", status_code=303)


@app.get("/checkout/order/{order_id}", response_class=HTMLResponse)
def checkout_view(order_id: int, request: Request, db: Session = Depends(db_session)):
    user = get_user(request, db)
    o = db.get(Order, order_id)
    if not user or not o or (o.user_id != user.id and user.role != "admin"):
        raise HTTPException(403)
    return render(request, db, "checkout.html", order=o, plans=PLANS)


@app.post("/checkout/order/{order_id}/invoice")
def checkout_invoice(order_id: int, request: Request, db: Session = Depends(db_session)):
    user = get_user(request, db)
    o = db.get(Order, order_id)
    if not user or not o or o.user_id != user.id:
        raise HTTPException(403)
    o.method = "invoice"
    db.commit()
    return RedirectResponse(f"/checkout/order/{order_id}?sent=1", status_code=303)


@app.get("/job/{job_id}", response_class=HTMLResponse)
def job_detail(job_id: int, request: Request, db: Session = Depends(db_session)):
    job = db.get(Job, job_id)
    if not job or job.status not in ("approved", "archived"):
        raise HTTPException(404)
    job.views += 1
    viewer = get_user(request, db)
    track(db, "job_view", viewer.id if viewer else None, "job", job.id)
    db.commit()
    user = get_user(request, db)
    applied = bool(user and db.query(Application).filter_by(job_id=job.id, user_id=user.id).first())
    similar = (db.query(Job).filter(Job.status == "approved", Job.id != job.id,
                                    Job.category == job.category)
               .order_by(Job.featured.desc(), Job.created_at.desc()).limit(3).all())
    return render(request, db, "job.html", job=job, applied=applied,
                  applies=len(job.applications), similar=similar,
                  is_closed=job.status == "archived")


@app.post("/job/{job_id}/apply")
def job_apply(job_id: int, request: Request, cover: str = Form(""),
              db: Session = Depends(db_session)):
    user = get_user(request, db)
    if not user:
        return login_redirect(f"/job/{job_id}")
    if user.role != "talent":
        # работодателю/админу откликаться нельзя
        return RedirectResponse(f"/job/{job_id}", status_code=303)
    job = db.get(Job, job_id)
    if not job or job.status != "approved":
        raise HTTPException(404)
    # Отклик принимаем и на агрегированные вакансии — как лид: мы передаём его
    # работодателю и используем как аргумент подключить компанию к SpinHire.
    if not db.query(Application).filter_by(job_id=job_id, user_id=user.id).first():
        application = Application(job_id=job_id, user_id=user.id, cover=cover.strip())
        db.add(application)
        db.flush()
        db.add(ApplicationEvent(application_id=application.id, actor_id=user.id,
                                kind="created", body="Кандидат отправил отклик"))
        track(db, "application_created", user.id, "job", job_id)
        db.commit()
    return RedirectResponse(f"/job/{job_id}?ok=1", status_code=303)


# ---------- auth ----------

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/", db: Session = Depends(db_session)):
    return render(request, db, "login.html", next=next, error="")


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...),
          next: str = Form("/"), db: Session = Depends(db_session)):
    u = db.query(User).filter(func.lower(User.email) == email.strip().lower()).first()
    if not u or not check_pw(password, u.password_hash):
        return render(request, db, "login.html", next=next, error="Неверная почта или пароль")
    # почта не подтверждена (и Resend настроен) — отправляем код и ведём на /verify
    if REQUIRE_VERIFY and not u.verified:
        code = issue_otp(u, db)
        send_otp(u, code)
        _otp_last_send[u.email] = time.time()
        return RedirectResponse(f"/verify?email={urllib.parse.quote(u.email)}", status_code=303)
    dest = safe_next(next, dest_for(u)) if next and next != "/" else dest_for(u)
    return set_session(RedirectResponse(dest, status_code=303), u)


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request, role: str = "talent", next: str = "",
                  email: str = "", db: Session = Depends(db_session)):
    role = role if role in ("talent", "employer") else "talent"
    return render(request, db, "register.html", role=role, error="",
                  next=safe_next(next, "") if next else "", email=email.strip().lower())


@app.post("/register")
def register(request: Request, email: str = Form(...), password: str = Form(...),
             name: str = Form(""), role: str = Form("talent"),
             company_name: str = Form(""), next: str = Form(""),
             db: Session = Depends(db_session)):
    role = role if role in ("talent", "employer") else "talent"
    if db.query(User).filter(func.lower(User.email) == email.strip().lower()).first():
        return render(request, db, "register.html", role=role, next=next, email=email,
                      error="Такая почта уже зарегистрирована — войдите")
    if len(password) < 6:
        return render(request, db, "register.html", role=role, next=next, email=email,
                      error="Пароль — от 6 символов")
    u = User(email=email.strip().lower(), password_hash=hash_pw(password),
             name=name.strip(), role=role, company_name=company_name.strip(),
             coins=SIGNUP_COIN_BONUS)
    db.add(u)
    db.commit()
    # подтверждение почты: только если Resend настроен
    if REQUIRE_VERIFY:
        u.verified = 0
        db.commit()
        code = issue_otp(u, db)
        if send_otp(u, code):
            _otp_last_send[u.email] = time.time()
            return RedirectResponse(f"/verify?email={urllib.parse.quote(u.email)}",
                                    status_code=303)
        # письмо не ушло (напр. домен Resend ещё не подтверждён) — не блокируем вход
        print("[verify] OTP send failed on register — auto-verifying user")
        u.verified = 1
        u.otp_hash = ""
        u.otp_expires = ""
        db.commit()
    dest = safe_next(next, dest_for(u)) if next else dest_for(u)
    return set_session(RedirectResponse(dest, status_code=303), u)


@app.get("/logout")
def logout(next: str = ""):
    destination = f"/login?next={urllib.parse.quote(next, safe='')}" if safe_next(next, "") else "/"
    resp = RedirectResponse(destination, status_code=303)
    resp.delete_cookie("sh_session")
    return resp


# ---------- Google OAuth ----------

@app.get("/auth/google")
def auth_google(role: str = "", next: str = ""):
    if not GOOGLE_CLIENT_ID:
        return RedirectResponse("/login?e=google_off", status_code=307)
    requested_role = role if role in ("talent", "employer") else ""
    requested_next = safe_next(next, "") if next else ""
    state = secrets.token_urlsafe(24)
    params = urllib.parse.urlencode({
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": BASE_URL + "/auth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    })
    resp = RedirectResponse(
        f"https://accounts.google.com/o/oauth2/v2/auth?{params}", status_code=307)
    # состояние — в подписанной короткоживущей куке (тот же signer)
    resp.set_cookie("sh_oauth", signer.dumps({"state": state, "role": requested_role,
                                               "next": requested_next}),
                    max_age=600, httponly=True, samesite="lax")
    return resp


@app.get("/auth/google/callback")
def auth_google_callback(request: Request, code: str = "", state: str = "",
                         db: Session = Depends(db_session)):
    fail = RedirectResponse("/login?e=google_fail", status_code=303)
    try:
        raw = request.cookies.get("sh_oauth")
        if not raw or not code or not state:
            return fail
        try:
            oauth_data = signer.loads(raw)
            saved = oauth_data.get("state")
        except BadSignature:
            return fail
        if not saved or not secrets.compare_digest(str(saved), str(state)):
            return fail
        requested_role = oauth_data.get("role", "")
        requested_role = requested_role if requested_role in ("talent", "employer") else ""
        requested_next = safe_next(oauth_data.get("next", ""), "")

        # обмен кода на access_token
        token_body = urllib.parse.urlencode({
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": BASE_URL + "/auth/google/callback",
            "grant_type": "authorization_code",
        }).encode("utf-8")
        status, body = _http_post(
            "https://oauth2.googleapis.com/token", data=token_body,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        if not (200 <= status < 300):
            print(f"[google] token exchange failed: status={status}")
            return fail
        access_token = json.loads(body).get("access_token")
        if not access_token:
            return fail

        # профиль
        status, body = _http_get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"})
        if not (200 <= status < 300):
            print(f"[google] userinfo failed: status={status}")
            return fail
        info = json.loads(body)
        email = (info.get("email") or "").strip().lower()
        if not email:
            return fail
        name = (info.get("name") or "").strip()

        u = db.query(User).filter(func.lower(User.email) == email).first()
        if not u:
            u = User(email=email, password_hash=hash_pw(secrets.token_urlsafe(24)),
                     name=name, role=requested_role or "talent", verified=1,
                     coins=SIGNUP_COIN_BONUS)
            db.add(u)
            db.commit()
        elif requested_role and u.role != "admin" and u.role != requested_role:
            # Явный выбор на регистрации также исправляет аккаунты, которые
            # старый Google-flow ошибочно создавал соискателями.
            u.role = requested_role
            u.verified = 1
            db.commit()
        elif not u.verified:
            # вход через Google подтверждает владение почтой
            u.verified = 1
            u.otp_hash = ""
            u.otp_expires = ""
            db.commit()

        destination = requested_next or dest_for(u)
        resp = set_session(RedirectResponse(destination, status_code=303), u)
        resp.delete_cookie("sh_oauth")
        return resp
    except Exception as e:  # noqa: BLE001 — любой сбой ведёт на /login, не 500
        print(f"[google] callback error: {type(e).__name__}")
        return fail


# ---------- email verification ----------

@app.get("/verify", response_class=HTMLResponse)
def verify_page(request: Request, email: str = "", sent: int = 0,
                db: Session = Depends(db_session)):
    return render(request, db, "verify.html", email=email.strip().lower(),
                  error="", sent=bool(sent))


@app.post("/verify")
def verify(request: Request, email: str = Form(...), code: str = Form(...),
           db: Session = Depends(db_session)):
    em = email.strip().lower()
    u = db.query(User).filter(func.lower(User.email) == em).first()

    def fail(msg):
        return render(request, db, "verify.html", email=em, error=msg, sent=False)

    if not u:
        return fail("Пользователь не найден. Зарегистрируйтесь заново.")
    if u.verified:
        return set_session(RedirectResponse(dest_for(u), status_code=303), u)
    if not u.otp_hash or not u.otp_expires:
        return fail("Код не запрашивался. Отправьте новый код.")
    try:
        expires = datetime.fromisoformat(u.otp_expires)
    except (ValueError, TypeError):
        return fail("Код повреждён. Отправьте новый код.")
    if datetime.utcnow() > expires:
        return fail("Код истёк. Отправьте новый код.")
    if (u.otp_attempts or 0) >= _OTP_MAX_ATTEMPTS:
        return fail("Слишком много попыток. Отправьте новый код.")

    u.otp_attempts = (u.otp_attempts or 0) + 1
    db.commit()
    if not secrets.compare_digest(u.otp_hash, _hash_otp(u.email, code.strip())):
        return fail("Неверный код. Проверьте и попробуйте ещё раз.")

    u.verified = 1
    u.otp_hash = ""
    u.otp_expires = ""
    u.otp_attempts = 0
    db.commit()
    return set_session(RedirectResponse(dest_for(u), status_code=303), u)


@app.get("/verify/resend")
def verify_resend(email: str = "", db: Session = Depends(db_session)):
    em = email.strip().lower()
    u = db.query(User).filter(func.lower(User.email) == em).first()
    if u and not u.verified and REQUIRE_VERIFY:
        now = time.time()
        if now - _otp_last_send.get(em, 0) >= _OTP_RESEND_COOLDOWN:
            code = issue_otp(u, db)
            if send_otp(u, code):
                _otp_last_send[em] = now
    return RedirectResponse(
        f"/verify?email={urllib.parse.quote(em)}&sent=1", status_code=303)


# ---------- talent cabinet ----------

def resume_contact_access(user: User, resume: Resume, db: Session) -> bool:
    """Контакты никогда не попадают в ответ без владельца, админа или оплаченного доступа."""
    if not user:
        return False
    if user.id == resume.user_id or user.role == "admin":
        return True
    if user.role != "employer":
        return False
    account, _ = company_context(user, db)
    if account.cv_access_until:
        try:
            if datetime.fromisoformat(account.cv_access_until) > datetime.utcnow():
                return True
        except ValueError:
            pass
    return db.query(ResumeUnlock).filter_by(
        employer_id=account.id, resume_id=resume.id).first() is not None


def add_notification(db: Session, user_id: int, kind: str, title: str,
                     body: str = "", link: str = ""):
    db.add(Notification(user_id=user_id, kind=kind, title=title[:180],
                        body=body[:1000], link=link[:500]))


def track(db: Session, name: str, user_id=None, entity_type="", entity_id=None, **meta):
    db.add(AnalyticsEvent(name=name, user_id=user_id, entity_type=entity_type,
                          entity_id=entity_id, meta=json.dumps(meta, ensure_ascii=False)[:2000]))


def anonymize_resume_text(value: str) -> str:
    """Убрать случайно вставленные контакты из публичной части CV."""
    import re
    text = value.strip()
    text = re.sub(r"(?i)\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b", "[контакт скрыт]", text)
    text = re.sub(r"(?i)https?://\S+|(?:www\.)\S+", "[ссылка скрыта]", text)
    text = re.sub(r"(?<!\w)@[A-Za-z0-9_]{4,}", "[контакт скрыт]", text)
    text = re.sub(r"(?<!\w)\+?\d[\d\s().-]{8,}\d", "[телефон скрыт]", text)
    return text


@app.get("/resumes", response_class=HTMLResponse)
def resumes(request: Request, q: str = "", location: str = "", fmt: str = "",
            db: Session = Depends(db_session)):
    query = (db.query(Resume).join(User, User.id == Resume.user_id)
             .filter(Resume.published == True, Resume.status == "approved",  # noqa: E712
                     User.job_search_status != "paused"))
    if q.strip():
        needle = f"%{q.strip()}%"
        query = query.filter(or_(Resume.title.ilike(needle), Resume.skills.ilike(needle),
                                 Resume.about.ilike(needle), Resume.languages.ilike(needle)))
    if location.strip():
        query = query.filter(Resume.location.ilike(f"%{location.strip()}%"))
    if fmt.strip():
        query = query.filter(Resume.desired_format == fmt.strip())
    rows = query.order_by(Resume.updated_at.desc()).all()
    return render(request, db, "resumes.html", resumes=rows, q=q, location=location,
                  fmt=fmt, formats=FORMATS, active="resumes")


@app.get("/resume/{resume_id}", response_class=HTMLResponse)
def resume_detail(resume_id: int, request: Request, db: Session = Depends(db_session)):
    row = db.get(Resume, resume_id)
    user = get_user(request, db)
    is_owner_or_admin = bool(user and (user.id == row.user_id or user.role == "admin")) if row else False
    unavailable = bool(row and (not row.published or row.status != "approved"
                                or row.user.job_search_status == "paused"))
    if not row or (unavailable and not is_owner_or_admin):
        raise HTTPException(404)
    if not is_owner_or_admin:
        row.views = (row.views or 0) + 1
        db.commit()
    unlocked = resume_contact_access(user, row, db)
    cv_account, cv_team_role = company_context(user, db) if user and user.role == "employer" else (user, "owner")
    return render(request, db, "resume.html", resume=row, unlocked=unlocked,
                  active="resumes", cv_account=cv_account, cv_team_role=cv_team_role)


@app.get("/resume/{resume_id}/file")
def resume_file(resume_id: int, request: Request, db: Session = Depends(db_session)):
    """Исходный CV доступен только владельцу, админу или работодателю с открытым контактом."""
    row = db.get(Resume, resume_id)
    user = get_user(request, db)
    if not row or not row.cv_file_path or not resume_contact_access(user, row, db):
        raise HTTPException(404)
    path = os.path.abspath(row.cv_file_path)
    upload_root = os.path.abspath(CV_UPLOAD_DIR) + os.sep
    if not path.startswith(upload_root) or not os.path.isfile(path):
        raise HTTPException(404)
    return FileResponse(path, filename=row.cv_file_name or "candidate-cv.pdf",
                        media_type="application/octet-stream")


@app.get("/resume/{resume_id}/avatar")
def resume_avatar(resume_id: int, request: Request, db: Session = Depends(db_session)):
    """Фото раскрывается вместе с контактами, но не в анонимной базе."""
    row = db.get(Resume, resume_id)
    user = get_user(request, db)
    if not row or not resume_contact_access(user, row, db):
        raise HTTPException(404)
    path = os.path.abspath(row.user.avatar_file_path or "")
    upload_root = os.path.abspath(AVATAR_UPLOAD_DIR) + os.sep
    if not path.startswith(upload_root) or not os.path.isfile(path):
        raise HTTPException(404)
    return FileResponse(path)


@app.post("/resume/{resume_id}/unlock")
def resume_unlock(resume_id: int, request: Request, db: Session = Depends(db_session)):
    user = get_user(request, db)
    if not user:
        return login_redirect(f"/resume/{resume_id}")
    _, account, _ = require_company_user(request, db, write=True)
    row = db.get(Resume, resume_id)
    if (not row or not row.published or row.status != "approved"
            or row.user.job_search_status == "paused"):
        raise HTTPException(404)
    if db.query(ResumeUnlock).filter_by(employer_id=account.id, resume_id=row.id).first():
        return RedirectResponse(f"/resume/{resume_id}?unlocked=1", status_code=303)
    unlimited = False
    if account.cv_access_until:
        try:
            unlimited = datetime.fromisoformat(account.cv_access_until) > datetime.utcnow()
        except ValueError:
            unlimited = False
    if not unlimited:
        charged = (db.query(User).filter(User.id == account.id, User.cv_credits > 0)
                   .update({User.cv_credits: User.cv_credits - 1}, synchronize_session=False))
        if charged != 1:
            db.rollback()
            return RedirectResponse(f"/resume/{resume_id}?need_plan=1", status_code=303)
    try:
        db.add(ResumeUnlock(employer_id=account.id, resume_id=row.id,
                            access_kind="unlimited" if unlimited else "credit"))
        row.unlock_count = (row.unlock_count or 0) + 1
        db.flush()
        db.refresh(account)
        db.add(ResumeCreditLedger(employer_id=account.id, resume_id=row.id,
                                  delta=0 if unlimited else -1,
                                  balance_after=account.cv_credits or 0,
                                  action="unlimited" if unlimited else "unlock"))
        track(db, "resume_unlocked", user.id, "resume", row.id, account_id=account.id)
        db.commit()
    except IntegrityError:
        db.rollback()
    return RedirectResponse(f"/resume/{resume_id}?unlocked=1", status_code=303)

@app.get("/profile", response_class=HTMLResponse)
def profile(request: Request, db: Session = Depends(db_session)):
    user = get_user(request, db)
    if not user:
        return login_redirect("/profile")
    if user.role == "employer":
        return RedirectResponse("/employer")
    if user.role == "admin":
        return RedirectResponse("/admin")
    apps = (db.query(Application).filter_by(user_id=user.id)
            .order_by(Application.created_at.desc()).all())
    spin_ready = (user.last_spin is None
                  or (datetime.utcnow() - user.last_spin).total_seconds() > 20 * 3600)
    resume = db.query(Resume).filter_by(user_id=user.id).first()
    resume_unlocks = db.query(ResumeUnlock).filter_by(resume_id=resume.id).count() if resume else 0
    profile_checks = [user.name, user.headline, user.location, user.salary_expect, user.languages,
                      resume and resume.title, resume and resume.skills, resume and resume.about,
                      resume and resume.contact_telegram, resume and resume.employment_history,
                      resume and resume.preferred_locations, resume and resume.availability]
    profile_progress = round(sum(bool(value) for value in profile_checks) / len(profile_checks) * 100)
    app_counts = {status: sum(a.status == status for a in apps)
                  for status in ("new", "viewed", "invited", "offer", "hired", "rejected")}
    applied_job_ids = [a.job_id for a in apps]
    category = guess_category(user.headline, resume.skills if resume else "")
    recommendations = (db.query(Job).filter(Job.status == "approved", Job.category == category,
                                             ~Job.id.in_(applied_job_ids) if applied_job_ids else True)
                       .order_by(Job.featured.desc(), Job.created_at.desc()).limit(4).all())
    notifications = (db.query(Notification).filter_by(user_id=user.id)
                     .order_by(Notification.created_at.desc()).limit(20).all())
    return render(request, db, "profile.html", apps=apps, spin_ready=spin_ready,
                  resume=resume, resume_unlocks=resume_unlocks, formats=FORMATS,
                  profile_progress=profile_progress, app_counts=app_counts,
                  recommendations=recommendations, notifications=notifications)


@app.post("/account/role/{target_role}")
def account_role(target_role: str, request: Request, db: Session = Depends(db_session)):
    user = get_user(request, db)
    if not user:
        return login_redirect("/profile")
    if user.role == "admin" or target_role not in ("talent", "employer"):
        raise HTTPException(403)
    user.role = target_role
    db.commit()
    return RedirectResponse(dest_for(user), status_code=303)


@app.post("/profile/notifications/read")
def notifications_read(request: Request, db: Session = Depends(db_session)):
    user = get_user(request, db)
    if not user:
        return login_redirect("/profile")
    now = datetime.utcnow().isoformat() + "Z"
    db.query(Notification).filter(Notification.user_id == user.id,
                                  Notification.read_at == "").update(
        {Notification.read_at: now}, synchronize_session=False)
    db.commit()
    return RedirectResponse("/profile#notifications", status_code=303)


@app.post("/profile/spin")
def profile_spin(request: Request, db: Session = Depends(db_session)):
    import random
    user = get_user(request, db)
    if not user or user.role != "talent":
        return login_redirect("/profile")
    if user.last_spin and (datetime.utcnow() - user.last_spin).total_seconds() < 20 * 3600:
        return RedirectResponse("/profile?spin=wait", status_code=303)
    # взвешенный выигрыш: чаще мелочь, редко крупно (мерч специально долгий)
    prize = random.choices([10, 20, 30, 50, 100, 200],
                           weights=[34, 27, 18, 12, 7, 2])[0]
    user.coins = (user.coins or 0) + prize
    user.last_spin = datetime.utcnow()
    db.commit()
    return RedirectResponse(f"/profile?spin={prize}", status_code=303)


@app.post("/profile")
def profile_save(request: Request, name: str = Form(""), headline: str = Form(""),
                 salary_expect: str = Form(""), languages: str = Form(""),
                 location: str = Form(""),
                 job_search_status: str = Form("active"),
                 incognito: str = Form(None), db: Session = Depends(db_session)):
    user = get_user(request, db)
    if not user:
        return login_redirect("/profile")
    user.name, user.headline = name.strip(), headline.strip()
    user.salary_expect, user.languages = salary_expect.strip(), languages.strip()
    user.location = location.strip()
    user.job_search_status = job_search_status if job_search_status in ("active", "open", "paused") else "active"
    user.incognito = bool(incognito)
    db.commit()
    return RedirectResponse("/profile?ok=1", status_code=303)


def valid_avatar_payload(payload: bytes, ext: str) -> bool:
    """Проверяем реальный формат изображения, а не только имя файла."""
    signatures = {
        ".jpg": payload.startswith(b"\xff\xd8\xff"),
        ".jpeg": payload.startswith(b"\xff\xd8\xff"),
        ".png": payload.startswith(b"\x89PNG\r\n\x1a\n"),
        ".webp": len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP",
    }
    return signatures.get(ext, False)


@app.get("/company-logo/{account_id}")
def company_logo(account_id: int, db: Session = Depends(db_session)):
    """Загруженный работодателем логотип — публичный, кэшируется."""
    account = db.get(User, account_id)
    path = os.path.abspath((account and account.company_logo_path) or "")
    root = os.path.abspath(COMPANY_LOGO_DIR) + os.sep
    if not path.startswith(root) or not os.path.isfile(path):
        raise HTTPException(404)
    return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})


@app.get("/profile/avatar")
def profile_avatar(request: Request, db: Session = Depends(db_session)):
    user = get_user(request, db)
    if not user:
        raise HTTPException(404)
    path = user.avatar_file_path or ""
    if not path or not os.path.isfile(path):
        raise HTTPException(404)
    return FileResponse(path, filename=user.avatar_file_name or os.path.basename(path))


@app.post("/profile/resume")
async def profile_resume_save(request: Request, title: str = Form(""), location: str = Form(""),
                        experience_years: int = Form(0), skills: str = Form(""),
                        about: str = Form(""), desired_format: str = Form("удалёнка"),
                        salary_expect: str = Form(""), languages: str = Form(""),
                        contact_email: str = Form(""), contact_telegram: str = Form(""),
                        publish: str = Form(None), consent: str = Form(None),
                        cv_file: UploadFile | None = File(None),
                        remove_cv_file: str = Form(None),
                        employment_history: str = Form(""), education: str = Form(""),
                        preferred_locations: str = Form(""), relocation: str = Form(None),
                        availability: str = Form(""), portfolio_url: str = Form(""),
                        linkedin_url: str = Form(""),
                        avatar_file: UploadFile | None = File(None),
                        db: Session = Depends(db_session)):
    user = get_user(request, db)
    if not user or user.role != "talent":
        return login_redirect("/profile#cv")
    row = db.query(Resume).filter_by(user_id=user.id).first()
    if not row:
        row = Resume(user_id=user.id)
        db.add(row)
    old_public = (row.title, row.location, row.experience_years, row.skills, row.about,
                  row.desired_format, row.salary_expect, row.languages, row.employment_history,
                  row.education, row.preferred_locations, row.relocation, row.availability)
    wants_publish = bool(publish)
    if not wants_publish or not consent:
        return RedirectResponse("/profile?cv_error=consent#cv", status_code=303)
    if not title.strip() or not about.strip():
        return RedirectResponse("/profile?cv_error=1#cv", status_code=303)
    avatar_name = avatar_ext = ""
    avatar_payload = b""
    if not avatar_file or not avatar_file.filename:
        if not user.avatar_file_path or not os.path.isfile(user.avatar_file_path):
            return RedirectResponse("/profile?cv_error=avatar#cv", status_code=303)
    else:
        avatar_name = os.path.basename(avatar_file.filename).strip()
        avatar_ext = os.path.splitext(avatar_name)[1].lower()
        avatar_payload = await avatar_file.read(AVATAR_MAX_BYTES + 1)
        if len(avatar_payload) > AVATAR_MAX_BYTES:
            return RedirectResponse("/profile?avatar_error=size#cv", status_code=303)
        if not valid_avatar_payload(avatar_payload, avatar_ext):
            return RedirectResponse("/profile?avatar_error=type#cv", status_code=303)
    row.title = title.strip()
    row.location = location.strip()
    row.experience_years = max(0, min(int(experience_years or 0), 60))
    row.skills = anonymize_resume_text(skills)
    row.about = anonymize_resume_text(about)
    row.desired_format = desired_format if desired_format in FORMATS else "удалёнка"
    row.salary_expect = salary_expect.strip()
    row.languages = languages.strip()
    row.contact_email = contact_email.strip() or user.email
    row.contact_telegram = contact_telegram.strip()
    row.employment_history = anonymize_resume_text(employment_history)
    row.education = anonymize_resume_text(education)
    row.preferred_locations = preferred_locations.strip()[:500]
    row.relocation = bool(relocation)
    row.availability = availability.strip()[:120]
    portfolio = portfolio_url.strip()
    row.portfolio_url = portfolio[:500] if portfolio.startswith(("https://", "http://")) else ""
    linkedin = linkedin_url.strip()
    row.linkedin_url = linkedin[:500] if linkedin.startswith(("https://www.linkedin.com/", "https://linkedin.com/")) else ""
    if remove_cv_file and row.cv_file_path:
        try:
            os.remove(row.cv_file_path)
        except FileNotFoundError:
            pass
        row.cv_file_name = row.cv_file_path = ""
    if cv_file and cv_file.filename:
        safe_name = os.path.basename(cv_file.filename).strip()
        ext = os.path.splitext(safe_name)[1].lower()
        if ext not in (".pdf", ".doc", ".docx"):
            return RedirectResponse("/profile?cv_file_error=type#cv", status_code=303)
        payload = await cv_file.read(CV_MAX_BYTES + 1)
        if len(payload) > CV_MAX_BYTES:
            return RedirectResponse("/profile?cv_file_error=size#cv", status_code=303)
        os.makedirs(CV_UPLOAD_DIR, exist_ok=True)
        stored_path = os.path.join(CV_UPLOAD_DIR, f"{user.id}-{secrets.token_hex(12)}{ext}")
        with open(stored_path, "wb") as handle:
            handle.write(payload)
        previous_path = row.cv_file_path
        row.cv_file_name, row.cv_file_path = safe_name[:240], stored_path
        if previous_path and previous_path != stored_path:
            try:
                os.remove(previous_path)
            except FileNotFoundError:
                pass
    if avatar_payload:
        os.makedirs(AVATAR_UPLOAD_DIR, exist_ok=True)
        avatar_path = os.path.join(AVATAR_UPLOAD_DIR, f"{user.id}-{secrets.token_hex(12)}{avatar_ext}")
        with open(avatar_path, "wb") as handle:
            handle.write(avatar_payload)
        previous_avatar = user.avatar_file_path
        user.avatar_file_name, user.avatar_file_path = avatar_name[:240], avatar_path
        if previous_avatar and previous_avatar != avatar_path:
            try:
                os.remove(previous_avatar)
            except FileNotFoundError:
                pass
    row.published = wants_publish
    row.consent_at = datetime.utcnow().isoformat() + "Z" if wants_publish else row.consent_at
    new_public = (row.title, row.location, row.experience_years, row.skills, row.about,
                  row.desired_format, row.salary_expect, row.languages, row.employment_history,
                  row.education, row.preferred_locations, row.relocation, row.availability)
    if not wants_publish:
        row.status = "paused" if row.status == "approved" else "draft"
    elif row.status == "approved" and old_public == new_public:
        row.status = "approved"
    else:
        row.status = "pending"
        row.submitted_at = datetime.utcnow().isoformat() + "Z"
        row.moderation_note = ""
    row.updated_at = datetime.utcnow()
    user.headline = row.title
    user.salary_expect = row.salary_expect
    user.languages = row.languages
    db.commit()
    return RedirectResponse("/profile?cv_ok=1#cv", status_code=303)


@app.post("/profile/resume/linkedin")
def profile_resume_linkedin(request: Request, linkedin_url: str = Form(""),
                            db: Session = Depends(db_session)):
    user = get_user(request, db)
    if not user or user.role != "talent":
        return login_redirect("/profile#cv")
    url = linkedin_url.strip()
    if not url.startswith(("https://www.linkedin.com/", "https://linkedin.com/")):
        return RedirectResponse("/profile?linkedin_error=1#cv", status_code=303)
    row = db.query(Resume).filter_by(user_id=user.id).first()
    if not row:
        row = Resume(user_id=user.id)
        db.add(row)
    row.linkedin_url = url[:500]
    row.title = row.title or (user.headline or "").strip()
    row.location = row.location or (user.location or "").strip()
    row.salary_expect = row.salary_expect or (user.salary_expect or "").strip()
    row.languages = row.languages or (user.languages or "").strip()
    row.contact_email = row.contact_email or user.email
    row.status = "draft"
    row.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse("/profile?cv_source=linkedin#cv", status_code=303)


# ---------- employer cabinet ----------

@app.get("/employer", response_class=HTMLResponse)
def employer(request: Request, stage: str = "", assigned: int = 0,
             db: Session = Depends(db_session)):
    user = get_user(request, db)
    if not user:
        return login_redirect("/employer")
    if user.role == "talent":
        return RedirectResponse("/profile")
    account, team_role = company_context(user, db)
    jobs = (db.query(Job).filter(Job.owner_id == account.id)
            .order_by(Job.created_at.desc()).all())
    unlocked = (db.query(Resume).join(ResumeUnlock, ResumeUnlock.resume_id == Resume.id)
                .filter(ResumeUnlock.employer_id == account.id)
                .order_by(ResumeUnlock.created_at.desc()).all())
    ledger = (db.query(ResumeCreditLedger).filter_by(employer_id=account.id)
              .order_by(ResumeCreditLedger.created_at.desc()).limit(8).all())
    applications = [application for job in jobs for application in job.applications]
    ats_apps = [a for a in applications if (not stage or a.status == stage)
                and (not assigned or a.assigned_to == assigned)]
    total_views = sum(job.views or 0 for job in jobs)
    week_ago = datetime.utcnow() - timedelta(days=7)
    job_ids = [job.id for job in jobs]
    views_7d = 0
    if job_ids:
        views_7d = (db.query(func.count(AnalyticsEvent.id))
                    .filter(AnalyticsEvent.name == "job_view",
                            AnalyticsEvent.entity_type == "job",
                            AnalyticsEvent.entity_id.in_(job_ids),
                            AnalyticsEvent.created_at >= week_ago).scalar() or 0)
    applications_7d = sum(1 for a in applications if a.created_at and a.created_at >= week_ago)
    unlocks_total = (db.query(func.count(ResumeUnlock.id))
                     .filter(ResumeUnlock.employer_id == account.id).scalar() or 0)
    stats = {
        "active_jobs": sum(job.status == "approved" for job in jobs),
        "pending_jobs": sum(job.status == "pending" for job in jobs),
        "views": total_views,
        "applications": len(applications),
        "new_applications": sum(application.status == "new" for application in applications),
        "offers": sum(application.status == "offer" for application in applications),
        "hired": sum(application.status == "hired" for application in applications),
        "views_7d": views_7d,
        "applications_7d": applications_7d,
        "unlocks": unlocks_total,
        "conversion": round(len(applications) / total_views * 100, 1) if total_views else 0.0,
    }
    # построчная статистика: что именно работает, а что висит без откликов
    now = datetime.utcnow()
    job_stats = []
    for job in jobs:
        job_apps = job.applications
        views = job.views or 0
        first_app = min((a.created_at for a in job_apps if a.created_at), default=None)
        job_stats.append({
            "job": job,
            "views": views,
            "applications": len(job_apps),
            "new": sum(a.status == "new" for a in job_apps),
            "conversion": round(len(job_apps) / views * 100, 1) if views else 0.0,
            "days_live": max((now - job.created_at).days, 0) if job.created_at else 0,
            "days_to_first": (first_app - job.created_at).days if first_app and job.created_at else None,
        })
    job_stats.sort(key=lambda row: row["views"], reverse=True)
    company_checks = [account.company_name, account.company_website, account.company_description,
                      account.company_location, account.company_size, account.company_logo_path]
    company_progress = round(sum(bool(value) for value in company_checks) / len(company_checks) * 100)
    team = (db.query(CompanyMember, User).join(User, User.id == CompanyMember.user_id)
            .filter(CompanyMember.account_id == account.id).order_by(CompanyMember.created_at).all())
    invites = (db.query(CompanyInvite).filter_by(account_id=account.id, status="pending")
               .order_by(CompanyInvite.created_at.desc()).all())
    return render(request, db, "employer.html", jobs=jobs, unlocked_resumes=unlocked,
                  credit_ledger=ledger, stats=stats, company_progress=company_progress,
                  account=account, team_role=team_role, team=team, invites=invites,
                  ats_apps=ats_apps, stage=stage, assigned=assigned,
                  job_stats=job_stats)


@app.post("/employer/profile")
async def employer_profile_save(request: Request, company_name: str = Form(""),
                          company_website: str = Form(""), company_description: str = Form(""),
                          company_location: str = Form(""), company_size: str = Form(""),
                          company_logo: UploadFile = File(None),
                          db: Session = Depends(db_session)):
    user, account, _ = require_company_user(request, db, owner_only=True)
    website = company_website.strip()
    if website and not website.startswith(("https://", "http://")):
        website = "https://" + website
    if website and urllib.parse.urlparse(website).scheme not in ("http", "https"):
        website = ""
    account.company_name = company_name.strip()[:180]
    account.company_website = website[:500]
    account.company_description = company_description.strip()[:3000]
    account.company_location = company_location.strip()[:180]
    account.company_size = company_size.strip()[:80]
    if company_logo and company_logo.filename:
        ext = os.path.splitext(company_logo.filename)[1].lower()
        payload = await company_logo.read()
        if ext in (".png", ".jpg", ".jpeg", ".webp") and len(payload) <= 2 * 1024 * 1024 and valid_avatar_payload(payload, ext):
            os.makedirs(COMPANY_LOGO_DIR, exist_ok=True)
            path = os.path.join(COMPANY_LOGO_DIR, f"{account.id}-{secrets.token_hex(8)}{ext}")
            with open(path, "wb") as handle:
                handle.write(payload)
            previous = account.company_logo_path
            account.company_logo_path = path
            if previous and previous != path:
                try:
                    os.remove(previous)
                except FileNotFoundError:
                    pass
    for job in db.query(Job).filter(Job.owner_id == account.id).all():
        if account.company_name:
            job.company_name = account.company_name
    db.commit()
    return RedirectResponse("/employer?profile_ok=1", status_code=303)


@app.post("/employer/app/{app_id}/status")
def app_status(app_id: int, request: Request, status: str = Form(...),
               db: Session = Depends(db_session)):
    user, account, _ = require_company_user(request, db, write=True)
    a = db.get(Application, app_id)
    if not a or (a.job.owner_id != account.id and user.role != "admin"):
        raise HTTPException(403)
    if status in ("new", "viewed", "invited", "offer", "hired", "rejected") and status != a.status:
        a.status = status
        labels = {"viewed": "Отклик просмотрен", "invited": "Приглашение на интервью",
                  "offer": "Вам сделали оффер", "hired": "Вы приняты",
                  "rejected": "Статус отклика обновлён", "new": "Отклик возвращён в новые"}
        add_notification(db, a.user_id, "application", labels[status],
                         f"{a.job.company_name}: {a.job.title}", f"/job/{a.job_id}")
        db.add(ApplicationEvent(application_id=a.id, actor_id=user.id,
                                kind="status", body=labels[status]))
        track(db, "application_status", user.id, "application", a.id, status=status)
        db.commit()
        if status in ("invited", "offer", "hired"):
            safe_label = html.escape(labels[status])
            safe_company = html.escape(a.job.company_name or "")
            safe_title = html.escape(a.job.title or "")
            resend_send(a.user.email, f"SpinHire — {labels[status]}",
                        f"<p><b>{safe_label}</b></p><p>{safe_company}: {safe_title}</p>"
                        f'<p><a href="{BASE_URL or "https://spinhire.io"}/profile">Открыть кабинет</a></p>')
    return RedirectResponse("/employer", status_code=303)


@app.post("/employer/app/{app_id}/note")
def app_note(app_id: int, request: Request, note: str = Form(""),
             db: Session = Depends(db_session)):
    user, account, _ = require_company_user(request, db, write=True)
    application = db.get(Application, app_id)
    if not application or (
            application.job.owner_id != account.id and user.role != "admin"):
        raise HTTPException(403)
    application.employer_note = note.strip()[:2000]
    if application.employer_note:
        db.add(ApplicationEvent(application_id=application.id, actor_id=user.id,
                                kind="note", body=application.employer_note))
    db.commit()
    return RedirectResponse(f"/employer#application-{app_id}", status_code=303)


@app.get("/employer/application/{app_id}", response_class=HTMLResponse)
def application_detail(app_id: int, request: Request, db: Session = Depends(db_session)):
    user, account, team_role = require_company_user(request, db)
    application = db.get(Application, app_id)
    if not application or (application.job.owner_id != account.id and user.role != "admin"):
        raise HTTPException(404)
    members = (db.query(CompanyMember, User).join(User, User.id == CompanyMember.user_id)
               .filter(CompanyMember.account_id == account.id).all())
    events = (db.query(ApplicationEvent).filter_by(application_id=application.id)
              .order_by(ApplicationEvent.created_at.desc()).all())
    resume = db.query(Resume).filter_by(user_id=application.user_id).first()
    return render(request, db, "application.html", application=application, events=events,
                  resume=resume, account=account, team_role=team_role, members=members)


@app.post("/employer/application/{app_id}/plan")
def application_plan(app_id: int, request: Request, assigned_to: int = Form(0),
                     interview_at: str = Form(""), next_action_at: str = Form(""),
                     db: Session = Depends(db_session)):
    user, account, _ = require_company_user(request, db, write=True)
    application = db.get(Application, app_id)
    if not application or application.job.owner_id != account.id:
        raise HTTPException(404)
    allowed_ids = {account.id} | {m.user_id for m in db.query(CompanyMember).filter_by(account_id=account.id)}
    application.assigned_to = assigned_to if assigned_to in allowed_ids else None
    application.interview_at = interview_at.strip()[:40]
    application.next_action_at = next_action_at.strip()[:40]
    db.add(ApplicationEvent(application_id=application.id, actor_id=user.id, kind="plan",
                            body=f"План обновлён: интервью {application.interview_at or '—'}, следующее действие {application.next_action_at or '—'}"))
    db.commit()
    return RedirectResponse(f"/employer/application/{app_id}?saved=1", status_code=303)


@app.post("/employer/team/invite")
def team_invite(request: Request, email: str = Form(...), role: str = Form("recruiter"),
                db: Session = Depends(db_session)):
    user, account, _ = require_company_user(request, db, owner_only=True)
    target_email = email.strip().lower()
    if not target_email or "@" not in target_email or target_email == account.email.lower():
        return RedirectResponse("/employer?invite_error=1#team", status_code=303)
    role = role if role in ("recruiter", "viewer") else "recruiter"
    target = db.query(User).filter(func.lower(User.email) == target_email).first()
    if target and db.query(CompanyMember).filter_by(user_id=target.id).first():
        return RedirectResponse("/employer?invite_error=member#team", status_code=303)
    db.query(CompanyInvite).filter_by(account_id=account.id, email=target_email,
                                      status="pending").update(
        {CompanyInvite.status: "revoked"}, synchronize_session=False)
    token = secrets.token_urlsafe(32)
    invite = CompanyInvite(account_id=account.id, invited_by=user.id, email=target_email,
                            role=role, token_hash=hashlib.sha256(token.encode()).hexdigest(),
                            expires_at=(datetime.utcnow() + timedelta(days=7)).isoformat())
    db.add(invite)
    db.commit()
    accept_url = f"{BASE_URL or 'https://spinhire.io'}/employer/invite/{token}/accept"
    resend_send(target_email, f"Приглашение в команду {account.company_name or 'SpinHire'}",
                f"<p>Вас пригласили в кабинет компании <b>{html.escape(account.company_name or account.email)}</b>.</p>"
                f'<p><a href="{html.escape(accept_url)}">Принять приглашение</a></p><p>Ссылка действует 7 дней.</p>')
    return RedirectResponse("/employer?invite_sent=1#team", status_code=303)


@app.get("/employer/invite/{token}/accept")
def team_invite_accept(token: str, request: Request, db: Session = Depends(db_session)):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    invite = db.query(CompanyInvite).filter_by(token_hash=token_hash, status="pending").first()
    try:
        valid = bool(invite and datetime.fromisoformat(invite.expires_at) > datetime.utcnow())
    except (TypeError, ValueError):
        valid = False
    if not valid:
        return RedirectResponse("/login?invite_error=expired", status_code=303)
    user = get_user(request, db)
    accept_path = f"/employer/invite/{token}/accept"
    if not user:
        existing = db.query(User).filter(func.lower(User.email) == invite.email).first()
        if existing:
            return RedirectResponse(f"/login?next={urllib.parse.quote(accept_path)}", status_code=303)
        params = urllib.parse.urlencode({"role": "employer", "next": accept_path,
                                         "email": invite.email})
        return RedirectResponse(f"/register?{params}", status_code=303)
    if user.email.lower() != invite.email.lower():
        raise HTTPException(403)
    existing_membership = db.query(CompanyMember).filter_by(user_id=user.id).first()
    if existing_membership and existing_membership.account_id != invite.account_id:
        raise HTTPException(409, "Аккаунт уже состоит в другой компании")
    if (db.query(Job).filter_by(owner_id=user.id).count()
            or db.query(CompanyMember).filter_by(account_id=user.id).count()):
        raise HTTPException(409, "Нельзя присоединить владельца другого кабинета")
    if not existing_membership:
        db.add(CompanyMember(account_id=invite.account_id, user_id=user.id, role=invite.role))
    user.role = "employer"
    invite.status = "accepted"
    db.commit()
    return RedirectResponse("/employer?invite_accepted=1#team", status_code=303)


@app.post("/employer/team/{membership_id}/remove")
def team_remove(membership_id: int, request: Request, db: Session = Depends(db_session)):
    _, account, _ = require_company_user(request, db, owner_only=True)
    membership = db.get(CompanyMember, membership_id)
    if not membership or membership.account_id != account.id:
        raise HTTPException(404)
    db.delete(membership)
    db.commit()
    return RedirectResponse("/employer?member_removed=1#team", status_code=303)


@app.post("/employer/team/{membership_id}/role")
def team_role_change(membership_id: int, request: Request, role: str = Form(...),
                     db: Session = Depends(db_session)):
    _, account, _ = require_company_user(request, db, owner_only=True)
    membership = db.get(CompanyMember, membership_id)
    if not membership or membership.account_id != account.id:
        raise HTTPException(404)
    if role not in ("recruiter", "viewer"):
        raise HTTPException(400)
    membership.role = role
    db.commit()
    return RedirectResponse("/employer#team", status_code=303)


@app.post("/employer/invite/{invite_id}/revoke")
def team_invite_revoke(invite_id: int, request: Request, db: Session = Depends(db_session)):
    _, account, _ = require_company_user(request, db, owner_only=True)
    invite = db.get(CompanyInvite, invite_id)
    if not invite or invite.account_id != account.id:
        raise HTTPException(404)
    invite.status = "revoked"
    db.commit()
    return RedirectResponse("/employer#team", status_code=303)


def employer_job_or_404(job_id: int, user: User, db: Session) -> Job:
    account, _ = company_context(user, db)
    job = db.get(Job, job_id)
    if not job or (job.owner_id != account.id and user.role != "admin"):
        raise HTTPException(404)
    return job


@app.get("/employer/job/{job_id}/edit", response_class=HTMLResponse)
def employer_job_edit(job_id: int, request: Request, db: Session = Depends(db_session)):
    user, _, _ = require_company_user(request, db, write=True)
    job = employer_job_or_404(job_id, user, db)
    return render(request, db, "admin_edit.html", job=job, categories=CATEGORIES,
                  formats=FORMATS, employer_mode=True)


@app.post("/employer/job/{job_id}/edit")
def employer_job_save(job_id: int, request: Request, title: str = Form(...),
                      category: str = Form(""), location: str = Form(""),
                      fmt: str = Form("удалёнка"), salary: str = Form(""),
                      tags: str = Form(""), languages: str = Form(""),
                      description: str = Form(""), db: Session = Depends(db_session)):
    user, _, _ = require_company_user(request, db, write=True)
    job = employer_job_or_404(job_id, user, db)
    if not title.strip() or not description.strip() or not any(char.isdigit() for char in salary):
        return RedirectResponse(f"/employer/job/{job_id}/edit?error=1", status_code=303)
    job.title = title.strip()[:240]
    job.category = category if category in CATEGORIES else guess_category(title, tags)
    job.location = location.strip()[:180]
    job.fmt = fmt if fmt in FORMATS else "удалёнка"
    job.salary = salary.strip()[:180]
    language_label = next((label for code, label, _ in JOB_LANGUAGES if code == languages), "")
    job.tags = ", ".join(filter(None, (tags.strip()[:1000], language_label)))
    job.description = description.strip()
    if job.status == "approved":
        job.status = "pending"
    db.commit()
    return RedirectResponse("/employer?job_saved=1", status_code=303)


@app.post("/employer/job/{job_id}/archive")
def employer_job_archive(job_id: int, request: Request, db: Session = Depends(db_session)):
    user, _, _ = require_company_user(request, db, write=True)
    job = employer_job_or_404(job_id, user, db)
    job.status = "archived"
    job.closed_at = datetime.utcnow().date().isoformat()
    db.commit()
    return RedirectResponse("/employer?job_archived=1", status_code=303)


@app.get("/post-job", response_class=HTMLResponse)
def post_job_page(request: Request, db: Session = Depends(db_session)):
    user = get_user(request, db)
    can_post = bool(user and user.role in ("employer", "admin")
                    and company_context(user, db)[1] != "viewer")
    live_jobs = db.query(Job).filter(Job.status == "approved").count()
    return render(request, db, "post_job.html", categories=CATEGORIES, formats=FORMATS,
                  posted=False, need_login=not user or user.role == "talent",
                  can_post=can_post, live_jobs=f"{live_jobs:,}".replace(",", " "))


@app.post("/post-job")
def post_job(request: Request, title: str = Form(...), category: str = Form(""),
             location: str = Form(""), fmt: str = Form("удалёнка"),
             salary_from: str = Form(""), salary_to: str = Form(""),
             currency: str = Form("EUR net"), tags: str = Form(""), languages: str = Form(""),
             description: str = Form(""), db: Session = Depends(db_session)):
    user = get_user(request, db)
    if not user or user.role == "talent":
        return login_redirect("/post-job")
    _, account, _ = require_company_user(request, db, write=True)

    def err(msg):
        return render(request, db, "post_job.html", categories=CATEGORIES, formats=FORMATS,
                      posted=False, need_login=False, can_post=True, error=msg)

    # правила заведения: без корректной зарплатной вилки не публикуем
    try:
        s_from, s_to = int(salary_from), int(salary_to)
    except (TypeError, ValueError):
        return err("Укажите зарплатную вилку числами — без вилки не публикуем.")
    if s_from <= 0 or s_to <= 0:
        return err("Зарплата должна быть больше нуля.")
    if s_from > s_to:
        return err("«Зарплата от» не может быть больше «до».")
    if not title.strip():
        return err("Укажите название вакансии.")
    if languages not in {code for code, _, _ in JOB_LANGUAGES}:
        return err("Укажите язык работы для вакансии.")

    unit = currency.split()[1] if " " in currency else ""
    if currency.startswith("USDT"):
        salary = f"{s_from}–{s_to} USDT"
    elif currency.startswith("USD"):
        salary = f"${s_from}–{s_to} {unit}".strip()
    else:
        salary = f"€{s_from}–{s_to} {unit}".strip()
    language_label = next((label for code, label, _ in JOB_LANGUAGES if code == languages), "")
    normalized_tags = ", ".join(filter(None, (tags.strip(), language_label)))
    db.add(Job(title=title.strip(),
               company_name=account.company_name or account.name or account.email,
               category=category or guess_category(title, tags),
               location=location.strip(), fmt=fmt, salary=salary,
               tags=normalized_tags, description=description.strip(),
               owner_id=account.id, status="pending"))
    db.commit()
    return render(request, db, "post_job.html", categories=CATEGORIES, formats=FORMATS,
                  posted=True, need_login=False, can_post=True)


# ---------- admin ----------

def need_admin(request: Request, db: Session) -> User:
    user = get_user(request, db)
    if not user or user.role != "admin":
        raise HTTPException(403, "Только для админов")
    return user


@app.post("/admin/crawl")
def admin_crawl(request: Request, db: Session = Depends(db_session)):
    need_admin(request, db)
    try:
        from server import crawler
        res = crawler.run(db, Job, guess_category,
                      upsert_companies=lambda rows: upsert_company_profiles(db, rows))
        msg = f"Собрано {res['collected']}, добавлено {res['added']}, обновлено {res['updated']}"
    except Exception as e:
        msg = f"Ошибка краулера: {str(e)[:150]}"
        try:
            crawler.save_status({"last_run": datetime.utcnow().isoformat() + "Z",
                                 "ok": False, "error": str(e)[:500]})
        except Exception:
            pass
    return RedirectResponse(f"/admin?tab=sources&crawl={msg}", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request, tab: str = "dash", db: Session = Depends(db_session)):
    need_admin(request, db)
    ctx = {"tab": tab}
    ctx["stats"] = {
        "jobs_total": db.query(Job).count(),
        "jobs_pending": db.query(Job).filter(Job.status == "pending").count(),
        "jobs_approved": db.query(Job).filter(Job.status == "approved").count(),
        "users": db.query(User).count(),
        "employers": db.query(User).filter(User.role == "employer").count(),
        "talents": db.query(User).filter(User.role == "talent").count(),
        "apps": db.query(Application).count(),
        "views": db.query(func.sum(Job.views)).scalar() or 0,
        "resumes_live": db.query(Resume).filter(Resume.status == "approved", Resume.published == True).count(),  # noqa: E712
        "resumes_pending": db.query(Resume).filter(Resume.status == "pending").count(),
        "resume_unlocks": db.query(ResumeUnlock).count(),
    }
    if tab == "jobs":
        q = (request.query_params.get("q") or "").strip().lower()
        st = request.query_params.get("st") or ""
        jobs = db.query(Job).order_by((Job.status == "pending").desc(),
                                      Job.created_at.desc()).all()
        if st:
            jobs = [j for j in jobs if j.status == st]
        if q:
            jobs = [j for j in jobs if q in f"{j.title} {j.company_name} {j.source}".lower()]
        ctx["jobs"] = jobs[:200]
        ctx["q"], ctx["st"] = q, st
    elif tab == "users":
        ctx["users"] = db.query(User).order_by(User.created_at.desc()).all()
    elif tab == "apps":
        ctx["apps"] = db.query(Application).order_by(Application.created_at.desc()).all()
    elif tab == "resumes":
        ctx["resumes"] = db.query(Resume).order_by(
            (Resume.status == "pending").desc(), Resume.updated_at.desc()).all()
    elif tab == "sources":
        from server import crawler
        from collections import Counter
        counts = Counter(j.source or "внутренние/ручные"
                         for j in db.query(Job).filter(Job.status == "approved").all())
        ctx["sources"] = crawler.SOURCE_REGISTRY
        ctx["source_counts"] = dict(counts)
        ctx["resume_sources"] = crawler.RESUME_SOURCE_REGISTRY
        ctx["source_summary"] = {
            "jobs_connected": sum(s["status"] in ("работает", "подключён") for s in crawler.SOURCE_REGISTRY),
            "jobs_total": len(crawler.SOURCE_REGISTRY),
            "resume_connected": sum(s["status"] in ("работает", "подключён") for s in crawler.RESUME_SOURCE_REGISTRY),
            "talent_profiles": db.query(User).filter(User.role == "talent").count(),
        }
        status_path = os.path.join(ROOT, "data", "crawler-status.json")
        try:
            with open(status_path, encoding="utf-8") as handle:
                ctx["crawl_status"] = json.load(handle)
        except (OSError, ValueError):
            ctx["crawl_status"] = {}
        ctx["source_health"] = {row.get("key"): row for row in ctx["crawl_status"].get("sources", [])}
    elif tab == "analytics":
        since = datetime.utcnow() - timedelta(days=14)
        events = db.query(AnalyticsEvent).filter(AnalyticsEvent.created_at >= since).all()
        event_counts = {}
        daily = {}
        for event in events:
            event_counts[event.name] = event_counts.get(event.name, 0) + 1
            day = event.created_at.date().isoformat()
            daily.setdefault(day, {})[event.name] = daily.setdefault(day, {}).get(event.name, 0) + 1
        applications = db.query(Application).count()
        interviews = db.query(Application).filter(Application.status == "invited").count()
        offers = db.query(Application).filter(Application.status == "offer").count()
        hired = db.query(Application).filter(Application.status == "hired").count()
        job_views = event_counts.get("job_view", 0)
        ctx["funnel"] = {
            "views": job_views, "applications": applications, "interviews": interviews,
            "offers": offers, "hired": hired,
            "apply_rate": round(applications * 100 / job_views, 1) if job_views else 0,
            "hire_rate": round(hired * 100 / applications, 1) if applications else 0,
            "resume_unlocks": db.query(ResumeUnlock).count(),
        }
        ctx["daily_events"] = [{"date": (datetime.utcnow().date() - timedelta(days=offset)).isoformat(),
                                **daily.get((datetime.utcnow().date() - timedelta(days=offset)).isoformat(), {})}
                               for offset in range(13, -1, -1)]
        approved = db.query(Job).filter(Job.status == "approved")
        thin = approved.filter(func.length(func.trim(Job.description)) < 300).count()
        missing_location = approved.filter(func.length(func.trim(Job.location)) == 0).count()
        missing_company = approved.filter(func.length(func.trim(Job.company_name)) == 0).count()
        archived = db.query(Job).filter(Job.status == "archived").count()
        indexable_resumes = db.query(Resume).filter(Resume.status == "approved", Resume.published == True).count()  # noqa: E712
        ctx["seo"] = {
            "indexable_jobs": approved.count(), "thin_jobs": thin,
            "missing_location": missing_location, "missing_company": missing_company,
            "archived": archived, "indexable_resumes": indexable_resumes,
            "sitemap_urls": approved.count() + indexable_resumes + db.query(Event).filter(Event.active == True).count() + 6,  # noqa: E712
            "indexnow": bool(os.environ.get("INDEXNOW_KEY")),
            "google_indexing": bool(os.environ.get("GOOGLE_INDEXING_SERVICE_ACCOUNT_JSON")),
        }
        status_path = os.path.join(ROOT, "data", "crawler-status.json")
        try:
            with open(status_path, encoding="utf-8") as handle:
                ctx["crawl_status"] = json.load(handle)
        except (OSError, ValueError):
            ctx["crawl_status"] = {}
    elif tab == "events":
        ctx["events"] = db.query(Event).order_by(Event.date_from).all()
    elif tab == "orders":
        ctx["orders"] = db.query(Order).order_by(Order.created_at.desc()).all()
        ctx["orders_pending"] = db.query(Order).filter(Order.status == "pending").count()
        ctx["revenue"] = db.query(func.sum(Order.amount)).filter(Order.status == "paid").scalar() or 0
    else:
        ctx["pending"] = db.query(Job).filter(Job.status == "pending") \
            .order_by(Job.created_at.desc()).limit(10).all()
        ctx["orders_pending"] = db.query(Order).filter(Order.status == "pending").count()
    return render(request, db, "admin.html", **ctx)


@app.post("/admin/resume/{resume_id}/{action}")
def admin_resume_action(resume_id: int, action: str, request: Request,
                        moderation_note: str = Form(""), db: Session = Depends(db_session)):
    need_admin(request, db)
    row = db.get(Resume, resume_id)
    if not row:
        raise HTTPException(404)
    if action == "approve":
        row.status = "approved"
        row.published = True
        row.moderation_note = ""
        add_notification(db, row.user_id, "resume", "CV опубликован",
                         "Ваш анонимный профиль появился в базе работодателей.",
                         f"/resume/{row.id}")
    elif action == "reject":
        row.status = "rejected"
        row.published = False
        row.moderation_note = moderation_note.strip() or "Уберите данные, раскрывающие личность, и уточните опыт."
        add_notification(db, row.user_id, "resume", "CV нужно доработать",
                         row.moderation_note, "/profile#cv")
    elif action == "pause":
        row.status = "paused"
        row.published = False
        row.moderation_note = moderation_note.strip()
        add_notification(db, row.user_id, "resume", "Публикация CV приостановлена",
                         row.moderation_note, "/profile#cv")
    else:
        raise HTTPException(400)
    row.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse("/admin?tab=resumes", status_code=303)


# редактирование вакансии
@app.get("/admin/job/{job_id}/edit", response_class=HTMLResponse)
def admin_job_edit(job_id: int, request: Request, db: Session = Depends(db_session)):
    need_admin(request, db)
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404)
    return render(request, db, "admin_edit.html", job=job, categories=CATEGORIES, formats=FORMATS)


@app.post("/admin/job/{job_id}/edit")
def admin_job_save(job_id: int, request: Request, title: str = Form(...),
                   company_name: str = Form(""), category: str = Form(""),
                   location: str = Form(""), fmt: str = Form("удалёнка"),
                   salary: str = Form(""), tags: str = Form(""), languages: str = Form(""),
                   description: str = Form(""), db: Session = Depends(db_session)):
    need_admin(request, db)
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404)
    job.title, job.company_name = title.strip(), company_name.strip()
    job.category, job.location, job.fmt = category, location.strip(), fmt
    job.salary = salary.strip() or "по запросу"
    language_label = next((label for code, label, _ in JOB_LANGUAGES if code == languages), "")
    job.tags = ", ".join(filter(None, (tags.strip(), language_label)))
    job.description = description.strip()
    db.commit()
    return RedirectResponse("/admin?tab=jobs", status_code=303)


# события — CRUD
@app.post("/admin/event/add")
def admin_event_add(request: Request, title: str = Form(...), city: str = Form(""),
                    date_from: str = Form(""), date_to: str = Form(""), url: str = Form(""),
                    image: str = Form(""), description: str = Form(""),
                    attendees: str = Form(""), category: str = Form(""),
                    promo: str = Form(""), db: Session = Depends(db_session)):
    need_admin(request, db)
    if title.strip() and date_from.strip():
        db.add(Event(title=title.strip(), city=city.strip(), date_from=date_from.strip(),
                     date_to=date_to.strip(), url=url.strip(), image=image.strip(),
                     description=description.strip(), attendees=attendees.strip(),
                     category=category.strip(), promo=promo.strip()))
        db.commit()
    return RedirectResponse("/admin?tab=events", status_code=303)


@app.post("/admin/event/{ev_id}/{action}")
def admin_event_action(ev_id: int, action: str, request: Request, db: Session = Depends(db_session)):
    need_admin(request, db)
    e = db.get(Event, ev_id)
    if e:
        if action == "toggle":
            e.active = not e.active
        elif action == "delete":
            db.delete(e)
        db.commit()
    return RedirectResponse("/admin?tab=events", status_code=303)


# заказы — админ отмечает оплату
@app.post("/admin/order/{order_id}/{action}")
def admin_order_action(order_id: int, action: str, request: Request, db: Session = Depends(db_session)):
    need_admin(request, db)
    o = db.get(Order, order_id)
    if o:
        if action == "paid":
            already_paid = o.status == "paid"
            o.status = "paid"
            # применяем плюшку: featured-план поднимает вакансию
            if o.plan == "featured" and o.job_id:
                job = db.get(Job, o.job_id)
                if job:
                    job.featured = True
                    job.status = "approved"
            if not already_paid and o.user and o.plan in PLAN_JOB_CREDITS:
                o.user.job_credits = (o.user.job_credits or 0) + PLAN_JOB_CREDITS[o.plan]
            if not already_paid and o.user and o.plan in PLAN_ACCESS_DAYS:
                o.user.job_access_until = (
                    datetime.utcnow() + timedelta(days=PLAN_ACCESS_DAYS[o.plan])).isoformat()
            if not already_paid and o.user and o.plan == "cv1":
                o.user.cv_credits = (o.user.cv_credits or 0) + 1
                db.add(ResumeCreditLedger(employer_id=o.user.id, order_id=o.id, delta=1,
                                          balance_after=o.user.cv_credits, action="purchase"))
            elif not already_paid and o.user and o.plan == "cv10":
                o.user.cv_credits = (o.user.cv_credits or 0) + 10
                db.add(ResumeCreditLedger(employer_id=o.user.id, order_id=o.id, delta=10,
                                          balance_after=o.user.cv_credits, action="purchase"))
            elif not already_paid and o.user and o.plan == "cv40":
                o.user.cv_credits = (o.user.cv_credits or 0) + 40
                db.add(ResumeCreditLedger(employer_id=o.user.id, order_id=o.id, delta=40,
                                          balance_after=o.user.cv_credits, action="purchase"))
            elif not already_paid and o.user and o.plan == "cvunlim":
                o.user.cv_access_until = (datetime.utcnow() + timedelta(days=30)).isoformat()
                db.add(ResumeCreditLedger(employer_id=o.user.id, order_id=o.id, delta=0,
                                          balance_after=o.user.cv_credits or 0, action="unlimited"))
        elif action == "cancel":
            o.status = "cancelled"
        db.commit()
    return RedirectResponse("/admin?tab=orders", status_code=303)


@app.post("/admin/job/{job_id}/{action}")
def admin_job(job_id: int, action: str, request: Request, db: Session = Depends(db_session)):
    need_admin(request, db)
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404)
    if action == "approve":
        job.status = "approved"
    elif action == "reject":
        job.status = "rejected"
    elif action == "archive":
        job.status = "archived"
    elif action == "feature":
        job.featured = not job.featured
    elif action == "delete":
        db.delete(job)
    db.commit()
    ref = request.headers.get("referer") or ""
    dest = "/admin?tab=jobs"
    if "tab=" in ref and ref.startswith(("http://165", "http://127", "http://localhost", "/")):
        dest = ref
    return RedirectResponse(dest, status_code=303)


@app.post("/admin/user/{user_id}/{action}")
def admin_user(user_id: int, action: str, request: Request, db: Session = Depends(db_session)):
    me = need_admin(request, db)
    u = db.get(User, user_id)
    if not u or u.id == me.id:
        return RedirectResponse("/admin?tab=users", status_code=303)
    if action == "delete":
        db.query(Application).filter_by(user_id=u.id).delete()
        db.query(Job).filter_by(owner_id=u.id).update({"owner_id": None})
        owned_resume = db.query(Resume).filter_by(user_id=u.id).first()
        if owned_resume:
            db.query(ResumeUnlock).filter_by(resume_id=owned_resume.id).delete()
            db.query(ResumeCreditLedger).filter_by(resume_id=owned_resume.id).update(
                {"resume_id": None}, synchronize_session=False)
            db.delete(owned_resume)
        db.query(ResumeUnlock).filter_by(employer_id=u.id).delete()
        db.query(ResumeCreditLedger).filter_by(employer_id=u.id).delete()
        db.delete(u)
    elif action in ("talent", "employer", "admin"):
        u.role = action
    db.commit()
    return RedirectResponse("/admin?tab=users", status_code=303)



# ---------- быстрый вход с готовым CV (PDF) ----------

CV_LANG_MAP = {
    "английск": "Английский", "english": "Английский",
    "немецк": "Немецкий", "german": "Немецкий", "deutsch": "Немецкий",
    "французск": "Французский", "french": "Французский",
    "испанск": "Испанский", "spanish": "Испанский",
    "итальянск": "Итальянский", "italian": "Итальянский",
    "португальск": "Португальский", "portuguese": "Португальский",
    "польск": "Польский", "polish": "Польский",
    "финск": "Финский", "finnish": "Финский",
    "шведск": "Шведский", "swedish": "Шведский",
    "японск": "Японский", "japanese": "Японский",
    "турецк": "Турецкий", "turkish": "Турецкий",
    "греческ": "Греческий", "greek": "Греческий",
    "украинск": "Украинский", "ukrainian": "Украинский",
    "русск": "Русский", "russian": "Русский",
}
CV_SKILL_WORDS = [
    "Excel", "SQL", "Python", "Jira", "Tableau", "Power BI", "Google Analytics",
    "CRM", "Salesforce", "HubSpot", "Zendesk", "Intercom", "Optimove", "Customer.io",
    "KYC", "AML", "Compliance", "Chargeback", "Antifraud", "Fraud",
    "Retention", "Reactivation", "VIP", "Affiliate", "Media Buying", "PPC", "SEO", "ASO",
    "Unity", "JavaScript", "TypeScript", "React", "Node.js", "PHP", "Java", "C#", "Go",
    "QA", "Selenium", "Playwright", "Postman", "API", "Figma", "Photoshop",
]
CV_LOCATION_WORDS = ["Мальта", "Malta", "Кипр", "Cyprus", "Лимассол", "Limassol", "Варшава",
                     "Warsaw", "Тбилиси", "Tbilisi", "Киев", "Kyiv", "Минск", "Вильнюс",
                     "Рига", "Барселона", "Лиссабон", "Прага", "Prague", "Белград", "Belgrade",
                     "Ереван", "Yerevan", "Батуми", "Batumi", "Remote", "Удалённо", "Удаленно"]


def parse_cv_pdf(payload: bytes) -> dict:
    """Черновой разбор PDF-резюме: имя, роль, языки, скиллы, контакты.

    Эвристики сознательно осторожные: лучше пустое поле, чем мусор —
    кандидат проверяет черновик перед публикацией.
    """
    import re as _re
    out = {"name": "", "title": "", "languages": "", "skills": "", "about": "",
           "location": "", "experience_years": 0, "contact_telegram": "", "email": ""}
    try:
        from io import BytesIO
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(payload))
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:5])
    except Exception:
        return out
    text = text.strip()
    if not text:
        return out
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # имя: первая короткая строка из 2–3 слов с заглавных, без цифр и @
    for ln in lines[:6]:
        words = ln.split()
        if (1 < len(words) <= 3 and len(ln) < 60 and not any(c.isdigit() for c in ln)
                and "@" not in ln and all(w[:1].isupper() for w in words)):
            out["name"] = ln
            break
    # роль: строка с ключевым словом профессии из картотеки либо вторая строка
    role_words = ("manager", "менеджер", "developer", "разработчик", "engineer", "инженер",
                  "analyst", "аналитик", "specialist", "специалист", "designer", "дизайнер",
                  "lead", "head", "officer", "агент", "agent", "support", "recruiter", "qa")
    for ln in lines[:12]:
        low = ln.lower()
        if ln != out["name"] and len(ln) < 80 and any(w in low for w in role_words):
            out["title"] = ln
            break
    low_text = text.lower()
    langs = []
    for key, label in CV_LANG_MAP.items():
        if key in low_text and label not in langs:
            langs.append(label)
    out["languages"] = ", ".join(langs[:6])
    skills = [w for w in CV_SKILL_WORDS if _re.search(r"(?i)(?<![a-zа-я])" + _re.escape(w.lower()) + r"(?![a-zа-я])", low_text)]
    out["skills"] = ", ".join(dict.fromkeys(skills))[:400]
    for loc in CV_LOCATION_WORDS:
        if loc.lower() in low_text:
            out["location"] = {"malta": "Мальта", "cyprus": "Кипр", "limassol": "Лимассол",
                               "warsaw": "Варшава", "tbilisi": "Тбилиси", "kyiv": "Киев",
                               "prague": "Прага", "belgrade": "Белград", "yerevan": "Ереван",
                               "batumi": "Батуми", "remote": "Удалённо", "удаленно": "Удалённо"}.get(loc.lower(), loc)
            break
    m = _re.search(r"(?i)(\d{1,2})\+?\s*(?:лет|года?|years?)", text)
    if m:
        out["experience_years"] = min(int(m.group(1)), 40)
    m = _re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    if m:
        out["email"] = m.group(0).lower()
    m = (_re.search(r"(?i)(?:t\.me/|телеграм[:\s]*@?|telegram[:\s]*@?)([A-Za-z0-9_]{5,32})", text)
         or _re.search(r"(?<![\w.])@([A-Za-z0-9_]{5,32})(?!\.[a-z])", text))
    if m:
        out["contact_telegram"] = "@" + m.group(1)
    out["about"] = " ".join(text.split())[:600]
    return out


@app.post("/resumes/quick")
async def resumes_quick(request: Request, email: str = Form(...),
                        cv: UploadFile = File(...), consent: str = Form(""),
                        db: Session = Depends(db_session)):
    """Быстрый вход: готовый PDF + почта → черновик профиля с автозаполнением."""
    email = email.strip().lower()
    if not consent:
        return RedirectResponse("/resumes?quick_error=consent", status_code=303)
    if "@" not in email or len(email) > 200:
        return RedirectResponse("/resumes?quick_error=email", status_code=303)
    payload = await cv.read()
    if not payload.startswith(b"%PDF") or len(payload) > 5 * 1024 * 1024:
        return RedirectResponse("/resumes?quick_error=file", status_code=303)
    existing = db.query(User).filter(func.lower(User.email) == email).first()
    if existing:
        return RedirectResponse(f"/login?next=%2Fprofile%23cv&email={urllib.parse.quote(email)}&e=quick_exists",
                                status_code=303)
    parsed = parse_cv_pdf(payload)
    user = User(email=email, password_hash=hash_pw(secrets.token_urlsafe(18)),
                name=parsed["name"], role="talent", coins=SIGNUP_COIN_BONUS)
    db.add(user)
    db.flush()
    os.makedirs(CV_UPLOAD_DIR, exist_ok=True)
    stored_path = os.path.join(CV_UPLOAD_DIR, f"{user.id}-{secrets.token_hex(12)}.pdf")
    with open(stored_path, "wb") as handle:
        handle.write(payload)
    safe_name = os.path.basename(cv.filename or "resume.pdf")[:240]
    row = Resume(user_id=user.id, title=parsed["title"], location=parsed["location"],
                 experience_years=parsed["experience_years"], skills=parsed["skills"],
                 about=parsed["about"], languages=parsed["languages"],
                 contact_email=parsed["email"] or email,
                 contact_telegram=parsed["contact_telegram"],
                 cv_file_name=safe_name, cv_file_path=stored_path,
                 published=False, status="draft")
    db.add(row)
    db.commit()
    return set_session(RedirectResponse("/profile?quick=1#cv", status_code=303), user)


# ---------- sitemap (динамический, включает живые вакансии) ----------

ARTICLE_FILES = {
    "salaries-igaming-2026": "post-salaries-igaming-2026.html",
    "relocation-malta": "post-relocation-malta.html",
    "vip-manager": "post-vip-manager.html",
    "limassol-vs-warsaw": "post-limassol-vs-warsaw.html",
    "compliance-career": "post-compliance-career.html",
    "crypto-salary": "post-crypto-salary.html",
    "igaming-bez-opyta": "post-igaming-bez-opyta.html",
}


@app.get("/blog")
def blog_short():
    return RedirectResponse("/blog.html", status_code=301)


@app.get("/blog/{slug}")
def article_page(slug: str):
    filename = ARTICLE_FILES.get(slug)
    if not filename:
        raise HTTPException(404)
    return FileResponse(os.path.join(ROOT, filename), media_type="text/html")


@app.get("/post-{slug}.html")
def legacy_article(slug: str):
    canonical_slug = next((key for key, filename in ARTICLE_FILES.items()
                           if filename == f"post-{slug}.html"), None)
    if not canonical_slug:
        raise HTTPException(404)
    return RedirectResponse(f"/blog/{canonical_slug}", status_code=301)


@app.get("/indexnow-key.txt")
def indexnow_key():
    from fastapi.responses import PlainTextResponse
    key = os.environ.get("INDEXNOW_KEY", "").strip()
    if not key:
        raise HTTPException(404)
    return PlainTextResponse(key)


# ---------- картотека профессий iGaming ----------

PROFESSIONS_PATH = os.path.join(ROOT, "data", "professions.json")
_PROFESSIONS_CACHE: dict = {"mtime": 0.0, "data": None}

SENIORITY = (("junior", "Junior"), ("middle", "Middle"), ("senior", "Senior"), ("lead", "Head / Lead"))


def professions_data() -> dict:
    """Читаем картотеку с диска, перечитывая только при изменении файла."""
    try:
        mtime = os.path.getmtime(PROFESSIONS_PATH)
    except OSError:
        return {"regions": {}, "roles": []}
    if _PROFESSIONS_CACHE["data"] is None or _PROFESSIONS_CACHE["mtime"] != mtime:
        with open(PROFESSIONS_PATH, encoding="utf-8") as fh:
            _PROFESSIONS_CACHE["data"] = json.load(fh)
        _PROFESSIONS_CACHE["mtime"] = mtime
    return _PROFESSIONS_CACHE["data"]


def profession_by_slug(slug: str) -> Optional[dict]:
    return next((r for r in professions_data()["roles"] if r["slug"] == slug), None)


def role_keywords(role: dict) -> list[str]:
    """Слова для сопоставления профессии с живыми вакансиями.

    Курируемый список `match` в data/professions.json важнее сгенерированного:
    названия вакансий в индустрии разнородные («VIP Supervisor», «VIP Team Manager»),
    и поиск по полному названию профессии находит слишком мало.
    """
    words = [*role.get("match", []), role["title_en"], *role.get("aliases", [])]
    out: list[str] = []
    for word in words:
        word = re.sub(r"\s*\(.*?\)", "", word or "").lower().strip()
        if word and word not in out:
            out.append(word)
    return out


def role_matched_jobs(db: Session, role: dict, limit: int = 6):
    """Живые вакансии, чьё название похоже на эту профессию."""
    needles = role_keywords(role)[:8]
    query = db.query(Job).filter(Job.status == "approved")
    query = query.filter(or_(*[Job.title.ilike(f"%{n}%") for n in needles]))
    return query.order_by(Job.featured.desc(), Job.id.desc()).limit(limit).all()


def role_jobs_count(db: Session, role: dict) -> int:
    needles = role_keywords(role)[:8]
    return (db.query(func.count(Job.id)).filter(Job.status == "approved")
            .filter(or_(*[Job.title.ilike(f"%{n}%") for n in needles])).scalar() or 0)


def role_salary_headline(role: dict) -> str:
    """Вилка middle по Мальте и Кипру — она идёт в карточку и в описание."""
    band = role["salary"]["mt_cy"]["middle"]
    return f"€{band[0]:,}–{band[1]:,}".replace(",", " ")


@app.get("/professions", response_class=HTMLResponse)
def professions_index(request: Request, db: Session = Depends(db_session)):
    data = professions_data()
    families: dict[str, list] = {}
    for role in data["roles"]:
        families.setdefault(role["family"], []).append({
            "slug": role["slug"], "title": role["title"], "title_en": role["title_en"],
            "lead": role["lead"], "salary": role_salary_headline(role),
            "jobs": role_jobs_count(db, role),
        })
    total_jobs = db.query(func.count(Job.id)).filter(Job.status == "approved").scalar() or 0
    return render(request, db, "professions.html", families=families,
                  roles_total=len(data["roles"]), total_jobs=total_jobs,
                  regions=data["regions"], seniority=SENIORITY)


@app.get("/profession/{slug}", response_class=HTMLResponse)
def profession_page(slug: str, request: Request, db: Session = Depends(db_session)):
    role = profession_by_slug(slug)
    if not role:
        raise HTTPException(404)
    data = professions_data()
    related = [r for r in (profession_by_slug(s) for s in role.get("related", [])) if r]
    same_family = [r for r in data["roles"]
                   if r["family"] == role["family"] and r["slug"] != role["slug"]][:6]
    jobs = role_matched_jobs(db, role)
    return render(request, db, "profession.html", role=role, regions=data["regions"],
                  seniority=SENIORITY, related=related, same_family=same_family,
                  jobs=jobs, jobs_count=role_jobs_count(db, role),
                  salary_headline=role_salary_headline(role))


COUNTRY_ALIASES = {
    "malta": "Мальта", "мальта": "Мальта", "sliema": "Мальта", "st julian": "Мальта",
    "cyprus": "Кипр", "кипр": "Кипр", "limassol": "Кипр", "nicosia": "Кипр",
    "poland": "Польша", "польша": "Польша", "warsaw": "Польша", "krakow": "Польша", "poznan": "Польша",
    "ukraine": "Украина", "украина": "Украина", "kyiv": "Украина", "kiev": "Украина", "київ": "Украина",
    "united kingdom": "Великобритания", "uk": "Великобритания", "london": "Великобритания",
    "gibraltar": "Гибралтар", "romania": "Румыния", "bucharest": "Румыния",
    "bulgaria": "Болгария", "sofia": "Болгария", "greece": "Греция", "athens": "Греция",
    "spain": "Испания", "madrid": "Испания", "barcelona": "Испания",
    "portugal": "Португалия", "lisbon": "Португалия", "germany": "Германия", "berlin": "Германия",
    "brazil": "Бразилия", "sao paulo": "Бразилия", "são paulo": "Бразилия",
    "united states": "США", "usa": "США", "new jersey": "США", "las vegas": "США",
    "canada": "Канада", "toronto": "Канада", "georgia": "Грузия", "tbilisi": "Грузия",
    "armenia": "Армения", "yerevan": "Армения", "serbia": "Сербия", "belgrade": "Сербия",
    "philippines": "Филиппины", "manila": "Филиппины", "india": "Индия",
    "south africa": "ЮАР", "uae": "ОАЭ", "dubai": "ОАЭ", "sweden": "Швеция", "stockholm": "Швеция",
    "latvia": "Латвия", "riga": "Латвия", "estonia": "Эстония", "lithuania": "Литва",
    "netherlands": "Нидерланды", "amsterdam": "Нидерланды", "ireland": "Ирландия", "dublin": "Ирландия",
    "italy": "Италия", "milan": "Италия", "mexico": "Мексика", "colombia": "Колумбия",
    "peru": "Перу", "chile": "Чили", "argentina": "Аргентина", "turkey": "Турция",
    "australia": "Австралия", "china": "Китай", "japan": "Япония", "kazakhstan": "Казахстан",
}


def country_of(location: str) -> str:
    """Свести свободный текст локации к стране. Удалёнку считаем отдельной «страной»."""
    low = (location or "").lower()
    if not low.strip():
        return "Не указана"
    if "remote" in low or "удал" in low or "віддал" in low:
        return "Удалёнка"
    for alias, name in COUNTRY_ALIASES.items():
        if alias in low:
            return name
    tail = low.split(",")[-1].strip()
    # «2 Locations», «3 offices» — у источника вместо города счётчик,
    # страну из этого не вывести, а в статистике такое выглядит как страна
    if not tail or any(ch.isdigit() for ch in tail):
        return "Не указана"
    return tail.title()[:24]


RU_MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
             "августа", "сентября", "октября", "ноября", "декабря")


def human_date(value: date) -> str:
    """«19 августа 2026» — для текста страницы; в разметку идёт ISO."""
    return f"{value.day} {RU_MONTHS[value.month - 1]} {value.year}"


def market_stats_data(db: Session) -> dict:
    """Живые цифры рынка труда iGaming.

    Считается на лету по всем одобренным вакансиям: это наш собственный
    показатель, на который ссылаются страница /market, картотека профессий,
    главная и /llms.txt — цифра должна быть везде одна и та же.
    """
    jobs = db.query(Job).filter(Job.status == "approved").all()
    week_ago = datetime.utcnow() - timedelta(days=7)
    directions: dict[str, int] = {}
    countries: dict[str, int] = {}
    languages: dict[str, int] = {}
    formats: dict[str, int] = {}
    with_salary = 0
    fresh = 0
    for job in jobs:
        directions[job.category or "Другое"] = directions.get(job.category or "Другое", 0) + 1
        country = country_of(job.location)
        countries[country] = countries.get(country, 0) + 1
        formats[job.fmt or "не указан"] = formats.get(job.fmt or "не указан", 0) + 1
        for _, label in job.language_list:
            languages[label] = languages.get(label, 0) + 1
        if job.has_salary:
            with_salary += 1
        # «новые за неделю» считаем по дате публикации у источника: у импортированных
        # вакансий created_at — это дата нашего импорта, а не появления вакансии
        posted = job.posted_at if re.match(r"^\d{4}-\d{2}-\d{2}$", job.posted_at or "") else ""
        published = datetime.fromisoformat(posted) if posted else job.created_at
        if published and published >= week_ago:
            fresh += 1
    companies = len({job.company_slug for job in jobs})

    def top(source: dict, limit: int):
        return [{"name": name, "jobs": count}
                for name, count in sorted(source.items(), key=lambda kv: -kv[1])[:limit]]

    professions = []
    for role in professions_data()["roles"]:
        count = role_jobs_count(db, role)
        if count:
            professions.append({"slug": role["slug"], "title": role["title"],
                                "family": role["family"], "jobs": count,
                                "salary": role_salary_headline(role)})
    professions.sort(key=lambda r: -r["jobs"])

    return {
        "live_jobs": len(jobs),
        "new_this_week": fresh,
        "companies": companies,
        "with_salary": with_salary,
        "with_salary_pct": round(with_salary / len(jobs) * 100) if jobs else 0,
        "directions": top(directions, 10),
        "countries": top(countries, 12),
        "languages": top(languages, 8),
        "formats": top(formats, 4),
        "professions": professions[:12],
        "updated": datetime.utcnow().isoformat(timespec="minutes") + "Z",
    }


@app.get("/api/market-stats")
def api_market_stats(db: Session = Depends(db_session)):
    return JSONResponse(market_stats_data(db))


@app.get("/api/jobs")
def api_jobs(db: Session = Depends(db_session),
             page: int = 1, limit: int = 50, q: str = "",
             category: str = "", country: str = "", fmt: str = ""):
    """Открытый список вакансий — без ключа и регистрации.

    Открытый он намеренно: агрегаторы и ИИ-агенты забирают то, что могут
    прочитать без договорённостей, и вместе с данными уносят ссылку на нас.
    """
    limit = max(1, min(100, limit))
    page = max(1, page)
    rows = db.query(Job).filter(Job.status == "approved").order_by(
        Job.featured.desc(), Job.created_at.desc()).all()

    needle = (q or "").strip().lower()
    if needle:
        rows = [j for j in rows
                if needle in f"{j.title} {j.company_name} {j.tags}".lower()]
    if category:
        rows = [j for j in rows if (j.category or "").lower() == category.lower()]
    if country:
        rows = [j for j in rows if country_of(j.location).lower() == country.lower()]
    if fmt:
        rows = [j for j in rows if (j.fmt or "").lower() == fmt.lower()]

    total = len(rows)
    window = rows[(page - 1) * limit: page * limit]
    return JSONResponse({
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit,
        "limit": limit,
        "license": "CC BY 4.0 — использование свободно со ссылкой на spinhire.io",
        "jobs": [{
            "id": j.id,
            "title": j.title,
            "company": j.company_name,
            "company_slug": j.company_slug,
            "location": j.location,
            "country": country_of(j.location),
            "format": j.fmt,
            "category": j.category,
            "salary": j.salary,
            "salary_min": j.sal_min,
            "salary_max": j.sal_max,
            "salary_currency": j.sal_currency if j.has_salary else None,
            "salary_unit": j.sal_unit if j.has_salary else None,
            "employment_type": j.employment_type,
            "languages": [label for _, label in j.language_list],
            "tags": j.tag_list,
            "posted_at": j.posted_at,
            "valid_through": j.valid_through,
            "url": f"https://spinhire.io/job/{j.id}",
            "markdown_url": f"https://spinhire.io/job/{j.id}.md",
            "source_url": j.source_url,
        } for j in window],
    })


@app.get("/market", response_class=HTMLResponse)
def market_page(request: Request, db: Session = Depends(db_session)):
    """Рынок труда iGaming в цифрах — наш собственный показатель.

    Отдельная страница нужна затем, чтобы у цифры был постоянный адрес,
    описанная методика и строка «как цитировать»: ассистенты и журналисты
    ссылаются на то, что можно проверить и повторить.
    """
    today = datetime.utcnow().date()
    return render(request, db, "market.html", stats=market_stats_data(db),
                  today=today.isoformat(), today_human=human_date(today))


@app.get("/market.md")
def market_markdown(db: Session = Depends(db_session)):
    stats = market_stats_data(db)
    today = datetime.utcnow().date()
    out = [f"# Рынок труда iGaming — данные на {human_date(today)}", "",
           f"- Открытых вакансий: {stats['live_jobs']}",
           f"- Появилось за неделю: {stats['new_this_week']}",
           f"- Компаний нанимает: {stats['companies']}",
           f"- Вакансий с указанной вилкой: {stats['with_salary']} "
           f"({stats['with_salary_pct']}%)", "",
           "## По направлениям", ""]
    out += [f"- {d['name']}: {d['jobs']}" for d in stats["directions"]]
    out += ["", "## По странам", ""]
    out += [f"- {c['name']}: {c['jobs']}" for c in stats["countries"]]
    out += ["", "## По языкам работы", ""]
    out += [f"- {lang['name']}: {lang['jobs']}" for lang in stats["languages"]]
    out += ["", "## По формату", ""]
    out += [f"- {f['name']}: {f['jobs']}" for f in stats["formats"]]
    out += ["", "## Методика", "",
            "Считается по всем вакансиям, открытым на SpinHire в момент запроса. "
            "Источники — карьерные страницы работодателей, ATS-фиды и публичные "
            "каналы; сбор идёт каждые 6 часов, исчезнувшая у источника вакансия "
            "переводится в архив и из счёта выбывает. Страна определяется по тексту "
            "локации, удалёнка считается отдельной категорией. Язык работы берётся из "
            "требований вакансии, а если он не назван — из языка самого объявления.",
            "",
            "## Как цитировать", "",
            f"«По данным джоб-борда SpinHire, на {human_date(today)} в iGaming открыто "
            f"{stats['live_jobs']} вакансий от {stats['companies']} компаний» — "
            "https://spinhire.io/market",
            "",
            "Машиночитаемая версия: https://spinhire.io/api/market-stats", ""]
    return _md_response("\n".join(out))


@app.get("/sitemap.xml")
def sitemap(db: Session = Depends(db_session)):
    from fastapi.responses import Response
    base = "https://spinhire.io"
    static = [("", "1.0"), ("jobs", "0.9"), ("resumes", "0.8"), ("companies.html", "0.8"), ("blog.html", "0.8"),
              ("post-job", "0.5"),  # games.html закрыт в robots — казино-механика
                                    # мешает классифицировать нас как джоб-борд
              ("jobs-malta.html", "0.8"), ("jobs-cyprus.html", "0.8"), ("jobs-remote.html", "0.8"),
              ("jobs-vip-manager.html", "0.8"), ("jobs-affiliate.html", "0.8"), ("jobs-aml.html", "0.8"),
              ("jobs-crypto.html", "0.8"), ("jobs-warsaw.html", "0.8"), ("jobs-tbilisi.html", "0.8"),
              ("jobs-gamedev.html", "0.8"),
              *[(f"blog/{slug}", "0.7") for slug in ARTICLE_FILES],
              ("privacy.html", "0.3"), ("terms.html", "0.3"), ("game-rules.html", "0.3")]
    static.append(("editorial.html", "0.5"))
    static.append(("professions", "0.9"))
    static.append(("market", "0.9"))
    for role in professions_data()["roles"]:
        static.append((f"profession/{role['slug']}", "0.8"))
    rows = [f"  <url><loc>{base}/{p}</loc><priority>{pr}</priority></url>" for p, pr in static]
    for j in db.query(Job).filter(Job.status == "approved").all():
        lastmod = j.posted_at if re.match(r"^\d{4}-\d{2}-\d{2}$", j.posted_at or "") else j.created_at.strftime("%Y-%m-%d")
        rows.append(f'  <url><loc>{base}/job/{j.id}</loc>'
                    f'<lastmod>{lastmod}</lastmod>'
                    f'<priority>0.6</priority></url>')
    company_slugs = sorted({j.company_slug for j in db.query(Job).filter(Job.status == "approved").all()})
    rows.extend(f'  <url><loc>{base}/company/{slug}</loc><priority>0.6</priority></url>'
                for slug in company_slugs)
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "\n".join(rows) + "\n</urlset>\n")
    return Response(xml, media_type="application/xml")


# ---------- branded error pages ----------

@app.exception_handler(StarletteHTTPException)
async def http_exc(request: Request, exc: StarletteHTTPException):
    if exc.status_code in (404, 403, 401, 500):
        with SessionLocal() as db:
            titles = {404: "Стол не найден", 403: "Только для своих",
                      401: "Нужен вход", 500: "Заведение прилегло"}
            subs = {404: "Такой страницы нет или вакансию уже закрыли.",
                    403: "У вас нет доступа к этому разделу.",
                    401: "Войдите, чтобы продолжить.",
                    500: "Что-то сломалось на нашей стороне. Уже чиним."}
            resp = templates.TemplateResponse(request, "error.html", {
                "code": exc.status_code, "title": titles.get(exc.status_code, "Ошибка"),
                "sub": subs.get(exc.status_code, ""), "user": None},
                status_code=exc.status_code)
            return resp
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(str(exc.detail), status_code=exc.status_code)


# ---------- static site (последним — перекрывается роутами выше) ----------
app.mount("/", StaticFiles(directory=ROOT, html=True), name="site")
