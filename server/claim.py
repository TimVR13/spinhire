# -*- coding: utf-8 -*-
"""Ссылка «заберите свои вакансии»: регистрация компании по её же откликам.

Кандидат откликается на агрегированную вакансию → бот присылает Алине текст для
HR и уникальную ссылку /claim/<token>. Компания по ней регистрируется (почта,
пароль, подтверждение кода), и все её вакансии, собранные краулером, сразу
лежат в кабинете бесплатно.

Контакты кандидатов, которые откликнулись ДО регистрации, остаются платными:
Application.lead_locked = 1, открытие — обычными cv-открытиями. Иначе лид, ради
которого мы искали HR и писали письмо, уходит даром.

Подключается в конце app.py: from server import claim; app.include_router(claim.router)
"""
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Session

from server.app import (Application, BASE_URL, Base, Job, REQUIRE_VERIFY,
                        Resume, SIGNUP_COIN_BONUS, User, _signup_source,
                        db_session, dest_for, get_user, grant_launch_promo,
                        hash_pw, is_c_level, is_real_company, issue_otp, render,
                        request_lang, resume_card, send_otp, set_session,
                        slugify_company, track)

router = APIRouter()


class CompanyClaim(Base):
    """Уникальная ссылка компании на её вакансии у нас.

    Токен хранится открытым: одну и ту же ссылку бот показывает Алине столько
    раз, сколько приходит откликов, — восстановить её из хэша нельзя. Ссылка
    одноразовая (used_at) и ведёт только к регистрации кабинета этой компании.
    """
    __tablename__ = "company_claims"
    id = Column(Integer, primary_key=True)
    company_slug = Column(String, unique=True, nullable=False)   # у пожобной ссылки — job-<id>
    company_name = Column(String, default="")
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True)  # ссылка на одну вакансию
    token = Column(String, unique=True, nullable=False)
    lang = Column(String, default="en")          # язык письма и страницы: ru | en
    created_at = Column(DateTime, default=datetime.utcnow)
    opened_at = Column(DateTime, nullable=True)  # компания открыла ссылку
    used_at = Column(DateTime, nullable=True)    # кабинет создан, вакансии переданы
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)


def get_or_create_claim(db: Session, company_name: str, lang: str = "en") -> "CompanyClaim | None":
    """Ссылка компании на все её вакансии. Только для компаний с настоящим именем:
    по «Компания не указана» ссылка отдала бы двум сотням чужих вакансий один кабинет."""
    if not is_real_company(company_name):
        return None
    slug = slugify_company(company_name)
    row = db.query(CompanyClaim).filter_by(company_slug=slug).first()
    if not row:
        row = CompanyClaim(company_slug=slug, company_name=company_name.strip(),
                           token=secrets.token_urlsafe(24), lang=lang)
        db.add(row)
        db.flush()
    return row


def get_or_create_job_claim(db: Session, job, lang: str = "en") -> "CompanyClaim":
    """Ссылка на одну вакансию — когда работодатель в объявлении не назван.
    Компания вводит своё имя при регистрации, им же подписывается вакансия."""
    slug = f"job-{job.id}"
    row = db.query(CompanyClaim).filter_by(company_slug=slug).first()
    if not row:
        row = CompanyClaim(company_slug=slug, company_name=job.company_name or "",
                           token=secrets.token_urlsafe(24), lang=lang, job_id=job.id)
        db.add(row)
        db.flush()
    return row


def claim_jobs(db: Session, row: "CompanyClaim") -> list:
    """Что именно уедет в кабинет по этой ссылке."""
    if row.job_id:
        job = db.get(Job, row.job_id)
        return [job] if job and job.owner_id is None else []
    return company_jobs(db, row.company_slug)


def needs_company_name(row: "CompanyClaim") -> bool:
    return not is_real_company(row.company_name)


