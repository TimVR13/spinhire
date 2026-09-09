"""API модерации резюме для облачной routine (без SSH): выгрузить кандидатов, применить структурированные профили.

  GET  /api/moderation/resumes/todo   → [{id, title, …, cv_text}]   заголовок X-Publish-Key
  POST /api/moderation/resumes/apply  {"<id>": {...}}  → {published, held}
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

from server.app import CV_UPLOAD_DIR, DB_PATH, ROOT, Resume, db_session

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
