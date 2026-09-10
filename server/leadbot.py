# -*- coding: utf-8 -*-
"""Бот откликов: новый отклик на чужую вакансию → сообщение Алине в Telegram.

Что уходит на каждый отклик (или пачку откликов в одну компанию):
  1) карточка отклика — вакансия, анонимное резюме кандидата, сайт компании и
     найденные контакты HR (почта и ссылки на LinkedIn);
  2) готовый текст для HR — копипастом, на языке компании (ru/en);
  3) ссылка на регистрацию компании /claim/<token> и строка про расценки.

Отправляет только Алине (SPINHIRE_TG_LEAD_CHAT) — дальше она сама пишет HR.

Переменные окружения:
  SPINHIRE_TG_BOT_TOKEN   тот же бот, что постит в каналы (@postingspin_bot)
  SPINHIRE_TG_LEAD_CHAT   chat_id Алины; список кандидатов — /admin/leadbot/chats
  SPINHIRE_LEAD_EVERY_MIN как часто проверять отклики, по умолчанию 10 минут
  SPINHIRE_LEAD_HOURS     окно отправки в часах МСК, по умолчанию 9-22

Подключается в конце app.py: from server import leadbot; app.include_router(leadbot.router)
"""
import json
import os
import re
import socket
import struct
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import Session

from server.app import (Application, BASE_URL, Base, Job, Resume, SessionLocal,
                        User, company_domain, db_session, host_of, is_c_level,
                        need_admin, resume_card, slugify_company, unlock_cost)

router = APIRouter()

TOKEN = os.environ.get("SPINHIRE_TG_BOT_TOKEN", "")
LEAD_CHAT = os.environ.get("SPINHIRE_TG_LEAD_CHAT", "")
EVERY_MIN = max(2, int(os.environ.get("SPINHIRE_LEAD_EVERY_MIN", "10")))
TZ_OFFSET = int(os.environ.get("SPINHIRE_TG_TZ_OFFSET", "3"))
_hours = os.environ.get("SPINHIRE_LEAD_HOURS", "9-22").split("-")
HOUR_FROM, HOUR_TO = int(_hours[0]), int(_hours[-1])
SITE = (BASE_URL or "https://spinhire.io").rstrip("/")
FETCH_TIMEOUT = 12
# Отклики старше этого срока не пересылаем: на первом запуске бот иначе высыпает
# в чат весь исторический хвост. Их по-прежнему видно в /admin/crm/leads.
MAX_AGE_DAYS = int(os.environ.get("SPINHIRE_LEAD_MAX_AGE_DAYS", "14"))


class LeadNotice(Base):
    """Какие отклики уже отправлены Алине — чтобы не слать дважды."""
    __tablename__ = "lead_notices"
    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, unique=True, nullable=False)
    company_slug = Column(String, default="")
    chat_id = Column(String, default="")
    ok = Column(Boolean, default=True)
    error = Column(String, default="")
    sent_at = Column(DateTime, default=datetime.utcnow)


class CompanyHr(Base):
    """Результат поиска HR по компании: чтобы не ходить на сайт при каждом отклике."""
    __tablename__ = "company_hr"
    id = Column(Integer, primary_key=True)
    company_slug = Column(String, unique=True, nullable=False)
    website = Column(String, default="")
    careers_url = Column(String, default="")
    emails = Column(Text, default="")          # найденные на сайте, через запятую
    guesses = Column(Text, default="")         # hr@/careers@ — гипотезы, MX проверен
    linkedin = Column(String, default="")      # страница компании или поиск людей
    checked_at = Column(DateTime, default=datetime.utcnow)


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------- поиск HR ----------

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,12}")
HR_WORDS = ("hr", "career", "careers", "job", "jobs", "recruit", "recruitment",
            "talent", "people", "cv", "resume", "hiring", "work")
JUNK_MAIL = ("example.com", "sentry.io", "wixpress.com", "domain.com", "email.com",
             "yourdomain", "sample", "test@", "@2x", ".png", ".jpg", ".webp", ".gif")
CONTACT_PATHS = ("", "/contact", "/contacts", "/contact-us", "/about", "/about-us",
                 "/careers", "/career", "/jobs", "/join-us", "/work-with-us")
