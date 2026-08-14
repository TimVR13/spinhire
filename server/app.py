# -*- coding: utf-8 -*-
"""SpinHire backend: вакансии, отклики, кабинеты, админка.

Запуск:  uvicorn server.app:app --reload --port 8000
Сид:     при пустой базе создаёт админа и импортирует data/jobs.csv
"""
import csv
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
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
                        String, Text, create_engine, func, or_)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "spinhire.db")
SECRET = os.environ.get("SPINHIRE_SECRET", "spinhire-dev-secret-change-me")
ADMIN_EMAIL = os.environ.get("SPINHIRE_ADMIN_EMAIL", "admin@spinhire.org")
ADMIN_PASSWORD = os.environ.get("SPINHIRE_ADMIN_PASSWORD", "spinhire-boss-2026")

# ---- внешние интеграции (секреты только из окружения; пустые дефолты для локали) ----
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM = os.environ.get("RESEND_FROM", "")
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")
# Подтверждение почты включается автоматически, когда настроен Resend.
REQUIRE_VERIFY = bool(RESEND_API_KEY)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()
signer = URLSafeSerializer(SECRET, salt="session")

CATEGORIES = ["Операции казино", "Беттинг и трейдинг", "Разработка игр",
              "Аффилейты и медиабаинг", "Комплаенс и AML", "Платежи и антифрод",
              "Саппорт (языки)", "Маркетинг и CRM", "Данные и BI", "Топ-менеджмент"]
FORMATS = ["офис", "гибрид", "удалёнка", "удалёнка ЕС"]


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
    incognito = Column(Boolean, default=True)
    coins = Column(Integer, default=0)              # SpinCoins на аккаунте
    last_spin = Column(DateTime, nullable=True)     # последний ежедневный фриспин
    verified = Column(Integer, default=1)           # 0 — ждём подтверждения почты; старые = 1
    otp_hash = Column(String, default="")           # хэш текущего кода подтверждения
    otp_expires = Column(String, default="")        # ISO-время истечения кода
    otp_attempts = Column(Integer, default=0)       # попыток ввода текущего кода
    created_at = Column(DateTime, default=datetime.utcnow)
    jobs = relationship("Job", back_populates="owner")
    applications = relationship("Application", back_populates="user")


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
    status = Column(String, default="pending")  # pending | approved | rejected | archived
    featured = Column(Boolean, default=False)
    views = Column(Integer, default=0)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User", back_populates="jobs")
    applications = relationship("Application", back_populates="job", cascade="all, delete-orphan")

    @property
    def tag_list(self):
        return [t.strip() for t in self.tags.split(",") if t.strip()][:3]

    @property
    def has_salary(self):
        return any(c.isdigit() for c in (self.salary or ""))

    @property
    def _sal_nums(self):
        import re as _re
        nums = [int(n.replace(" ", "")) for n in _re.findall(r"\d[\d ]*", self.salary or "")]
        return [n for n in nums if n > 0]

    @property
    def sal_min(self):
        n = self._sal_nums
        return min(n) if n else None

    @property
    def sal_max(self):
        n = self._sal_nums
        return max(n) if n else None

    @property
    def sal_currency(self):
        s = self.salary or ""
        if "USDT" in s:
            return "USDT"
        if "$" in s:
            return "USD"
        return "EUR"

    @property
    def logo_url(self):
        """Фото/логотип компании через favicon-сервис по домену (если известен)."""
        dom = company_domain(self.company_name)
        return f"https://icons.duckduckgo.com/ip3/{dom}.ico" if dom else ""

    @property
    def company_slug(self):
        import re as _re
        s = _re.sub(r"[^a-zа-я0-9]+", "-", (self.company_name or "").lower()).strip("-")
        return s or "company"

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
    status = Column(String, default="new")  # new | viewed | invited | rejected
    created_at = Column(DateTime, default=datetime.utcnow)
    job = relationship("Job", back_populates="applications")
    user = relationship("User", back_populates="applications")


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    city = Column(String, default="")
    date_from = Column(String, default="")   # YYYY-MM-DD
    date_to = Column(String, default="")
    url = Column(String, default="")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


