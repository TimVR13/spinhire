# -*- coding: utf-8 -*-
"""CRM SpinHire: пайплайн компаний iGaming для продажи размещений.

Модель по мотивам Overtron Sales (TRX-CRM), урезана под наш мотив продаж:
одна компания = одна «сделка», поэтому стадия живёт прямо на компании,
без отдельных лидов и пайплайнов. Канал касаний — email/LinkedIn/Telegram.

Подключается в конце app.py:  from server import crm; app.include_router(crm.router)
"""
import json
import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer,
                        String, Text, func, or_)
from sqlalchemy.orm import Session

from server.app import (Base, CompanyProfile, Job, ROOT, db_session,
                        need_admin, render, slugify_company)

router = APIRouter()

# Стадии фиксированы кодом: их мало и на них завязана автологика.
STAGES = [
    ("new", "Новая"),
    ("contact", "Контакт найден"),
    ("to_notify", "Проинформировать"),   # пришёл отклик на вакансию компании — надо сообщить
    ("outreach", "В работе"),
    ("replied", "Ответила"),
    ("talks", "Переговоры"),
    ("client", "Клиент"),
    ("lost", "Отказ"),
]
STAGE_LABELS = dict(STAGES)
KINDS = [("operator", "Оператор"), ("provider", "Провайдер"), ("affiliate", "Аффилиат"),
         ("agency", "Агентство"), ("media", "Медиа"), ("other", "Другое")]
KIND_LABELS = dict(KINDS)
CHANNELS = [("email", "Email"), ("linkedin", "LinkedIn"), ("telegram", "Telegram"),
            ("call", "Звонок"), ("other", "Другое")]
CHANNEL_LABELS = dict(CHANNELS)


class CrmCompany(Base):
    __tablename__ = "crm_companies"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False)  # тот же слаг, что у Job.company_slug
    domain = Column(String, default="")
    website = Column(String, default="")
    careers_url = Column(String, default="")
    kind = Column(String, default="other")
    country = Column(String, default="")
    size = Column(String, default="")
    open_jobs = Column(Integer, default=0)    # вакансий на их карьерной странице (из краулера)
    jobs_here = Column(Integer, default=0)    # их вакансий у нас на борде
    stage = Column(String, default="new")
    lost_reason = Column(String, default="")
    icp_score = Column(Integer, default=0)
    icp_why = Column(String, default="")
    source = Column(String, default="manual")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class CrmContact(Base):
    __tablename__ = "crm_contacts"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("crm_companies.id"), nullable=False)
    name = Column(String, nullable=False)
    role_title = Column(String, default="")
    email = Column(String, default="")
    email_status = Column(String, default="unknown")  # unknown | valid | invalid | risky
    linkedin = Column(String, default="")
    telegram = Column(String, default="")
    lang = Column(String, default="ru")
    do_not_contact = Column(Boolean, default=False)
    dnc_reason = Column(String, default="")
    last_touch_at = Column(DateTime, nullable=True)
    last_reply_at = Column(DateTime, nullable=True)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class CrmTouch(Base):
    """Касание: письмо, сообщение, звонок. direction=in — ответ компании нам."""
    __tablename__ = "crm_touches"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("crm_companies.id"), nullable=False)
    contact_id = Column(Integer, ForeignKey("crm_contacts.id"), nullable=True)
    channel = Column(String, default="email")
    direction = Column(String, default="out")  # out | in
    subject = Column(String, default="")
    body = Column(Text, default="")
    status = Column(String, default="sent")    # sent | replied | bounced | failed
    happened_at = Column(DateTime, default=datetime.utcnow)


class CrmTask(Base):
    __tablename__ = "crm_tasks"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("crm_companies.id"), nullable=False)
    title = Column(String, nullable=False)
    due_at = Column(DateTime, nullable=True)
    done_at = Column(DateTime, nullable=True)
    result = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class CrmEvent(Base):
    """История карточки: смены стадий, импорт, заметки системы."""
    __tablename__ = "crm_events"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("crm_companies.id"), nullable=False)
    kind = Column(String, default="note")
    body = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