GUESS_LOCAL = ("hr", "careers", "jobs", "recruitment", "people")
# careers.acme.com — это ATS, почту компания держит на корневом домене
SUB_PREFIXES = ("www", "careers", "career", "jobs", "job", "job-boards", "boards",
                "apply", "recruiting", "recruitment", "talent", "hr", "my", "work")


def root_domain(host: str) -> str:
    parts = [p for p in (host or "").lower().split(".") if p]
    while len(parts) > 2 and parts[0] in SUB_PREFIXES:
        parts.pop(0)
    return ".".join(parts)


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        return resp.read(600_000).decode("utf-8", "replace")


def has_mx(domain: str) -> bool:
    """MX-запись домена без сторонних библиотек: DNS-запрос к 1.1.1.1 по UDP."""
    if not domain:
        return False
    try:
        query = struct.pack(">HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0)
        for part in domain.split("."):
            query += bytes([len(part)]) + part.encode()
        query += b"\x00" + struct.pack(">HH", 15, 1)          # QTYPE=MX, QCLASS=IN
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(4)
        try:
            sock.sendto(query, ("1.1.1.1", 53))
            data, _ = sock.recvfrom(1024)
        finally:
            sock.close()
        return len(data) > 6 and struct.unpack(">H", data[6:8])[0] > 0
    except Exception:                                          # noqa: BLE001
        return False


def _emails_from(page: str, domain: str) -> list:
    out = []
    for raw in EMAIL_RE.findall(page or ""):
        mail = raw.strip(" .,;:'\"").lower()
        if any(bad in mail for bad in JUNK_MAIL) or len(mail) > 80:
            continue
        host = mail.split("@")[-1]
        if domain and not (host == domain or host.endswith("." + domain)
                           or domain.endswith("." + host)):
            continue
        if mail not in out:
            out.append(mail)
    # сначала кадровые ящики: hr@, careers@, jobs@…
    out.sort(key=lambda m: 0 if m.split("@")[0].split(".")[0] in HR_WORDS else 1)
    return out[:6]


def linkedin_links(company_name: str) -> str:
    """Страница людей компании и поиск HR — открывается кликом, скрейпа нет:
    LinkedIn без логина списки не отдаёт, а логиниться ботом — терять аккаунт."""
    slug = re.sub(r"[^a-z0-9]+", "-", (company_name or "").lower()).strip("-")
    people = f"https://www.linkedin.com/company/{slug}/people/?keywords=recruiter"
    search = ("https://www.linkedin.com/search/results/people/?keywords="
              + urllib.parse.quote(f'{company_name} recruiter OR "talent acquisition" OR HR'))
    return f"{people}\n{search}"


def find_hr(db: Session, company_name: str, jobs, refresh: bool = False) -> dict:
    """Сайт компании, почты HR и ссылки на LinkedIn. Результат кэшируется на 30 дней."""
    slug = slugify_company(company_name)
    row = db.query(CompanyHr).filter_by(company_slug=slug).first()
    fresh = row and row.checked_at and row.checked_at > datetime.utcnow() - timedelta(days=30)
    if row and fresh and not refresh:
        return _hr_dict(row)

    website, careers = "", ""
    try:
        from server import crm
        company = db.query(crm.CrmCompany).filter_by(slug=slug).first()
        if company:
            website, careers = company.website or "", company.careers_url or ""
    except Exception:                                          # noqa: BLE001
        company = None
    if not website:
        from server.app import CompanyProfile
        profile = db.query(CompanyProfile).filter_by(slug=slug).first()
        if profile:
            website, careers = website or profile.website, careers or profile.careers_url
    source_url = next((job.source_url for job in jobs if getattr(job, "source_url", "")), "")
    host = host_of(website) or company_domain(company_name, source_url)
    domain = root_domain(host)
    if not website and host:
        website = f"https://{host}"

    emails, guesses = [], []
    if domain:
        hosts = [domain] + ([host] if host and host != domain else [])
        for site in hosts:
            for path in CONTACT_PATHS:
                if len(emails) >= 3:
                    break
                try:
                    emails += [m for m in _emails_from(_get(f"https://{site}{path}"), domain)
                               if m not in emails]
                except Exception:                              # noqa: BLE001
                    continue
        if careers and not any(m.split("@")[0] in HR_WORDS for m in emails):
            try:
                emails += [m for m in _emails_from(_get(careers), domain) if m not in emails]
            except Exception:                                  # noqa: BLE001
                pass
        if not any(m.split("@")[0].split(".")[0] in HR_WORDS for m in emails) and has_mx(domain):
            guesses = [f"{local}@{domain}" for local in GUESS_LOCAL[:3]]

    if not row:
        row = CompanyHr(company_slug=slug)
        db.add(row)
    row.website, row.careers_url = website, careers or ""
    row.emails = ", ".join(emails[:6])
    row.guesses = ", ".join(guesses)
    row.linkedin = linkedin_links(company_name)
    row.checked_at = datetime.utcnow()
    db.flush()
    _save_contact(db, company_name, emails)
    return _hr_dict(row)


def _hr_dict(row: "CompanyHr") -> dict:
    emails = [m for m in (row.emails or "").split(", ") if m]
    return {"website": row.website or "", "careers_url": row.careers_url or "",
            "emails": emails,
            "hr_emails": [m for m in emails if m.split("@")[0].split(".")[0] in HR_WORDS],
            "common": [m for m in emails if m.split("@")[0].split(".")[0] not in HR_WORDS],
            "guesses": [m for m in (row.guesses or "").split(", ") if m],
            "linkedin": row.linkedin or ""}


def _save_contact(db: Session, company_name: str, emails: list) -> None:
    """Найденную почту кладём в CRM — оттуда работает кнопка «Отправить письмо»."""
    if not emails:
        return
    try:
        from server import crm
        company = crm.ensure_company(db, company_name)
        if not company:
            return
        mail = emails[0]
        if db.query(crm.CrmContact).filter_by(company_id=company.id, email=mail).first():
            return
        db.add(crm.CrmContact(company_id=company.id, name=mail.split("@")[0],
                              role_title="HR (найдено ботом)", email=mail,
                              notes="Автопоиск по сайту компании"))
    except Exception as exc:                                   # noqa: BLE001
        print(f"[leadbot] контакт в CRM: {type(exc).__name__}: {exc}")


# ---------- язык компании ----------

CYR_RE = re.compile(r"[а-яё]", re.I)
RU_PLACES = ("cyprus", "кипр", "limassol", "лимассол", "nicosia", "georgia", "грузи",
             "tbilisi", "тбилиси", "armenia", "армени", "yerevan", "ереван", "kazakh",
             "казах", "almaty", "алматы", "ukraine", "украин", "kyiv", "киев", "belarus",
             "беларус", "minsk", "минск", "russia", "росси", "moscow", "москв",
             "montenegro", "черногор", "serbia", "сербия", "belgrade", "белград")


def company_lang(jobs) -> str:
    """RU, если у компании русскоязычная команда: кириллица в вакансиях или офис в СНГ."""
    for job in jobs:
        blob = " ".join([job.title or "", job.company_name or "", (job.description or "")[:600]])
        if CYR_RE.search(blob):
            return "ru"
    for job in jobs:
        place = (job.location or "").lower()
        if any(word in place for word in RU_PLACES):
            return "ru"
    return "en"


# ---------- тексты ----------

def _card_lines(card: dict, job_title: str, lang: str) -> str:
    who = card.get("title") or ("Кандидат" if lang == "ru" else "Candidate")
    facts = " · ".join(card.get("facts") or [])
    skills = ", ".join(card.get("skills") or [])
    about = (card.get("about") or "")[:400]
    head = (f"▸ {who} → откликнулся на «{job_title}»" if lang == "ru"
            else f"▸ {who} → applied to “{job_title}”")
    lines = [head]
    if facts:
        lines.append(f"  {facts}")
    if skills:
        lines.append(("  Навыки: " if lang == "ru" else "  Skills: ") + skills)
    if about:
        lines.append(f"  {about}")
    return "\n".join(lines)


def build_hr_text(company_name: str, items: list, lang: str) -> str:
    """Сообщение №2 — то, что Алина копирует и отправляет HR."""
    cards = "\n\n".join(_card_lines(it["card"], it["job"].title, lang) for it in items[:4])
    titles = sorted({it["job"].title for it in items})
    one = len(items) == 1
    job_line = ("«" + "», «".join(titles[:3]) + "»" if lang == "ru"
                else "“" + "”, “".join(titles[:3]) + "”")
    if lang == "ru":
        head = (f"На нашей платформе SpinHire появился отклик на вашу вакансию {job_line}. "
                f"Вот краткое резюме кандидата:" if one else
                f"На нашей платформе SpinHire появились отклики на ваши вакансии {job_line}. "
                f"Вот краткие резюме кандидатов:")
        tail = ("Чтобы получить его полное резюме, вам необходимо пройти регистрацию."
                if one else
                "Чтобы получить их полные резюме, вам необходимо пройти регистрацию.")
        return f"Добрый день!\n\n{head}\n\n{cards}\n\n{tail}"
    head = (f"A candidate has applied to your job {job_line} on our platform SpinHire. "
            f"Here is a short summary of the candidate:" if one else
            f"Candidates have applied to your jobs {job_line} on our platform SpinHire. "
            f"Here are their short summaries:")
    tail = ("To get the full CV you need to complete a short registration." if one else
            "To get the full CVs you need to complete a short registration.")
    return f"Hello!\n\n{head}\n\n{cards}\n\n{tail}"


def build_link_text(company_name: str, url: str, jobs_count: int, lang: str,
                    cost: int = 1) -> str:
    """Сообщение №3 — ссылка на регистрацию и что стоит денег."""
    price = ("Открытие контакта кандидата — по нашим расценкам: €5 за контакт, "
             "€45 за 10, €120 за 30. Контакт руководителя уровня C-level — 5 открытий."
             if lang == "ru" else
             "Opening a candidate contact is charged at our rates: €5 per contact, "
             "€45 for 10, €120 for 30. A C-level contact costs 5 credits.")
    if lang == "ru":
        return (f"Ссылка для регистрации: {url}\n\n"
                f"По ней вы заводите кабинет компании (почта, пароль, подтверждение почты). "
                f"В кабинете сразу и бесплатно лежат все ваши вакансии — "
                f"{jobs_count} шт., мы собрали их с ваших карьерных страниц. "
                f"Там же вы видите отклики.\n\n{price}")
    return (f"Registration link: {url}\n\n"
            f"It creates your company account (email, password, email confirmation). "
            f"All your openings are already inside for free — {jobs_count} of them, "
            f"collected from your own career pages — together with the applications.\n\n{price}")


def build_owner_text(company_name: str, items: list, hr: dict, lang: str) -> str:
    """Сообщение №1 — Алине: что за отклик и куда писать."""
    n = len(items)
    titles = sorted({it["job"].title for it in items})
    lines = [f"🎯 <b>{'Новый отклик' if n == 1 else 'Новые отклики (%d)' % n}</b> · "
             f"{_esc(company_name)}",
             "Вакансии: " + ", ".join(_esc(t) for t in titles[:3])
             + (f" и ещё {len(titles) - 3}" if len(titles) > 3 else "")]
    for it in items[:4]:
        card = it["card"]
        head = _esc(card.get("title") or "Кандидат")
        if it["clevel"]:
            head += " · C-level"
        row = [f"\n👤 <b>{head}</b>"]
        facts = " · ".join(card.get("facts") or [])
        if facts:
            row.append(_esc(facts))
        if card.get("skills"):
            row.append(_esc(", ".join(card["skills"])))
        if card.get("public") and card.get("id"):
            row.append(f"{SITE}/resume/{card['id']}")
        row.append(f"Открытие контакта: {it['cost']} "
                   + ("кредит" if it["cost"] == 1 else "кредитов"))
        lines.append("\n".join(row))
    if n > 4:
        lines.append(f"\n…и ещё {n - 4}")
    lines.append("\n📍 <b>Куда писать</b>")
    lines.append(f"Сайт: {_esc(hr['website']) or '— не нашли'}")
    if hr.get("careers_url"):
        lines.append(f"Карьера: {_esc(hr['careers_url'])}")
    if hr.get("hr_emails"):
        lines.append("Почта HR: " + ", ".join(_esc(m) for m in hr["hr_emails"]))
    if hr.get("common"):
        lines.append("Общая почта: " + ", ".join(_esc(m) for m in hr["common"]))
    if hr.get("guesses"):
        lines.append("Гипотезы (домен принимает почту, адрес не проверен): "
                     + ", ".join(_esc(m) for m in hr["guesses"]))
    if not (hr.get("emails") or hr.get("guesses")):
        lines.append("Почта не нашлась — пишите в LinkedIn")
    lines.append("LinkedIn:\n" + _esc(hr["linkedin"]))
    lines.append(f"\nЯзык письма: {'русский' if lang == 'ru' else 'английский'}"
                 f"\nКарточка в CRM: {SITE}/admin/crm/leads")
    return "\n".join(lines)


# ---------- отправка ----------

def _api(method: str, payload: dict) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/{method}", data=body,
        headers={"Content-Type": "application/json",
                 "User-Agent": "SpinHire/1.0 (+https://spinhire.io)"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except Exception as exc:                                   # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _send(text: str, html: bool = False) -> dict:
    payload = {"chat_id": LEAD_CHAT, "text": text, "disable_web_page_preview": True}
    if html:
        payload["parse_mode"] = "HTML"
    return _api("sendMessage", payload)


def pending_batches(db: Session, limit_companies: int = 6) -> tuple:
    """Отклики на вакансии без владельца, о которых Алине ещё не сообщали.

    Возвращает (пачки по компаниям, id откликов без пригодного резюме) — про
    последние сообщать нечего: карточка кандидата пустая, HR такое письмо
    только раздражает.
    """
    sent = {row.application_id for row in db.query(LeadNotice.application_id).all()}
    rows = (db.query(Application, Job, User)
            .join(Job, Job.id == Application.job_id)
            .join(User, User.id == Application.user_id)
            .filter(Job.owner_id.is_(None))
            .order_by(Application.created_at.desc()).limit(200).all())
    fresh_from = datetime.utcnow() - timedelta(days=MAX_AGE_DAYS)
    stale = [r[0].id for r in rows
             if r[0].id not in sent and r[0].created_at and r[0].created_at < fresh_from]
    rows = [r for r in rows if r[0].id not in sent and r[0].id not in set(stale)]
    if not rows:
        return [], stale
    resumes = {r.user_id: r for r in db.query(Resume).filter(
        Resume.user_id.in_({u.id for _, _, u in rows}))}
    groups: dict = {}
    empty = list(stale)
    for application, job, user in rows:
        cv = resumes.get(user.id)
        card = resume_card(cv, user.name or "") if cv else {}
        if not (card.get("title") or card.get("skills") or card.get("about")):
            empty.append(application.id)
            continue
        slug = slugify_company(job.company_name)
        group = groups.setdefault(slug, {"company": job.company_name, "slug": slug, "items": []})
        group["items"].append({
            "application": application, "job": job, "user": user, "resume": cv, "card": card,
            "clevel": is_c_level(job.title) or is_c_level(cv.title if cv else ""),
            "cost": unlock_cost(cv) if cv else 1,
        })
    return list(groups.values())[:limit_companies], empty


def send_pending(db: Session, dry: bool = False, refresh_hr: bool = False) -> dict:
    """Разослать Алине всё, о чём ещё не сообщали. Возвращает сводку."""
    from server import claim
    out = {"companies": 0, "applications": 0, "messages": [], "errors": []}
    if not dry and (not TOKEN or not LEAD_CHAT):
        return {"skipped": "нет SPINHIRE_TG_BOT_TOKEN или SPINHIRE_TG_LEAD_CHAT"}
    groups, empty = pending_batches(db)
    if empty and not dry:
        for app_id in empty:
            db.add(LeadNotice(application_id=app_id, ok=False,
                              error="старый отклик или пустое резюме — не отправляли"))
        db.commit()
    out["skipped"] = len(empty)
    for group in groups:
        items = group["items"]
        jobs = [it["job"] for it in items]
        lang = company_lang(jobs)
        try:
            hr = find_hr(db, group["company"], jobs, refresh=refresh_hr)
        except Exception as exc:                               # noqa: BLE001
            hr = {"website": "", "careers_url": "", "emails": [], "guesses": [],
                  "linkedin": linkedin_links(group["company"])}
            out["errors"].append(f"{group['company']}: поиск HR — {type(exc).__name__}")
        row = claim.get_or_create_claim(db, group["company"], lang)
        if not row:
            continue
        all_jobs = claim.company_jobs(db, group["slug"])
        texts = [
            (build_owner_text(group["company"], items, hr, lang), True),
            (build_hr_text(group["company"], items, lang), False),
            (build_link_text(group["company"], claim.claim_url(row), len(all_jobs), lang), False),
        ]
        out["companies"] += 1
        out["applications"] += len(items)
        if dry:
            out["messages"].append({"company": group["company"], "lang": lang,
                                    "hr": hr, "texts": [t for t, _ in texts]})
            continue
        ok, error = True, ""
        for text, as_html in texts:
            resp = _send(text, as_html)
            if not resp.get("ok"):
                ok = False
                error = str(resp.get("description") or resp.get("error"))[:200]
                out["errors"].append(f"{group['company']}: {error}")
                break
            time.sleep(0.4)
        for it in items:
            db.add(LeadNotice(application_id=it["application"].id, company_slug=group["slug"],
                              chat_id=str(LEAD_CHAT), ok=ok, error=error))
        db.commit()
    return out


def notify_claimed(row, user, jobs: int, apps: int) -> None:
    """Компания зарегистрировалась по ссылке — сказать об этом в тот же чат."""
    if not TOKEN or not LEAD_CHAT:
        return
    _send(f"✅ <b>{_esc(row.company_name)}</b> зарегистрировалась по ссылке\n"
          f"Почта: {_esc(user.email)}\nВакансий передано: {jobs} · откликов в кабинете: {apps}\n"
          f"Контакты кандидатов заперты — открываются за кредиты.", html=True)


# ---------- админка ----------

@router.get("/admin/leadbot/preview")
def leadbot_preview(request: Request, db: Session = Depends(db_session)):
    need_admin(request, db)
    return JSONResponse(send_pending(db, dry=True))


@router.post("/admin/leadbot/run")
def leadbot_run(request: Request, dry: int = 0, refresh: int = 0,
                db: Session = Depends(db_session)):
    need_admin(request, db)
    return JSONResponse(send_pending(db, dry=bool(dry), refresh_hr=bool(refresh)))


@router.get("/admin/leadbot/chats")
def leadbot_chats(request: Request, db: Session = Depends(db_session)):
    """Кто писал боту: отсюда берём chat_id для SPINHIRE_TG_LEAD_CHAT."""
    need_admin(request, db)
    if not TOKEN:
        return JSONResponse({"error": "нет SPINHIRE_TG_BOT_TOKEN"})
    data = _api("getUpdates", {"limit": 50, "allowed_updates": ["message"]})
    chats = {}
    for update in data.get("result", []) or []:
        message = update.get("message") or update.get("my_chat_member") or {}
        chat = message.get("chat") or {}
        if chat.get("id"):
            chats[str(chat["id"])] = {
                "id": chat.get("id"), "type": chat.get("type"),
                "name": " ".join(x for x in (chat.get("first_name"), chat.get("last_name"),
                                             chat.get("title")) if x),
                "username": chat.get("username", ""),
            }
    return JSONResponse({"ok": data.get("ok", False), "current": LEAD_CHAT,
                         "chats": list(chats.values()),
                         "hint": "chat_id нужного человека → SPINHIRE_TG_LEAD_CHAT"})


def _scheduler():
    while True:
        try:
            now = datetime.utcnow() + timedelta(hours=TZ_OFFSET)
            if HOUR_FROM <= now.hour < HOUR_TO:
                db = SessionLocal()
                try:
                    res = send_pending(db)
                    if res.get("companies"):
                        print(f"[leadbot] отправлено компаний: {res['companies']}, "
                              f"откликов: {res['applications']}")
                finally:
                    db.close()
        except Exception as exc:                               # noqa: BLE001
            print(f"[leadbot] ошибка планировщика: {type(exc).__name__}: {exc}")
        time.sleep(EVERY_MIN * 60)


def start_scheduler():
    if not TOKEN or not LEAD_CHAT:
        print("[leadbot] молчит: нет SPINHIRE_TG_BOT_TOKEN или SPINHIRE_TG_LEAD_CHAT")
        return
    threading.Thread(target=_scheduler, daemon=True).start()
    print(f"[leadbot] отклики уходят в чат {LEAD_CHAT} каждые {EVERY_MIN} мин "
          f"({HOUR_FROM}:00–{HOUR_TO}:00 +{TZ_OFFSET})")
