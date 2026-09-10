"""API модерации резюме для облачной routine (без SSH): выгрузить кандидатов, применить структурированные профили.

  GET  /api/moderation/resumes/todo   → [{id, title, …, cv_text}]   заголовок X-Publish-Key
  POST /api/moderation/resumes/apply  {"<id>": {...}}  → {published, held}
  GET  /api/moderation/jobs/todo      → [{id, title, description, …}]  вакансии в очереди
  POST /api/moderation/jobs/apply     {"<id>": {"action": "approve|reject|skip", …}}
Правила и формат объекта — как у плановой задачи spinhire-cv-moderation (scripts/apply_resume_updates.py).
"""
import os
import re
import sys
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import Session

from server.app import CV_UPLOAD_DIR, DB_PATH, ROOT, Job, Resume, db_session

sys.path.insert(0, os.path.join(ROOT, "scripts"))
from apply_resume_updates import apply_updates  # noqa: E402

router = APIRouter()
PUBLISH_KEY = os.environ.get("SPINHIRE_PUBLISH_KEY", "")
MAX_TEXT = 11000


def _auth(key: str):
    if not PUBLISH_KEY or key != PUBLISH_KEY:
        raise HTTPException(403, "bad key")


def cv_text(path: str) -> str:
    if not path:
        return ""
    full = path if os.path.isabs(path) else os.path.join(CV_UPLOAD_DIR, os.path.basename(path))
    if not os.path.exists(full):
        full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return ""
    ext = full.lower().rsplit(".", 1)[-1]
    try:
        if ext == "pdf":
            from pypdf import PdfReader
            r = PdfReader(full)
            return "\n".join((pg.extract_text() or "") for pg in r.pages[:6])[:MAX_TEXT]
        if ext == "docx":
            with zipfile.ZipFile(full) as z:
                xml = z.read("word/document.xml").decode("utf8", "ignore")
            return re.sub(r"<[^>]+>", " ", xml)[:MAX_TEXT]
        return open(full, "rb").read().decode("utf8", "ignore")[:MAX_TEXT]
    except Exception as e:  # битый файл — пусть агент решит по полям
        return f"[не удалось прочитать файл: {e}]"


@router.get("/api/moderation/resumes/todo")
def resumes_todo(request: Request, x_publish_key: str = Header(default=""), db: Session = Depends(db_session)):
    _auth(x_publish_key)
    rows = (db.query(Resume).filter(or_(Resume.status == "pending", Resume.moderation_note.like("auto:%"),
                                        Resume.title == "Резюме на обработке",
                                        and_(Resume.status == "approved", func.length(Resume.about) < 80)))
            .order_by(Resume.updated_at.desc()).limit(40).all())
    out = []
    for r in rows:
        out.append({k: getattr(r, k) for k in ("id", "title", "location", "experience_years", "skills", "about", "languages",
                                                "employment_history", "education", "salary_expect", "desired_format",
                                                "preferred_locations", "cv_file_name", "cv_file_path", "status", "moderation_note")}
                   | {"cv_text": cv_text(r.cv_file_path)})
    return JSONResponse(out)


@router.post("/api/moderation/resumes/apply")
async def resumes_apply(request: Request, x_publish_key: str = Header(default=""), db: Session = Depends(db_session)):
    _auth(x_publish_key)
    updates = await request.json()
    if not isinstance(updates, dict):
        raise HTTPException(400, "ожидается {\"<id>\": {...}}")
    force = request.query_params.get("force", "1") == "1"
    published, held = apply_updates({str(k): v for k, v in updates.items()}, DB_PATH, dry=False, force=force)
    # снять маркер auto: у опубликованных
    ids = [int(rid) for rid, _ in published]
    if ids:
        for r in db.query(Resume).filter(Resume.id.in_(ids)).all():
            if (r.moderation_note or "").startswith("auto:"):
                r.moderation_note = ""
        db.commit()
    return JSONResponse({"published": published, "held": held, "at": datetime.utcnow().isoformat()})