def log_event(db: Session, company_id: int, kind: str, body: str):
    db.add(CrmEvent(company_id=company_id, kind=kind, body=body))


def set_stage(db: Session, company: CrmCompany, stage: str, reason: str = ""):
    if stage not in STAGE_LABELS or stage == company.stage:
        return
    old = company.stage
    company.stage = stage
    company.updated_at = datetime.utcnow()
    if stage == "lost" and reason:
        company.lost_reason = reason
    log_event(db, company.id, "stage",
              f"{STAGE_LABELS.get(old, old)} → {STAGE_LABELS[stage]}"
              + (f" · {reason}" if reason else ""))


def icp(open_jobs: int, jobs_here: int, has_domain: bool) -> tuple[int, str]:
    """Скоринг «насколько компании нужен джоб-борд». Просто и объяснимо."""
    score, why = 30, []
    if open_jobs >= 100:
        score += 40; why.append(f"{open_jobs} открытых вакансий — массовый найм")
    elif open_jobs >= 30:
        score += 30; why.append(f"{open_jobs} открытых вакансий")
    elif open_jobs >= 10:
        score += 20; why.append(f"{open_jobs} вакансий")
    elif open_jobs >= 3:
        score += 10; why.append(f"{open_jobs} вакансии")
    if jobs_here:
        score += 20; why.append(f"{jobs_here} их вакансий уже у нас на борде")
    if has_domain:
        score += 10; why.append("есть карьерный домен")
    return min(score, 100), "; ".join(why)


def company_or_404(db: Session, cid: int) -> CrmCompany:
    company = db.get(CrmCompany, cid)
    if not company:
        raise HTTPException(404, "Компания не найдена")
    return company


# ---------- страницы ----------

@router.get("/admin/crm", response_class=HTMLResponse)
def crm_board(request: Request, db: Session = Depends(db_session)):
    need_admin(request, db)
    companies = db.query(CrmCompany).order_by(CrmCompany.icp_score.desc()).all()
    columns = [(code, label, [c for c in companies if c.stage == code]) for code, label in STAGES]
    now = datetime.utcnow()
    overdue = {t.company_id for t in db.query(CrmTask)
               .filter(CrmTask.done_at.is_(None), CrmTask.due_at < now)}
    week_ago = now.replace(hour=0, minute=0) - timedelta(days=7)
    stats = {
        "total": len(companies),
        "clients": sum(1 for c in companies if c.stage == "client"),
        "replied": sum(1 for c in companies if c.stage in ("replied", "talks")),
        "touches_7d": db.query(CrmTouch).filter(CrmTouch.happened_at >= week_ago).count(),
        "tasks_overdue": db.query(CrmTask).filter(CrmTask.done_at.is_(None), CrmTask.due_at < now).count(),
    }
    return render(request, db, "crm/board.html", columns=columns, stats=stats,
                  overdue=overdue, stages=STAGES, msg=request.query_params.get("msg"))


@router.get("/admin/crm/companies", response_class=HTMLResponse)
def crm_companies(request: Request, db: Session = Depends(db_session)):
    need_admin(request, db)
    q = (request.query_params.get("q") or "").strip()
    stage = request.query_params.get("stage") or ""
    kind = request.query_params.get("kind") or ""
    sort = request.query_params.get("sort") or "icp"
    query = db.query(CrmCompany)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(or_(func.lower(CrmCompany.name).like(like),
                                 func.lower(CrmCompany.domain).like(like),
                                 func.lower(CrmCompany.country).like(like)))
    if stage:
        query = query.filter(CrmCompany.stage == stage)
    if kind:
        query = query.filter(CrmCompany.kind == kind)
    order = {"icp": CrmCompany.icp_score.desc(), "jobs": CrmCompany.open_jobs.desc(),
             "updated": CrmCompany.updated_at.desc(), "name": func.lower(CrmCompany.name)}
    companies = query.order_by(order.get(sort, order["icp"])).all()
    return render(request, db, "crm/companies.html", companies=companies,
                  q=q, stage=stage, kind=kind, sort=sort,
                  stages=STAGES, kinds=KINDS, stage_labels=STAGE_LABELS,
                  kind_labels=KIND_LABELS, msg=request.query_params.get("msg"))


