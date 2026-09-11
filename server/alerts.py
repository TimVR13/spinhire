# -*- coding: utf-8 -*-
"""Письма о вакансиях под резюме: раз в день подборка того, что появилось и подходит.

Матчинг тот же, что кандидат видит на странице вакансии (match_score), поэтому в
письме стоит та же цифра «совпадение N%», что и на сайте. Шлём не чаще раза в
сутки на человека, только новое (JobAlertSent помнит, что уже уходило), только
подтверждённым и не поставившим поиск на паузу. Отписка — по подписанной ссылке
из письма, без входа.

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

from server.app import (Application, Base, Job, PATH_LANGS, Resume, SECRET, SessionLocal, User,
                        add_notification, db_session, match_score, resend_send, resume_is_ready,
                        track, user_lang)
from server.mail_i18n import mail_t

router = APIRouter()

SITE = "https://spinhire.io"
MIN_SCORE = int(os.environ.get("SPINHIRE_ALERTS_MIN_SCORE", "60"))   # порог «стоит написать»
MAX_JOBS = 5
LOOKBACK_DAYS = 3        # краулер ходит раз в 6 часов; трое суток — с запасом на пропуски
MIN_GAP_HOURS = 20       # «раз в день» с запасом на дрейф часа запуска
CHECK_SECONDS = 3600

# Отдельный подписант: токен отписки не должен годиться в качестве сессионной куки.
_unsub = URLSafeSerializer(SECRET, salt="alerts-unsubscribe")


class JobAlertSent(Base):
    """Какие вакансии уже уходили пользователю — чтобы не слать одно и то же дважды."""
    __tablename__ = "job_alert_sent"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)


def _lang_prefix(lang: str) -> str:
    return f"/{lang}" if lang in PATH_LANGS else ""


def _job_url(job, lang: str) -> str:
    return f"{SITE}{_lang_prefix(lang)}/job/{job.id}?utm_source=alerts&utm_medium=email&utm_campaign=cv_match"


def unsubscribe_token(user) -> str:
    return _unsub.dumps({"uid": user.id})


def pick_jobs(db: Session, user, cv) -> list:
    """[(percent, job)] — новые подходящие вакансии, лучшие первыми, не больше MAX_JOBS."""
    since = datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)
    already = {jid for (jid,) in db.query(JobAlertSent.job_id).filter_by(user_id=user.id)}
    applied = {jid for (jid,) in db.query(Application.job_id).filter_by(user_id=user.id)}
    scored = []
    for job in db.query(Job).filter(Job.status == "approved", Job.created_at >= since):
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
        picks = pick_jobs(db, user, cv)
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

    def loop():
        time.sleep(180)   # не мешать старту и первому краулу
        while True:
            try:
                with SessionLocal() as db:
                    count = send_job_alerts(db)
                if count:
                    print(f"[alerts] отправлено подборок: {count}")
            except Exception as e:
                print(f"[alerts] сбой: {type(e).__name__}: {str(e)[:160]}")
            time.sleep(CHECK_SECONDS)

    threading.Thread(target=loop, name="job-alerts", daemon=True).start()