PLANS = {
    "single": ("Одна вакансия", 199, "Размещение вакансии на 30 дней"),
    "featured": ("Featured ⚡", 399, "Топ поиска + главная, 60 дней"),
    "pack5": ("Пакет 5 вакансий", 799, "5 размещений по 30 дней"),
    "cv10": ("10 контактов из базы", 69, "Открытие 10 контактов резюме (€6.9/контакт)"),
    "cv40": ("40 контактов из базы", 199, "Открытие 40 контактов резюме (€4.98/контакт)"),
    "cvunlim": ("База резюме — безлимит / мес", 349, "Безлимитные контакты на 30 дней"),
    "hunt": ("Подбор под ключ", 1999, "Шорт-лист под роль за 7 дней"),
}


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
}


def company_domain(name: str) -> str:
    n = (name or "").lower().strip()
    if n in COMPANY_DOMAINS:
        return COMPANY_DOMAINS[n]
    # частичное совпадение по ключевому слову бренда
    for key, dom in COMPANY_DOMAINS.items():
        if key in n or n in key:
            return dom
    return ""


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
    ("Саппорт (языки)", ("customer support", "customer service", "support agent", "саппорт",
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
    if db.query(User).first():
        return
    db.add(User(email=ADMIN_EMAIL, password_hash=hash_pw(ADMIN_PASSWORD),
                name="Админ", role="admin"))
    db.commit()
    print(f"[seed] админ создан: {ADMIN_EMAIL}")


def migrate(db: Session):
    """Лёгкая миграция: добавить недостающие колонки в существующую БД."""
    from sqlalchemy import text
    cols = {r[1] for r in db.execute(text("PRAGMA table_info(jobs)")).fetchall()}
    for name in ("source", "ext_id", "posted_at", "deadline"):
        if name not in cols:
            db.execute(text(f"ALTER TABLE jobs ADD COLUMN {name} VARCHAR DEFAULT ''"))
    ucols = {r[1] for r in db.execute(text("PRAGMA table_info(users)")).fetchall()}
    if "coins" not in ucols:
        db.execute(text("ALTER TABLE users ADD COLUMN coins INTEGER DEFAULT 0"))
    if "last_spin" not in ucols:
        db.execute(text("ALTER TABLE users ADD COLUMN last_spin DATETIME"))
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
            ("SBC Summit 2026", "🇵🇹 Лиссабон, Португалия", "2026-09-02", "2026-09-04", "https://sbcevents.com"),
            ("iGB L!VE", "🇬🇧 Лондон, Великобритания", "2026-09-23", "2026-09-25", "https://igblive.com"),
            ("SiGMA Europe (Malta Week)", "🇲🇹 Мальта", "2026-11-10", "2026-11-13", "https://sigma.world"),
            ("SBC Summit Latinoamérica", "🇧🇷 Сан-Паулу, Бразилия", "2026-12-02", "2026-12-04", "https://sbcevents.com"),
            ("ICE Barcelona", "🇪🇸 Барселона, Испания", "2027-01-20", "2027-01-22", "https://icegaming.com"),
            ("SiGMA Eurasia", "🇦🇪 Дубай, ОАЭ", "2027-02-25", "2027-02-27", "https://sigma.world"),
        ]:
            db.add(Event(title=e[0], city=e[1], date_from=e[2], date_to=e[3], url=e[4]))
        db.commit()


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
_SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path.lower()
    if (path in _BLOCKED_EXACT or path.startswith(_BLOCKED_PREFIXES)
            or path.endswith(_BLOCKED_SUFFIXES)):
        # sitemap.xml / robots.txt / og-cover.jpg остаются доступны — не .md/.py/.db
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("Not found", status_code=404)
    resp = await call_next(request)
    for k, v in _SECURITY_HEADERS.items():
        resp.headers.setdefault(k, v)
    return resp


@app.on_event("startup")
def _startup():
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        migrate(db)
        seed(db)
        purge_thin_external(db)
        backfill_categories(db)
        # первичный сбор клонов, если вакансий ещё нет (best-effort, не валит старт)
        if db.query(Job).count() == 0:
            try:
                from server import crawler
                crawler.run(db, Job, guess_category)
            except Exception as e:
                print(f"[startup] первичный crawl не удался: {str(e)[:120]}")


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


def render(request, db, name, **ctx):
    ctx.setdefault("user", get_user(request, db))
    return templates.TemplateResponse(request, name, ctx)


def login_redirect(next_url: str):
    return RedirectResponse(f"/login?next={next_url}", status_code=303)


def set_session(resp, user: User):
    resp.set_cookie("sh_session", signer.dumps({"uid": user.id}),
                    httponly=True, max_age=30 * 24 * 3600, samesite="lax")
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

JOBS_PER_PAGE = 100


@app.get("/jobs", response_class=HTMLResponse)
def jobs_list(request: Request, q: str = "", fmt: str = "", cat: str = "",
              loc: str = "", salary_only: int = 0, page: int = 1,
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
        jobs = [j for j in jobs
                if ql in f"{j.title} {j.company_name} {j.tags} {j.location}".lower()]
    if salary_only:
        jobs = [j for j in jobs if j.has_salary]

    # список локаций для выпадающего фильтра (страна/город)
    locations = sorted({j.location for j in base.all() if j.location})

    # пагинация по 100 на страницу
    found = len(jobs)
    total_pages = max(1, (found + JOBS_PER_PAGE - 1) // JOBS_PER_PAGE)
    page = max(1, min(page, total_pages))
    page_jobs = jobs[(page - 1) * JOBS_PER_PAGE: page * JOBS_PER_PAGE]

    from urllib.parse import urlencode
    active = {k: v for k, v in (("q", q), ("fmt", fmt), ("cat", cat),
              ("loc", loc), ("salary_only", salary_only or "")) if v}
    qs_base = urlencode(active)

    return render(request, db, "jobs.html", jobs=page_jobs, q=q, fmt=fmt, cat=cat,
                  loc=loc, salary_only=salary_only, formats=FORMATS, categories=CATEGORIES,
                  locations=locations, page=page, total_pages=total_pages, found=found,
                  qs_base=qs_base,
                  total=base.count())


@app.get("/api/featured-jobs")
def api_featured(db: Session = Depends(db_session)):
    """Реальные вакансии для блока «Вакансии дня» на главной (внутренние ссылки /job/{id})."""
    from fastapi.responses import JSONResponse
    jobs = (db.query(Job).filter(Job.status == "approved")
            .order_by(Job.featured.desc(), Job.created_at.desc()).limit(30).all())
    # приоритет — с зарплатой, потом свежие; берём 6
    jobs.sort(key=lambda j: (not j.has_salary,))
    out = [{"id": j.id, "title": j.title, "company": j.company_name,
            "location": j.location or "—", "fmt": j.fmt,
            "salary": j.salary if j.has_salary else "по запросу",
            "cat": j.category, "initials": j.initials} for j in jobs[:6]]
    return JSONResponse(out)


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
    return render(request, db, "company.html", company=company, jobs=matched,
                  domain=dom, logo=matched[0].logo_url, locations=locs[:6])


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
                    "dt": e.date_from, "end": e.date_to or e.date_from, "url": e.url})
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
    if not job or job.status != "approved":
        raise HTTPException(404)
    job.views += 1
    db.commit()
    user = get_user(request, db)
    applied = bool(user and db.query(Application).filter_by(job_id=job.id, user_id=user.id).first())
    similar = (db.query(Job).filter(Job.status == "approved", Job.id != job.id,
                                    Job.category == job.category)
               .order_by(Job.featured.desc(), Job.created_at.desc()).limit(3).all())
    return render(request, db, "job.html", job=job, applied=applied,
                  applies=len(job.applications), similar=similar)


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
        db.add(Application(job_id=job_id, user_id=user.id, cover=cover.strip()))
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
    dest = safe_next(next) if u.role not in ("admin", "employer") else dest_for(u)
    return set_session(RedirectResponse(dest, status_code=303), u)


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request, role: str = "talent", db: Session = Depends(db_session)):
    return render(request, db, "register.html", role=role, error="")