@router.get("/admin/crm/company/{cid}", response_class=HTMLResponse)
def crm_company(cid: int, request: Request, db: Session = Depends(db_session)):
    need_admin(request, db)
    company = company_or_404(db, cid)
    contacts = db.query(CrmContact).filter_by(company_id=cid).order_by(CrmContact.created_at).all()
    touches = (db.query(CrmTouch).filter_by(company_id=cid)
               .order_by(CrmTouch.happened_at.desc()).limit(50).all())
    tasks = (db.query(CrmTask).filter_by(company_id=cid)
             .order_by(CrmTask.done_at.isnot(None), CrmTask.due_at).all())
    events = (db.query(CrmEvent).filter_by(company_id=cid)
              .order_by(CrmEvent.created_at.desc()).limit(30).all())
    contact_names = {c.id: c.name for c in contacts}
    profile = db.query(CompanyProfile).filter_by(slug=company.slug).first()
    return render(request, db, "crm/company.html", c=company, contacts=contacts,
                  touches=touches, tasks=tasks, events=events, profile=profile,
                  contact_names=contact_names, now=datetime.utcnow(),
                  stages=STAGES, kinds=KINDS, channels=CHANNELS,
                  stage_labels=STAGE_LABELS, channel_labels=CHANNEL_LABELS,
                  msg=request.query_params.get("msg"))


@router.get("/admin/crm/tasks", response_class=HTMLResponse)
def crm_tasks(request: Request, db: Session = Depends(db_session)):
    need_admin(request, db)
    now = datetime.utcnow()
    open_tasks = (db.query(CrmTask).filter(CrmTask.done_at.is_(None))
                  .order_by(CrmTask.due_at.is_(None), CrmTask.due_at).all())
    names = {c.id: c.name for c in db.query(CrmCompany)
             .filter(CrmCompany.id.in_([t.company_id for t in open_tasks] or [0]))}
    return render(request, db, "crm/tasks.html", tasks=open_tasks, names=names, now=now,
                  msg=request.query_params.get("msg"))


# ---------- действия ----------

@router.post("/admin/crm/company/new")
def crm_company_new(request: Request, name: str = Form(...), kind: str = Form("other"),
                    country: str = Form(""), website: str = Form(""),
                    db: Session = Depends(db_session)):
    need_admin(request, db)
    slug = slugify_company(name)
    if db.query(CrmCompany).filter_by(slug=slug).first():
        return RedirectResponse("/admin/crm/companies?msg=Такая компания уже есть", status_code=303)
    company = CrmCompany(name=name.strip(), slug=slug, kind=kind, country=country.strip(),
                         website=website.strip(), source="manual")
    db.add(company)
    db.flush()
    log_event(db, company.id, "created", "Добавлена вручную")
    db.commit()
    return RedirectResponse(f"/admin/crm/company/{company.id}", status_code=303)


@router.post("/admin/crm/company/{cid}/update")
def crm_company_update(cid: int, request: Request, name: str = Form(...),
                       kind: str = Form("other"), country: str = Form(""),
                       website: str = Form(""), careers_url: str = Form(""),
                       stage: str = Form(""), lost_reason: str = Form(""),
                       notes: str = Form(""), db: Session = Depends(db_session)):
    need_admin(request, db)
    company = company_or_404(db, cid)
    company.name, company.kind = name.strip(), kind
    company.country, company.website = country.strip(), website.strip()
    company.careers_url, company.notes = careers_url.strip(), notes
    set_stage(db, company, stage, lost_reason.strip())
    company.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(f"/admin/crm/company/{cid}?msg=Сохранено", status_code=303)


@router.post("/admin/crm/company/{cid}/stage")
def crm_company_stage(cid: int, request: Request, stage: str = Form(...),
                      db: Session = Depends(db_session)):
    """Быстрая смена стадии с доски."""
    need_admin(request, db)
    company = company_or_404(db, cid)
    set_stage(db, company, stage)
    db.commit()
    return RedirectResponse("/admin/crm", status_code=303)