def claim_url(row: "CompanyClaim") -> str:
    """Ссылка в языке компании: /uk/claim/… отдаёт HR страницу целиком украинской
    (шапка, кнопки, футер), русский — базовый язык сайта и префикса не требует."""
    lang = (row.lang or "ru").lower()
    prefix = "" if lang == "ru" else f"/{lang}"
    return f"{(BASE_URL or 'https://spinhire.io').rstrip('/')}{prefix}/claim/{row.token}"


def company_jobs(db: Session, slug: str, only_free: bool = True):
    """Вакансии компании по слагу. company_slug — питоновское свойство, не колонка,
    поэтому фильтруем в памяти по лёгкой выборке (id, company_name)."""
    q = db.query(Job).filter(Job.status.in_(("approved", "pending")))
    if only_free:
        q = q.filter(Job.owner_id.is_(None))
    return [job for job in q.all() if slugify_company(job.company_name) == slug]


def attach_company_jobs(db: Session, row: "CompanyClaim", user: User,
                        company_name: str = "") -> dict:
    """Передать компании её вакансии и запереть контакты по старым откликам."""
    company_name = (company_name or "").strip()
    if company_name and needs_company_name(row):
        row.company_name = company_name          # объявление было без работодателя
    jobs = claim_jobs(db, row)
    for job in jobs:
        job.owner_id = user.id
        if company_name and not is_real_company(job.company_name):
            job.company_name = company_name      # и на борде вакансия наконец подписана
    apps = []
    if jobs:
        apps = (db.query(Application)
                .filter(Application.job_id.in_([job.id for job in jobs])).all())
        for application in apps:
            application.lead_locked = 1
    if user.role == "talent":
        user.role = "employer"
    if not (user.company_name or "").strip():
        user.company_name = row.company_name if is_real_company(row.company_name) else company_name
    grant_launch_promo(user)
    row.used_at = datetime.utcnow()
    row.user_id = user.id
    track(db, "company_claimed", user.id, "company_claim", row.id,
          jobs=len(jobs), applications=len(apps))
    try:
        from server import crm
        company = crm.ensure_company(db, row.company_name) if is_real_company(row.company_name) else None
        if company:
            crm.log_event(db, company.id, "claim",
                          f"Компания зарегистрировалась по ссылке: вакансий {len(jobs)}, "
                          f"откликов {len(apps)}")
            if company.stage in ("new", "contact", "to_notify", "outreach"):
                crm.set_stage(db, company, "replied", "")
    except Exception as exc:                                    # noqa: BLE001
        print(f"[claim] CRM: {type(exc).__name__}: {exc}")
    try:
        from server import leadbot
        leadbot.notify_claimed(row, user, len(jobs), len(apps))
    except Exception as exc:                                    # noqa: BLE001
        print(f"[claim] телеграм: {type(exc).__name__}: {exc}")
    return {"jobs": len(jobs), "applications": len(apps)}


def apply_pending_claim(db: Session, user: User) -> dict:
    """Вызывается после подтверждения почты: если человек пришёл по ссылке — отдать вакансии."""
    row = (db.query(CompanyClaim)
           .filter(CompanyClaim.user_id == user.id, CompanyClaim.used_at.is_(None))
           .first())
    if not row or not user.verified:
        return {}
    return attach_company_jobs(db, row, user, user.company_name or "")


# ---------- страница ----------