@app.post("/register")
def register(request: Request, email: str = Form(...), password: str = Form(...),
             name: str = Form(""), role: str = Form("talent"),
             company_name: str = Form(""), db: Session = Depends(db_session)):
    role = role if role in ("talent", "employer") else "talent"
    if db.query(User).filter(func.lower(User.email) == email.strip().lower()).first():
        return render(request, db, "register.html", role=role, error="Такая почта уже зарегистрирована — войдите")
    if len(password) < 6:
        return render(request, db, "register.html", role=role, error="Пароль — от 6 символов")
    u = User(email=email.strip().lower(), password_hash=hash_pw(password),
             name=name.strip(), role=role, company_name=company_name.strip())
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
    dest = "/employer" if role == "employer" else "/profile"
    return set_session(RedirectResponse(dest, status_code=303), u)


@app.get("/logout")
def logout():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("sh_session")
    return resp


# ---------- Google OAuth ----------

@app.get("/auth/google")
def auth_google():
    if not GOOGLE_CLIENT_ID:
        return RedirectResponse("/login?e=google_off", status_code=307)
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
    resp.set_cookie("sh_oauth", signer.dumps({"state": state}),
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
            saved = signer.loads(raw).get("state")
        except BadSignature:
            return fail
        if not saved or not secrets.compare_digest(str(saved), str(state)):
            return fail

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
                     name=name, role="talent", verified=1)
            db.add(u)
            db.commit()
        elif not u.verified:
            # вход через Google подтверждает владение почтой
            u.verified = 1
            u.otp_hash = ""
            u.otp_expires = ""
            db.commit()

        resp = set_session(RedirectResponse(dest_for(u), status_code=303), u)
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
    return render(request, db, "profile.html", apps=apps, spin_ready=spin_ready)


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
                 incognito: str = Form(None), db: Session = Depends(db_session)):
    user = get_user(request, db)
    if not user:
        return login_redirect("/profile")
    user.name, user.headline = name.strip(), headline.strip()
    user.salary_expect, user.languages = salary_expect.strip(), languages.strip()
    user.incognito = bool(incognito)
    db.commit()
    return RedirectResponse("/profile?ok=1", status_code=303)