@router.post("/admin/crm/company/{cid}/contact/new")
def crm_contact_new(cid: int, request: Request, name: str = Form(...),
                    role_title: str = Form(""), email: str = Form(""),
                    linkedin: str = Form(""), telegram: str = Form(""),
                    db: Session = Depends(db_session)):
    need_admin(request, db)
    company = company_or_404(db, cid)
    db.add(CrmContact(company_id=cid, name=name.strip(), role_title=role_title.strip(),
                      email=email.strip().lower(), linkedin=linkedin.strip(),
                      telegram=telegram.strip().lstrip("@")))
    log_event(db, cid, "contact", f"Контакт: {name.strip()}" + (f" ({email.strip()})" if email.strip() else ""))
    # Первый контакт двигает компанию со стадии «Новая»
    if company.stage == "new":
        set_stage(db, company, "contact")
    db.commit()
    return RedirectResponse(f"/admin/crm/company/{cid}?msg=Контакт добавлен", status_code=303)


@router.post("/admin/crm/contact/{contact_id}/dnc")
def crm_contact_dnc(contact_id: int, request: Request, reason: str = Form(""),
                    db: Session = Depends(db_session)):
    need_admin(request, db)
    contact = db.get(CrmContact, contact_id)
    if not contact:
        raise HTTPException(404)
    contact.do_not_contact = not contact.do_not_contact
    contact.dnc_reason = reason.strip() if contact.do_not_contact else ""
    log_event(db, contact.company_id, "dnc",
              f"{contact.name}: {'не беспокоить' if contact.do_not_contact else 'снова можно писать'}")
    db.commit()
    return RedirectResponse(f"/admin/crm/company/{contact.company_id}", status_code=303)


@router.post("/admin/crm/company/{cid}/touch/new")
def crm_touch_new(cid: int, request: Request, channel: str = Form("email"),
                  direction: str = Form("out"), contact_id: str = Form(""),
                  subject: str = Form(""), body: str = Form(""),
                  db: Session = Depends(db_session)):
    need_admin(request, db)
    company = company_or_404(db, cid)
    contact = db.get(CrmContact, int(contact_id)) if contact_id.isdigit() else None
    now = datetime.utcnow()
    db.add(CrmTouch(company_id=cid, contact_id=contact.id if contact else None,
                    channel=channel, direction=direction,
                    subject=subject.strip(), body=body, happened_at=now,
                    status="replied" if direction == "in" else "sent"))
    # Автологика стадий: исходящее касание = «В работе», ответ = «Ответила»
    if direction == "out":
        if contact:
            contact.last_touch_at = now
        if company.stage in ("new", "contact"):
            set_stage(db, company, "outreach")
    else:
        if contact:
            contact.last_reply_at = now
        if company.stage in ("new", "contact", "outreach"):
            set_stage(db, company, "replied")
    db.commit()
    return RedirectResponse(f"/admin/crm/company/{cid}?msg=Касание записано", status_code=303)


@router.post("/admin/crm/company/{cid}/task/new")
def crm_task_new(cid: int, request: Request, title: str = Form(...),
                 due: str = Form(""), db: Session = Depends(db_session)):
    need_admin(request, db)
    company_or_404(db, cid)
    due_at = None
    if due:
        try:
            due_at = datetime.strptime(due, "%Y-%m-%d")
        except ValueError:
            pass
    db.add(CrmTask(company_id=cid, title=title.strip(), due_at=due_at))
    db.commit()
    return RedirectResponse(f"/admin/crm/company/{cid}?msg=Задача добавлена", status_code=303)


@router.post("/admin/crm/task/{task_id}/done")
def crm_task_done(task_id: int, request: Request, result: str = Form(""),
                  db: Session = Depends(db_session)):
    need_admin(request, db)
    task = db.get(CrmTask, task_id)
    if not task:
        raise HTTPException(404)
    task.done_at = datetime.utcnow()
    task.result = result.strip()
    log_event(db, task.company_id, "task", f"Сделано: {task.title}"
              + (f" — {task.result}" if task.result else ""))
    db.commit()
    back = request.headers.get("referer") or f"/admin/crm/company/{task.company_id}"
    return RedirectResponse(back, status_code=303)


