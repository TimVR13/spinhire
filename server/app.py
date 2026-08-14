# -*- coding: utf-8 -*-
"""SpinHire backend: вакансии, отклики, кабинеты, админка.

Запуск:  uvicorn server.app:app --reload --port 8000
Сид:     при пустой базе создаёт админа и импортирует data/jobs.csv
"""
import csv
import os
from datetime import datetime
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


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


_CAT_RULES = [
    ("Комплаенс и AML", ("compl", "aml", "kyc", "комплаенс", "антифрод", "fraud")),
    ("Платежи и антифрод", ("payment", "psp", "платеж", "reconcil", "treasury")),
    ("Аффилейты и медиабаинг", ("affili", "аффил", "media buy", "медиабай", "seo", "promo", "streamer", "influenc")),
    ("Разработка игр", ("developer", "engineer", "разработ", "java", ".net", "backend", "frontend",
                        "математик", "devops", "qa", "unity", "ai engineer", "1c")),
    ("Беттинг и трейдинг", ("trader", "трейдер", "sportsbook", "спортбук", "odds", "беттинг")),
    ("Саппорт (языки)", ("support", "саппорт", "customer service", "presenter", "агент")),
    ("Данные и BI", ("data ", "data eng", "bi ", "analyt", "аналит")),
    ("Маркетинг и CRM", ("crm", "retention", "ретеншн", "vip", "marketing", "маркетинг", "brand")),
    ("Топ-менеджмент", ("head of", "vp ", "chief", "director", "c-level", "директор", "руковод")),
]


def guess_category(title: str, tags: str) -> str:
    text = f"{title} {tags}".lower()
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
    for name in ("source", "ext_id"):
        if name not in cols:
            db.execute(text(f"ALTER TABLE jobs ADD COLUMN {name} VARCHAR DEFAULT ''"))
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
        seed(db)
        migrate(db)
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

@app.get("/jobs", response_class=HTMLResponse)
def jobs_list(request: Request, q: str = "", fmt: str = "", cat: str = "",
              salary_only: int = 0, db: Session = Depends(db_session)):
    qs = db.query(Job).filter(Job.status == "approved")
    if fmt:
        qs = qs.filter(Job.fmt == fmt)
    if cat:
        qs = qs.filter(Job.category == cat)
    jobs = qs.order_by(Job.featured.desc(), Job.created_at.desc()).all()
    if q:
        # регистронезависимо, включая кириллицу (SQLite LIKE не сворачивает регистр не-ASCII)
        ql = q.strip().lower()
        jobs = [j for j in jobs
                if ql in f"{j.title} {j.company_name} {j.tags} {j.location}".lower()]
    if salary_only:
        jobs = [j for j in jobs if j.has_salary]
    return render(request, db, "jobs.html", jobs=jobs, q=q, fmt=fmt, cat=cat,
                  salary_only=salary_only, formats=FORMATS, categories=CATEGORIES,
                  total=db.query(Job).filter(Job.status == "approved").count())


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
    if job.source_url:
        # внешняя вакансия — отклик только у источника
        return RedirectResponse(f"/job/{job_id}", status_code=303)
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
    dest = "/admin" if u.role == "admin" else ("/employer" if u.role == "employer" else safe_next(next))
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
    dest = "/employer" if role == "employer" else "/profile"
    return set_session(RedirectResponse(dest, status_code=303), u)


@app.get("/logout")
def logout():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("sh_session")
    return resp


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
    return render(request, db, "profile.html", apps=apps)


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
        ctx["jobs"] = db.query(Job).order_by(
            (Job.status == "pending").desc(), Job.created_at.desc()).all()
    elif tab == "users":
        ctx["users"] = db.query(User).order_by(User.created_at.desc()).all()
    elif tab == "apps":
        ctx["apps"] = db.query(Application).order_by(Application.created_at.desc()).all()
    else:
        ctx["pending"] = db.query(Job).filter(Job.status == "pending") \
            .order_by(Job.created_at.desc()).limit(10).all()
    return render(request, db, "admin.html", **ctx)


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