TEXT = {
    "ru": {
        "kicker": "Ваши вакансии на SpinHire",
        "title": "{company}: кандидаты уже откликнулись",
        "lead": "Мы собрали ваши вакансии на SpinHire — площадке вакансий iGaming. "
                "На них откликаются кандидаты. Заберите вакансии в свой кабинет: "
                "это бесплатно и занимает минуту.",
        "jobs": "Вакансий перейдёт в кабинет",
        "apps": "Откликов ждёт ответа",
        "cands": "Кто откликнулся",
        "form": "Создать кабинет компании",
        "email": "Рабочая почта",
        "pass": "Пароль (от 6 символов)",
        "name": "Ваше имя",
        "company": "Название компании",
        "company_error": "Укажите название компании — вакансия опубликована без него",
        "submit": "Забрать вакансии →",
        "have": "Уже есть аккаунт SpinHire?",
        "login": "Войдите",
        "attach": "Забрать вакансии в этот кабинет →",
        "note": "Вакансии и кабинет — бесплатно. Открытие контакта кандидата "
                "(имя, почта, телефон, мессенджер) — по тарифам: €5 за контакт, "
                "€45 за 10, €120 за 30. Контакт руководителя уровня C-level — 5 открытий.",
        "used": "Эта ссылка уже использована — войдите в кабинет.",
        "taken": "Такая почта уже зарегистрирована — войдите и заберите вакансии",
    },
    "uk": {
        "kicker": "Ваші вакансії на SpinHire",
        "title": "{company}: кандидати вже відгукнулися",
        "lead": "Ми зібрали ваші вакансії на SpinHire — майданчику вакансій iGaming. "
                "На них відгукуються кандидати. Заберіть вакансії у свій кабінет: "
                "це безкоштовно й займає хвилину.",
        "jobs": "Вакансій перейде в кабінет",
        "apps": "Відгуків чекає на відповідь",
        "cands": "Хто відгукнувся",
        "form": "Створити кабінет компанії",
        "email": "Робоча пошта",
        "pass": "Пароль (від 6 символів)",
        "name": "Ваше ім'я",
        "company": "Назва компанії",
        "company_error": "Вкажіть назву компанії — вакансію опубліковано без неї",
        "submit": "Забрати вакансії →",
        "have": "Вже є акаунт SpinHire?",
        "login": "Увійдіть",
        "attach": "Забрати вакансії в цей кабінет →",
        "note": "Вакансії та кабінет — безкоштовно. Відкриття контакту кандидата "
                "(ім'я, пошта, телефон, месенджер) — за тарифами: €5 за контакт, "
                "€45 за 10, €120 за 30. Контакт керівника рівня C-level — 5 відкриттів.",
        "used": "Це посилання вже використано — увійдіть у кабінет.",
        "taken": "Ця пошта вже зареєстрована — увійдіть і заберіть вакансії",
    },
    "en": {
        "kicker": "Your jobs on SpinHire",
        "title": "{company}: candidates have already applied",
        "lead": "We collected your openings on SpinHire, an iGaming job board, and "
                "candidates are applying to them. Claim the jobs into your own "
                "account — it is free and takes a minute.",
        "jobs": "Jobs moving to your account",
        "apps": "Applications waiting",
        "cands": "Who applied",
        "form": "Create the company account",
        "email": "Work email",
        "pass": "Password (6+ characters)",
        "name": "Your name",
        "company": "Company name",
        "company_error": "Tell us the company name — the posting went out without it",
        "submit": "Claim the jobs →",
        "have": "Already have a SpinHire account?",
        "login": "Sign in",
        "attach": "Claim the jobs into this account →",
        "note": "Jobs and the account are free. Opening a candidate contact "
                "(name, email, phone, messenger) is charged at our rates: €5 per "
                "contact, €45 for 10, €120 for 30. A C-level contact costs 5 credits.",
        "used": "This link has already been used — please sign in.",
        "taken": "This email is already registered — sign in and claim the jobs",
    },
}


def _claim_or_404(db: Session, token: str) -> "CompanyClaim":
    row = db.query(CompanyClaim).filter_by(token=token).first()
    if not row:
        raise HTTPException(404)
    return row