@router.post("/admin/crm/import")
def crm_import(request: Request, db: Session = Depends(db_session)):
    """Импорт компаний из data/companies.json (краулер) + профилей с борда.

    Повторный запуск безопасен: обновляет счётчики и скоринг, не трогает
    стадии, заметки и контакты.
    """
    need_admin(request, db)
    path = os.path.join(ROOT, "data", "companies.json")
    try:
        rows = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        return RedirectResponse(f"/admin/crm?msg=Не прочитал companies.json: {str(e)[:80]}", status_code=303)

    # их вакансии у нас на борде — считаем одним запросом
    here = {}
    for name, cnt in (db.query(Job.company_name, func.count(Job.id))
                      .filter(Job.status == "approved").group_by(Job.company_name)):
        here[slugify_company(name)] = cnt

    added = updated = 0
    for row in rows or ():
        name = (row.get("name") or "").strip()
        slug = slugify_company(name)
        if not name or slug == "company" or name.lower() in ("компания не указана", "unknown", "n/a"):
            continue
        company = db.query(CrmCompany).filter_by(slug=slug).first()
        if not company:
            company = CrmCompany(name=name, slug=slug, source="crawler")
            db.add(company)
            db.flush()
            log_event(db, company.id, "created", "Импорт из краулера")
            added += 1
        else:
            updated += 1
        company.open_jobs = int(row.get("open_jobs") or 0)
        company.jobs_here = here.get(slug, 0)
        if row.get("domain"):
            company.domain = row["domain"]
        if row.get("career_url") and not company.careers_url:
            company.careers_url = row["career_url"]
        if not company.country and row.get("locations"):
            company.country = ", ".join(row["locations"][:3])
        profile = db.query(CompanyProfile).filter_by(slug=slug).first()
        if profile:
            company.website = company.website or profile.website
            company.size = company.size or profile.size
            company.careers_url = company.careers_url or profile.careers_url
        company.icp_score, company.icp_why = icp(company.open_jobs, company.jobs_here,
                                                 bool(company.domain))
        company.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(f"/admin/crm?msg=Импорт: добавлено {added}, обновлено {updated}",
                            status_code=303)


# ---------- отклики на чужие (агрегированные) вакансии ----------
# Таланты откликаются на сайте, ссылок на первоисточник нет. Каждый отклик на
# вакансию без владельца — лид: компанию надо найти, сообщить об отклике и
# предложить открыть контакт кандидата за деньги (обычные cv-открытия).

def ensure_company(db: Session, name: str) -> "CrmCompany | None":
    name = (name or "").strip()
    slug = slugify_company(name)
    if not name or slug == "company":
        return None
    company = db.query(CrmCompany).filter_by(slug=slug).first()
    if not company:
        company = CrmCompany(name=name, slug=slug, source="applications")
        db.add(company)
        db.flush()
        log_event(db, company.id, "created", "Появился отклик на вакансию компании")
    return company


def note_application(db: Session, job, user, application) -> None:
    """Каждый отклик заводит компанию в CRM и ставит её в очередь «Проинформировать». Не коммитит."""
    company = ensure_company(db, job.company_name)
    if not company:
        return
    company.updated_at = datetime.utcnow()
    log_event(db, company.id, "application",
              f"Отклик на «{job.title}» (вакансия #{job.id}) от кандидата #{user.id}")
    # пока компании не сообщили — она висит на этапе «Проинформировать»;
    # письмо или отметка «сообщили вручную» уводит её в «В работе» (crm_lead_notify)
    # у вакансии с владельцем работодатель видит отклик в своём кабинете — сообщать нечего
    if job.owner_id is None and company.stage in ("new", "contact"):
        set_stage(db, company, "to_notify", "")


