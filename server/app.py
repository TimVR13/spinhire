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
    source_url = Column(String, default="")  # внешняя вакансия-агрегат
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
    def initials(self):
        words = [w for w in self.company_name.replace("(", " ").split() if w[:1].isalnum()]
        if not words:
            return "??"
        return (words[0][0] + (words[1][0] if len(words) > 1 else words[0][1:2] or "•")).upper()


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


def seed(db: Session):
    if db.query(User).count():
        return
    admin = User(email=ADMIN_EMAIL, password_hash=hash_pw(ADMIN_PASSWORD),
                 name="Админ", role="admin")
    db.add(admin)
    csv_path = os.path.join(ROOT, "data", "jobs.csv")
    if os.path.exists(csv_path):
        with open(csv_path, encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter=";"):
                db.add(Job(title=row["title"], company_name=row["company"],
                           location=row["location"], fmt=row["format"],
                           salary=row["salary"], tags=row["tags"],
                           source_url=row["source_url"], status="approved"))
    db.commit()
    print(f"[seed] админ создан: {ADMIN_EMAIL}; вакансии импортированы из CSV")


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
    if q:
        like = f"%{q}%"
        qs = qs.filter(or_(Job.title.ilike(like), Job.company_name.ilike(like), Job.tags.ilike(like)))
    if fmt:
        qs = qs.filter(Job.fmt == fmt)
    if cat:
        qs = qs.filter(Job.category == cat)
    jobs = qs.order_by(Job.featured.desc(), Job.created_at.desc()).all()
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
    return render(request, db, "job.html", job=job, applied=applied,
                  applies=len(job.applications))


@app.post("/job/{job_id}/apply")
def job_apply(job_id: int, request: Request, cover: str = Form(""),
              db: Session = Depends(db_session)):
    user = get_user(request, db)
    if not user:
        return login_redirect(f"/job/{job_id}")
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404)
    if not db.query(Application).filter_by(job_id=job_id, user_id=user.id).first():
        db.add(Application(job_id=job_id, user_id=user.id, cover=cover))
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
    dest = "/admin" if u.role == "admin" else ("/employer" if u.role == "employer" else next or "/profile")
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
    return RedirectResponse(request.headers.get("referer") or "/employer", status_code=303)


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
    salary = f"€{salary_from}–{salary_to} {currency.split()[1] if ' ' in currency else ''}".strip() \
        if salary_from and salary_to else "по запросу"
    if currency.startswith("USD"):
        salary = salary.replace("€", "$")
    if currency.startswith("USDT"):
        salary = f"{salary_from}–{salary_to} USDT"
    db.add(Job(title=title.strip(), company_name=user.company_name or user.name or user.email,
               category=category, location=location.strip(), fmt=fmt, salary=salary,
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
    return RedirectResponse(request.headers.get("referer") or "/admin?tab=jobs", status_code=303)


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


# ---------- static site (последним — перекрывается роутами выше) ----------
app.mount("/", StaticFiles(directory=ROOT, html=True), name="site")
