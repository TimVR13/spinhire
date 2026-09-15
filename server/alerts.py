# -*- coding: utf-8 -*-
"""Письма о вакансиях под резюме: раз в неделю, по понедельникам, подборка за неделю.

Матчинг тот же, что кандидат видит на странице вакансии (match_score), поэтому в
письме стоит та же цифра «совпадение N%», что и на сайте. Окно отправки — понедельник
с 9 до 20 по местному времени сайта (SPINHIRE_ALERTS_WEEKDAY/FROM/TO, SPINHIRE_TG_TZ_OFFSET);
внутри окна проход раз в час, но каждому человеку не чаще раза в 6 дней
(SPINHIRE_ALERTS_GAP_HOURS), только новое за 7 дней (SPINHIRE_ALERTS_LOOKBACK_DAYS; JobAlertSent
помнит, что уже уходило), только подтверждённым и не поставившим поиск на паузу.
Решение владельца 15.09.2026: вместо писем каждые три дня — одна подборка в понедельник.
Отписка — по подписанной ссылке из письма, без входа.

Подключается в конце app.py:
    from server import alerts; app.include_router(alerts.router); alerts.start_scheduler()
"""
import html
import os
import threading
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import Column, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Session

from server.app import (Application, Base, Job, PATH_LANGS, ROOT, Resume, SECRET, SessionLocal, User,
                        add_notification, db_session, match_score, resend_send, resume_is_ready,
                        track, user_lang)
from server.mail_i18n import mail_t

router = APIRouter()

SITE = "https://spinhire.io"
MIN_SCORE = int(os.environ.get("SPINHIRE_ALERTS_MIN_SCORE", "60"))   # порог «стоит написать»
MAX_JOBS = 5
MIN_GAP_HOURS = int(os.environ.get("SPINHIRE_ALERTS_GAP_HOURS", "144"))   # раз в неделю: 6 дней с запасом
LOOKBACK_DAYS = int(os.environ.get("SPINHIRE_ALERTS_LOOKBACK_DAYS", "7"))   # подборка за неделю
# Окно отправки: день недели (0 = понедельник) и часы по местному времени сайта.
SEND_WEEKDAY = int(os.environ.get("SPINHIRE_ALERTS_WEEKDAY", "0"))
SEND_FROM = int(os.environ.get("SPINHIRE_ALERTS_FROM", "9"))
SEND_TO = int(os.environ.get("SPINHIRE_ALERTS_TO", "20"))
TZ_OFFSET = int(os.environ.get("SPINHIRE_TG_TZ_OFFSET", "3"))   # тот же сдвиг, что у ботов
CHECK_SECONDS = int(os.environ.get("SPINHIRE_ALERTS_CHECK_SECONDS", "3600"))
# Когда был последний проход — переживает рестарт. Без метки каждый рестарт деплоя (их до
# десятка в день) через 3 минуты запускал полный перебор резюме × вакансий.
_STAMP = os.path.join(ROOT, "data", "alerts_last_pass")

# Отдельный подписант: токен отписки не должен годиться в качестве сессионной куки.
_unsub = URLSafeSerializer(SECRET, salt="alerts-unsubscribe")


class JobAlertSent(Base):
    """Какие вакансии уже уходили пользователю — чтобы не слать одно и то же дважды."""
    __tablename__ = "job_alert_sent"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)


def in_send_window(now: datetime = None) -> bool:
    """Понедельник, рабочие часы по местному времени сайта — только тогда шлём."""
    local = (now or datetime.utcnow()) + timedelta(hours=TZ_OFFSET)
    return local.weekday() == SEND_WEEKDAY and SEND_FROM <= local.hour < SEND_TO


def _lang_prefix(lang: str) -> str:
    return f"/{lang}" if lang in PATH_LANGS else ""


def _job_url(job, lang: str) -> str:
    return f"{SITE}{_lang_prefix(lang)}/job/{job.id}?utm_source=alerts&utm_medium=email&utm_campaign=cv_match"


def unsubscribe_token(user) -> str:
    return _unsub.dumps({"uid": user.id})


def fresh_jobs(db: Session, now: datetime = None) -> list:
    """Одобренные вакансии за окно рассылки — одна выборка на проход, а не на каждого подписчика."""
    since = (now or datetime.utcnow()) - timedelta(days=LOOKBACK_DAYS)
    return db.query(Job).filter(Job.status == "approved", Job.created_at >= since).order_by(Job.id).all()


def pick_jobs(db: Session, user, cv, jobs: list = None) -> list:
    """[(percent, job)] — новые подходящие вакансии, лучшие первыми, не больше MAX_JOBS."""
    if jobs is None:
        jobs = fresh_jobs(db)
    already = {jid for (jid,) in db.query(JobAlertSent.job_id).filter_by(user_id=user.id)}
    applied = {jid for (jid,) in db.query(Application.job_id).filter_by(user_id=user.id)}
    scored = []
    for job in jobs:
        if job.id in already or job.id in applied:
            continue
        match = match_score(cv, job)
        if match and match["percent"] >= MIN_SCORE:
            scored.append((match["percent"], job))
    scored.sort(key=lambda pair: (-pair[0], -pair[1].id))
    return scored[:MAX_JOBS]