def _lead_rows(db: Session):
    """Компании с откликами на их агрегированные вакансии, свежие сверху."""
    from server.app import Application, Resume, User, is_c_level, resume_card
    rows = (db.query(Application, Job, User)
            .join(Job, Job.id == Application.job_id)
            .join(User, User.id == Application.user_id)
            .filter(Job.owner_id.is_(None))
            .order_by(Application.created_at.desc()).all())
    resumes = {r.user_id: r for r in db.query(Resume).filter(
        Resume.user_id.in_({u.id for _, _, u in rows} or {0}))}
    groups: dict[str, dict] = {}
    for application, job, user in rows:
        slug = slugify_company(job.company_name)
        g = groups.get(slug)
        if not g:
            company = ensure_company(db, job.company_name)
            if not company:
                continue
            contact = (db.query(CrmContact).filter(CrmContact.company_id == company.id,
                                                   CrmContact.email != "", CrmContact.do_not_contact.is_(False))
                       .order_by(CrmContact.id).first())
            touch = (db.query(CrmTouch).filter(CrmTouch.company_id == company.id,
                                               CrmTouch.subject.like("Отклик%"), CrmTouch.direction == "out")
                     .order_by(CrmTouch.happened_at.desc()).first())
            g = groups[slug] = {"company": company, "contact": contact, "notified": touch,
                                "items": [], "new_since_notify": 0}
        resume = resumes.get(user.id)
        public = bool(resume and resume.published and resume.status == "approved")
        item = {"application": application, "job": job, "user": user, "resume": resume,
                "public": public, "card": resume_card(resume, user.name or "") if resume else {},
                "clevel": is_c_level(job.title) or is_c_level(resume.title if resume else "")}
        g["items"].append(item)
        if not g["notified"] or application.created_at > g["notified"].happened_at:
            g["new_since_notify"] += 1
    db.flush()
    return sorted(groups.values(), key=lambda g: g["items"][0]["application"].created_at, reverse=True)


def build_lead_letter(g: dict) -> tuple[str, str, str]:
    """(subject, text, html) — письмо компании об откликах: анонимные карточки кандидатов
    и вопрос, прислать ли полное резюме. По-английски: компании международные."""
    from server.app import CLEVEL_UNLOCK_COST, resume_card
    company = g["company"]
    items = g["items"]
    titles = sorted({it["job"].title for it in items})
    n = len(items)
    subject = (f"{n} candidate{'s' if n > 1 else ''} applied to your job "
               f"“{titles[0]}” on SpinHire" if len(titles) == 1 else
               f"{n} candidates applied to your {len(titles)} jobs on SpinHire")
    text_blocks, html_blocks = [], []
    for it in items[:8]:
        card = resume_card(it["resume"], (it["user"].name or "")) if it["resume"] else {}
        who = card.get("title") or "Candidate"
        code = card.get("code") or ""
        facts = " · ".join(card.get("facts") or [])
        skills = ", ".join(card.get("skills") or [])
        about = card.get("about") or ""
        link = f"https://spinhire.io/resume/{card['id']}" if card.get("public") else ""
        text_blocks.append("\n".join(x for x in [
            f"▸ {who}{f' ({code})' if code else ''} → applied to “{it['job'].title}”",
            f"  {facts}" if facts else "",
            f"  Skills: {skills}" if skills else "",
            f"  {about}" if about else "",
            f"  Anonymous profile: {link}" if link else "  Full profile available on request.",
        ] if x))
        html_blocks.append(
            f'<li style="margin-bottom:14px;"><b>{who}</b>{f" <span style=\'color:#888\'>({code})</span>" if code else ""}'
            f' → applied to “{it["job"].title}”'
            + (f'<br><span style="color:#555;">{facts}</span>' if facts else "")
            + (f'<br><span style="color:#555;">Skills: {skills}</span>' if skills else "")
            + (f'<br>{about}' if about else "")
            + (f'<br><a href="{link}">{link}</a>' if link else '<br><i>Full profile available on request.</i>')
            + "</li>")
    text_items = "\n\n".join(text_blocks)
    html_items = "".join(html_blocks)
    more = f"\n…and {n - 8} more." if n > 8 else ""
    text = f"""Hello {company.name} team,

Candidates on SpinHire — an iGaming job board with 6 000+ live jobs — applied to your posting{'s' if len(titles) > 1 else ''}.
Below is what they look like without personal data:

{text_items}{more}

Want the full CV of anyone above — work history, education and contacts? Just reply to this email and tell us who, we will send it over.
Or open contacts yourself (name, email, Telegram): €5 per contact, €4.5 in a pack of 10. C-level contacts cost {CLEVEL_UNLOCK_COST} credits.
Pricing: https://spinhire.io/post-job#pricing

Post your own jobs on SpinHire — the first 3 are free: https://spinhire.io/post-job

— SpinHire team, https://spinhire.io"""
    html = f"""<p>Hello {company.name} team,</p>
<p>Candidates on <a href="https://spinhire.io">SpinHire</a> — an iGaming job board with 6 000+ live jobs — applied to your posting{'s' if len(titles) > 1 else ''}.
Below is what they look like without personal data:</p>
<ul>{html_items}</ul>{('<p>…and %d more.</p>' % (n - 8)) if n > 8 else ''}
<p><b>Want the full CV of anyone above</b> — work history, education and contacts? Just reply to this email and tell us who, we will send it over.<br>
Or open contacts yourself (name, email, Telegram): <b>€5 per contact</b>, €4.5 in a pack of 10. C-level contacts cost {CLEVEL_UNLOCK_COST} credits.
<a href="https://spinhire.io/post-job#pricing">Pricing</a></p>
<p>Post your own jobs on SpinHire — the first 3 are free: <a href="https://spinhire.io/post-job">spinhire.io/post-job</a></p>
<p>— SpinHire team</p>"""
    return subject, text, html