def _page(request: Request, db: Session, row: "CompanyClaim", error: str = "",
          email: str = "") -> HTMLResponse:
    jobs = claim_jobs(db, row)
    apps = []
    if jobs:
        apps = (db.query(Application)
                .filter(Application.job_id.in_([job.id for job in jobs]))
                .order_by(Application.created_at.desc()).all())
    resumes = {r.user_id: r for r in db.query(Resume).filter(
        Resume.user_id.in_({a.user_id for a in apps} or {0}))} if apps else {}
    cards = []
    for application in apps[:5]:
        cv = resumes.get(application.user_id)
        if not cv:
            continue
        card = resume_card(cv, application.user.name or "")
        card["job"] = application.job.title
        card["clevel"] = is_c_level(application.job.title) or is_c_level(cv.title or "")
        cards.append(card)
    return render(request, db, "claim.html", claim=row, jobs=jobs, apps_count=len(apps),
                  cards=cards, t=TEXT.get(row.lang or "en", TEXT["en"]),
                  error=error, email=email, viewer=get_user(request, db),
                  ask_company=needs_company_name(row))


@router.get("/claim/{token}", response_class=HTMLResponse)
def claim_page(token: str, request: Request, db: Session = Depends(db_session)):
    row = _claim_or_404(db, token)
    if not row.opened_at:
        row.opened_at = datetime.utcnow()
        track(db, "claim_opened", None, "company_claim", row.id)
        db.commit()
    if row.used_at:
        return RedirectResponse("/login?claimed=1", status_code=303)
    return _page(request, db, row)


@router.post("/claim/{token}")
def claim_register(token: str, request: Request, email: str = Form(...),
                   password: str = Form(...), name: str = Form(""),
                   company_name: str = Form(""), db: Session = Depends(db_session)):
    row = _claim_or_404(db, token)
    t = TEXT.get(row.lang or "en", TEXT["en"])
    if row.used_at:
        return RedirectResponse("/login?claimed=1", status_code=303)
    em = email.strip().lower()
    if db.query(User).filter(func.lower(User.email) == em).first():
        return _page(request, db, row, email=em, error=t["taken"])
    if len(password) < 6:
        return _page(request, db, row, email=em, error=t["pass"])
    if needs_company_name(row) and not is_real_company(company_name):
        return _page(request, db, row, email=em, error=t["company_error"])
    title = row.company_name if is_real_company(row.company_name) else company_name.strip()
    user = User(email=em, password_hash=hash_pw(password), name=name.strip(),
                role="employer", company_name=title,
                coins=SIGNUP_COIN_BONUS, signup_source="claim",
                lang=row.lang or request_lang(request))
    db.add(user)
    db.flush()
    row.user_id = user.id
    if needs_company_name(row):
        row.company_name = company_name.strip()   # подтвердит почту — этим и подпишем
    db.commit()
    if REQUIRE_VERIFY:
        user.verified = 0
        db.commit()
        code = issue_otp(user, db)
        if send_otp(user, code, row.lang or "en"):
            import urllib.parse
            return RedirectResponse(f"/verify?email={urllib.parse.quote(user.email)}",
                                    status_code=303)
        user.verified = 1                  # письмо не ушло — не запираем компанию
        user.otp_hash = user.otp_expires = ""
        db.commit()
    result = attach_company_jobs(db, row, user, company_name)
    db.commit()
    return set_session(RedirectResponse(
        f"/employer?claimed={result['jobs']}", status_code=303), user)


@router.post("/claim/{token}/attach")
def claim_attach(token: str, request: Request, db: Session = Depends(db_session)):
    """Компания уже зарегистрирована на SpinHire — просто отдаём вакансии в её кабинет."""
    row = _claim_or_404(db, token)
    user = get_user(request, db)
    if not user:
        return RedirectResponse(f"/login?next=/claim/{token}", status_code=303)
    if row.used_at:
        return RedirectResponse("/employer?claimed=0", status_code=303)
    if not user.verified:
        import urllib.parse
        row.user_id = user.id
        db.commit()
        return RedirectResponse(f"/verify?email={urllib.parse.quote(user.email)}",
                                status_code=303)
    result = attach_company_jobs(db, row, user)
    db.commit()
    return RedirectResponse(f"/employer?claimed={result['jobs']}", status_code=303)