# ---------- вакансии: ежечасная проверка и публикация ----------
JOB_FIELDS = ("title", "company_name", "category", "location", "fmt", "salary",
              "tags", "description", "source", "source_url", "posted_at", "status")
EDITABLE = ("title", "company_name", "category", "location", "fmt", "salary", "tags", "description")


@router.get("/api/moderation/jobs/todo")
def jobs_todo(request: Request, x_publish_key: str = Header(default=""),
              db: Session = Depends(db_session)):
    """Очередь: всё, что ждёт решения (pending). limit по умолчанию 60."""
    _auth(x_publish_key)
    try:
        limit = max(1, min(200, int(request.query_params.get("limit", "60"))))
    except ValueError:
        limit = 60
    rows = (db.query(Job).filter(Job.status == "pending")
            .order_by(Job.created_at.desc()).limit(limit).all())
    out = []
    for j in rows:
        item = {k: getattr(j, k) for k in JOB_FIELDS}
        item["id"] = j.id
        item["owner_id"] = j.owner_id            # есть владелец → вакансию разместил работодатель
        item["created_at"] = j.created_at.isoformat() if j.created_at else ""
        item["description"] = (item["description"] or "")[:MAX_TEXT]
        out.append(item)
    return JSONResponse({"total_pending": db.query(Job).filter(Job.status == "pending").count(),
                         "jobs": out})


@router.post("/api/moderation/jobs/apply")
async def jobs_apply(request: Request, x_publish_key: str = Header(default=""),
                     db: Session = Depends(db_session)):
    """{"<id>": {"action": "approve|reject|skip", "reason": "…", "fields": {"title": …}}}"""
    _auth(x_publish_key)
    updates = await request.json()
    if not isinstance(updates, dict):
        raise HTTPException(400, "ожидается {\"<id>\": {...}}")
    from server import crawler
    approved, rejected, edited, skipped, missing = [], [], [], [], []
    # вайтлист компаний считаем один раз и только если что-то одобряют
    known = None
    for raw_id, payload in updates.items():
        try:
            job = db.get(Job, int(raw_id))
        except (TypeError, ValueError):
            job = None
        if not job:
            missing.append(raw_id)
            continue
        payload = payload if isinstance(payload, dict) else {"action": str(payload)}
        fields = payload.get("fields") or {}
        changed = [k for k, v in fields.items()
                   if k in EDITABLE and isinstance(v, str) and v.strip() and getattr(job, k) != v.strip()]
        for k in changed:
            setattr(job, k, fields[k].strip())
        if changed:
            edited.append({"id": job.id, "fields": changed})
        action = (payload.get("action") or "skip").lower()
        if action == "approve":
            # борд про iGaming: одобрение модератора не отменяет фильтр
            # релевантности, иначе логистика и аутсорс висят до следующего
            # прохода краулера
            if known is None:
                known = crawler.known_igaming_companies(db, Job)
            offtopic = (crawler.job_is_irrelevant(job.title)
                        or crawler.company_is_offtopic(job.company_name, job.title,
                                                       job.description or "")
                        or crawler.generic_job_offtopic(job.source, job.title, job.company_name,
                                                        job.description or "", known))
            if offtopic:
                job.status = "rejected"
                job.closed_at = datetime.utcnow().date().isoformat()
                rejected.append({"id": job.id, "reason": "не про iGaming"})
            else:
                job.status = "approved"
                approved.append(job.id)
        elif action == "reject":
            job.status = "rejected"
            job.closed_at = datetime.utcnow().date().isoformat()
            rejected.append({"id": job.id, "reason": payload.get("reason", "")})
        else:
            skipped.append(job.id)
    db.commit()
    return JSONResponse({"approved": approved, "rejected": rejected, "edited": edited,
                         "skipped": skipped, "missing": missing,
                         "left_pending": db.query(Job).filter(Job.status == "pending").count(),
                         "at": datetime.utcnow().isoformat()})