@router.get("/admin/crm/leads", response_class=HTMLResponse)
def crm_leads(request: Request, db: Session = Depends(db_session)):
    need_admin(request, db)
    groups = _lead_rows(db)
    db.commit()
    for g in groups:
        g["subject"], g["text"], _ = build_lead_letter(g)
    return render(request, db, "crm/leads.html", groups=groups, channels=CHANNELS,
                  stage_labels=STAGE_LABELS, msg=request.query_params.get("msg"))


@router.post("/admin/crm/leads/{cid}/notify")
def crm_lead_notify(cid: int, request: Request, channel: str = Form("email"),
                    db: Session = Depends(db_session)):
    """Отправить письмо об откликах (email через Resend) или отметить, что сообщили вручную."""
    from server.app import resend_send
    need_admin(request, db)
    company = company_or_404(db, cid)
    g = next((g for g in _lead_rows(db) if g["company"].id == cid), None)
    if not g:
        return RedirectResponse("/admin/crm/leads?msg=У компании нет откликов", status_code=303)
    subject, text, html = build_lead_letter(g)
    contact = g["contact"]
    status = "sent"
    if channel == "email":
        if not contact:
            return RedirectResponse("/admin/crm/leads?msg=Нет контакта с email — добавьте его в карточке компании",
                                    status_code=303)
        if not resend_send(contact.email, subject, html):
            status = "failed"
    db.add(CrmTouch(company_id=company.id, contact_id=contact.id if contact else None,
                    channel=channel if channel in CHANNEL_LABELS else "other", direction="out",
                    subject=f"Отклик: {subject}", body=text, status=status))
    if contact:
        contact.last_touch_at = datetime.utcnow()
    if company.stage in ("new", "contact", "to_notify"):
        set_stage(db, company, "outreach")
    log_event(db, company.id, "touch",
              f"Сообщили об откликах ({CHANNEL_LABELS.get(channel, channel)}): {status}")
    db.commit()
    msg = ("Письмо отправлено" if status == "sent" and channel == "email"
           else "Не удалось отправить письмо (Resend)" if status == "failed"
           else "Отмечено: сообщили " + CHANNEL_LABELS.get(channel, channel))
    return RedirectResponse(f"/admin/crm/leads?msg={msg}", status_code=303)