def mail_html(user, lang: str, picks: list) -> str:
    rows = []
    for percent, job in picks:
        meta = " · ".join(part for part in (job.company_name, job.location or job.fmt) if part)
        salary = (f'<div style="color:#0a7a5c;font-weight:600;margin-top:4px">{html.escape(job.salary)}</div>'
                  if job.has_salary else "")
        rows.append(
            '<tr><td style="padding:14px 0;border-bottom:1px solid #eee">'
            f'<a href="{_job_url(job, lang)}" style="font-size:16px;font-weight:700;color:#111;text-decoration:none">'
            f'{html.escape(job.title)}</a>'
            f'<div style="color:#666;font-size:13px;margin-top:4px">{html.escape(meta)}</div>{salary}'
            f'<div style="font-size:12px;color:#0a7a5c;margin-top:6px">{mail_t(lang, "alerts_match", p=percent)}</div>'
            '</td></tr>')
    all_jobs = f"{SITE}{_lang_prefix(lang)}/jobs?utm_source=alerts&utm_medium=email&utm_campaign=cv_match"
    unsub = f"{SITE}/alerts/unsubscribe?t={unsubscribe_token(user)}"
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;color:#111;max-width:560px">'
        f'<p>{mail_t(lang, "alerts_intro")}</p>'
        f'<table style="width:100%;border-collapse:collapse">{"".join(rows)}</table>'
        f'<p style="margin-top:20px"><a href="{all_jobs}" style="display:inline-block;padding:10px 18px;'
        f'background:#111;color:#fff;border-radius:8px;text-decoration:none;font-weight:700">'
        f'{mail_t(lang, "alerts_open_all")}</a></p>'
        f'<p style="color:#888;font-size:12px;margin-top:28px">{mail_t(lang, "alerts_why")} '
        f'<a href="{unsub}" style="color:#888">{mail_t(lang, "alerts_unsub")}</a></p>'
        '</div>')


def send_job_alerts(db: Session, now: datetime = None) -> int:
    """Один проход по всем подписанным. Возвращает число отправленных писем."""
    now = now or datetime.utcnow()
    gap = (now - timedelta(hours=MIN_GAP_HOURS)).isoformat()
    # commit() по умолчанию сбрасывает загруженные объекты, и общий список вакансий пришлось бы
    # перечитывать по одной строке после каждого письма — держим его в памяти весь проход
    db.expire_on_commit = False
    jobs = fresh_jobs(db, now)
    users = (db.query(User)
             .filter(User.role == "talent", User.alerts_enabled == True,  # noqa: E712
                     User.verified == 1, User.job_search_status != "paused").all())
    sent = 0
    for user in users:
        if user.alerts_last_sent and user.alerts_last_sent > gap:
            continue
        cv = db.query(Resume).filter_by(user_id=user.id).first()
        if not resume_is_ready(cv):
            continue
        picks = pick_jobs(db, user, cv, jobs)
        time.sleep(0.01)   # отдать GIL веб-потокам, если крутимся с ними в одном процессе
        if not picks:
            continue
        lang = user_lang(user)
        subject = mail_t(lang, "alerts_subject", n=len(picks))
        if not resend_send(user.email, subject, mail_html(user, lang, picks)):
            continue   # почта не ушла — не помечаем, попробуем в следующий час
        for _, job in picks:
            db.add(JobAlertSent(user_id=user.id, job_id=job.id))
        user.alerts_last_sent = now.isoformat()
        add_notification(db, user.id, "alerts", subject,
                         " · ".join(job.title for _, job in picks)[:300], "/jobs")
        track(db, "alert_sent", user.id, "user", user.id, jobs=len(picks))
        db.commit()
        sent += 1
    return sent


@router.get("/alerts/unsubscribe", response_class=HTMLResponse)
def unsubscribe(t: str = Query(""), db: Session = Depends(db_session)):
    try:
        data = _unsub.loads(t)
    except BadSignature:
        raise HTTPException(404)
    user = db.get(User, data.get("uid"))
    if not user:
        raise HTTPException(404)
    user.alerts_enabled = False
    db.commit()
    lang = user_lang(user)
    return HTMLResponse(
        '<!doctype html><html><head><meta charset="utf-8"><title>SpinHire</title></head>'
        '<body style="font-family:Arial,Helvetica,sans-serif;color:#111;padding:48px 24px;max-width:560px">'
        f'<p>{mail_t(lang, "alerts_unsub_done")}</p>'
        f'<p><a href="{SITE}/profile">{mail_t(lang, "open_cabinet")}</a></p></body></html>')


def start_scheduler() -> None:
    if os.environ.get("SPINHIRE_ALERTS_ENABLED", "1").lower() in ("0", "false", "no"):
        print("[alerts] выключено: SPINHIRE_ALERTS_ENABLED=0")
        return

    def last_pass() -> float:
        try:
            with open(_STAMP) as fh:
                return float(fh.read().strip() or 0)
        except (OSError, ValueError):
            return 0.0

    def mark_pass() -> None:
        try:
            os.makedirs(os.path.dirname(_STAMP), exist_ok=True)
            with open(_STAMP, "w") as fh:
                fh.write(f"{time.time():.0f}")
        except OSError:
            pass

    def loop():
        # не мешать старту, и не раньше чем через CHECK_SECONDS после прошлого прохода
        time.sleep(max(180.0, last_pass() + CHECK_SECONDS - time.time()))
        while True:
            if not in_send_window():
                time.sleep(CHECK_SECONDS)
                continue
            started = time.time()
            try:
                with SessionLocal() as db:
                    count = send_job_alerts(db)
                if count:
                    print(f"[alerts] отправлено подборок: {count} за {time.time() - started:.0f} с")
            except Exception as e:
                print(f"[alerts] сбой: {type(e).__name__}: {str(e)[:160]}")
            mark_pass()
            time.sleep(CHECK_SECONDS)

    threading.Thread(target=loop, name="job-alerts", daemon=True).start()
    print(f"[alerts] подборка раз в неделю: день {SEND_WEEKDAY} (0=пн), {SEND_FROM}:00–{SEND_TO}:00 (+{TZ_OFFSET}), "
          f"окно вакансий {LOOKBACK_DAYS} дн., пауза {MIN_GAP_HOURS} ч")