# ---------- employer cabinet ----------

@app.get("/employer", response_class=HTMLResponse)
def employer(request: Request, db: Session = Depends(db_session)):
    user = get_user(request, db)
    if not user:
        return login_redirect("/employer")
    if user.role == "talent":
        return RedirectResponse("/profile")
    jobs = (db.query(Job).filter(Job.owner_id == user.id)
            .order_by(Job.created_at.desc()).all())
    return render(request, db, "employer.html", jobs=jobs)


@app.post("/employer/app/{app_id}/status")
def app_status(app_id: int, request: Request, status: str = Form(...),
               db: Session = Depends(db_session)):
    user = get_user(request, db)
    a = db.get(Application, app_id)
    if not user or not a or (a.job.owner_id != user.id and user.role != "admin"):
        raise HTTPException(403)
    if status in ("new", "viewed", "invited", "rejected"):
        a.status = status
        db.commit()
    return RedirectResponse("/employer", status_code=303)


@app.get("/post-job", response_class=HTMLResponse)
def post_job_page(request: Request, db: Session = Depends(db_session)):
    user = get_user(request, db)
    return render(request, db, "post_job.html", categories=CATEGORIES, formats=FORMATS,
                  posted=False, need_login=not user or user.role == "talent")


@app.post("/post-job")
def post_job(request: Request, title: str = Form(...), category: str = Form(""),
             location: str = Form(""), fmt: str = Form("удалёнка"),
             salary_from: str = Form(""), salary_to: str = Form(""),
             currency: str = Form("EUR net"), tags: str = Form(""),
             description: str = Form(""), db: Session = Depends(db_session)):
    user = get_user(request, db)
    if not user or user.role == "talent":
        return login_redirect("/post-job")

    def err(msg):
        return render(request, db, "post_job.html", categories=CATEGORIES, formats=FORMATS,
                      posted=False, need_login=False, error=msg)

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

    unit = currency.split()[1] if " " in currency else ""
    if currency.startswith("USDT"):
        salary = f"{s_from}–{s_to} USDT"
    elif currency.startswith("USD"):
        salary = f"${s_from}–{s_to} {unit}".strip()
    else:
        salary = f"€{s_from}–{s_to} {unit}".strip()
    db.add(Job(title=title.strip(),
               company_name=user.company_name or user.name or user.email,
               category=category or guess_category(title, tags),
               location=location.strip(), fmt=fmt, salary=salary,
               tags=tags.strip(), description=description.strip(),
               owner_id=user.id, status="pending"))
    db.commit()
    return render(request, db, "post_job.html", categories=CATEGORIES, formats=FORMATS,
                  posted=True, need_login=False)


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
        res = crawler.run(db, Job, guess_category)
        msg = f"Собрано {res['collected']}, добавлено {res['added']}, обновлено {res['updated']}"
    except Exception as e:
        msg = f"Ошибка краулера: {str(e)[:150]}"
    return RedirectResponse(f"/admin?tab=jobs&crawl={msg}", status_code=303)


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
    elif tab == "sources":
        from server import crawler
        from collections import Counter
        counts = Counter(j.source or "внутренние/ручные"
                         for j in db.query(Job).filter(Job.status == "approved").all())
        ctx["sources"] = crawler.SOURCE_REGISTRY
        ctx["source_counts"] = dict(counts)
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
                   salary: str = Form(""), tags: str = Form(""),
                   description: str = Form(""), db: Session = Depends(db_session)):
    need_admin(request, db)
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404)
    job.title, job.company_name = title.strip(), company_name.strip()
    job.category, job.location, job.fmt = category, location.strip(), fmt
    job.salary = salary.strip() or "по запросу"
    job.tags, job.description = tags.strip(), description.strip()
    db.commit()
    return RedirectResponse("/admin?tab=jobs", status_code=303)


# события — CRUD
@app.post("/admin/event/add")
def admin_event_add(request: Request, title: str = Form(...), city: str = Form(""),
                    date_from: str = Form(""), date_to: str = Form(""), url: str = Form(""),
                    db: Session = Depends(db_session)):
    need_admin(request, db)
    if title.strip() and date_from.strip():
        db.add(Event(title=title.strip(), city=city.strip(), date_from=date_from.strip(),
                     date_to=date_to.strip(), url=url.strip()))
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
            o.status = "paid"
            # применяем плюшку: featured-план поднимает вакансию
            if o.plan == "featured" and o.job_id:
                job = db.get(Job, o.job_id)
                if job:
                    job.featured = True
                    job.status = "approved"
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
        db.delete(u)
    elif action in ("talent", "employer", "admin"):
        u.role = action
    db.commit()
    return RedirectResponse("/admin?tab=users", status_code=303)


# ---------- sitemap (динамический, включает живые вакансии) ----------

@app.get("/sitemap.xml")
def sitemap(db: Session = Depends(db_session)):
    from fastapi.responses import Response
    base = "https://spinhire.org"
    static = [("", "1.0"), ("jobs", "0.9"), ("companies.html", "0.8"), ("blog.html", "0.8"),
              ("post-job", "0.5"), ("games.html", "0.5"),
              ("jobs-malta.html", "0.8"), ("jobs-cyprus.html", "0.8"), ("jobs-remote.html", "0.8"),
              ("jobs-vip-manager.html", "0.8"), ("jobs-affiliate.html", "0.8"), ("jobs-aml.html", "0.8"),
              ("jobs-crypto.html", "0.8"), ("jobs-warsaw.html", "0.8"), ("jobs-tbilisi.html", "0.8"),
              ("jobs-gamedev.html", "0.8"),
              ("post-salaries-igaming-2026.html", "0.7"), ("post-relocation-malta.html", "0.7"),
              ("post-vip-manager.html", "0.7"), ("post-limassol-vs-warsaw.html", "0.7"),
              ("post-compliance-career.html", "0.7"), ("post-crypto-salary.html", "0.7"),
              ("privacy.html", "0.3"), ("terms.html", "0.3"), ("game-rules.html", "0.3")]
    rows = [f"  <url><loc>{base}/{p}</loc><priority>{pr}</priority></url>" for p, pr in static]
    for j in db.query(Job).filter(Job.status == "approved").all():
        rows.append(f'  <url><loc>{base}/job/{j.id}</loc>'
                    f'<lastmod>{j.created_at.strftime("%Y-%m-%d")}</lastmod>'
                    f'<priority>0.6</priority></url>')
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
