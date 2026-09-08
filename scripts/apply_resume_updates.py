#!/usr/bin/env python3
"""Применяет структурированные поля CV к базе и публикует готовые анонимные профили.

Запуск НА ПРОДЕ из /opt/spinhire:  ./venv/bin/python3 scripts/apply_resume_updates.py /tmp/resume_updates.json [--dry]

Правило публикации: есть должность, «о себе» длиннее 200 символов и навыки — публикуем,
даже если модель сомневалась в датах. Пустые или нечитаемые CV остаются на модерации с
заметкой для соискателя. Контактные поля не трогаем: их открывает работодатель.
"""
import json
import re
import sqlite3
import sys
from datetime import datetime

DB = "data/spinhire.db"
FIELDS = ("title", "location", "experience_years", "skills", "about", "languages",
          "employment_history", "education", "desired_format", "preferred_locations", "relocation")
PII = re.compile(r"(\+?\d[\d\s().-]{8,}\d)|([\w.+-]+@[\w-]+\.[\w.]+)|(https?://\S+)", re.I)


def clean(v, joiner=", "):
    if isinstance(v, list):
        v = joiner.join(str(x) for x in v if x)
    if isinstance(v, dict):
        v = "\n".join(f"{k}: {val}" for k, val in v.items())
    if isinstance(v, str):
        return PII.sub("", v).strip()
    return v


def main():
    updates = json.load(open(sys.argv[1], encoding="utf-8"))
    dry = "--dry" in sys.argv
    c = sqlite3.connect(DB, timeout=60)
    c.row_factory = sqlite3.Row
    now = datetime.utcnow().isoformat(sep=" ")
    published, held = [], []
    for rid, u in updates.items():
        row = c.execute("select * from resumes where id=?", (rid,)).fetchone()
        if not row or row["status"] != "pending":
            continue
        title, about, skills = clean(u.get("title") or ""), clean(u.get("about") or ""), clean(u.get("skills") or "")
        ok = bool(title) and len(about) >= 200 and bool(skills)
        if not ok:
            note = u.get("reason") or "Загрузите читаемый PDF или заполните должность, навыки и «о себе» вручную."
            held.append((rid, note))
            if not dry:
                c.execute("update resumes set moderation_note=?, updated_at=? where id=?", (note, now, rid))
            continue
        values = {}
        for f in FIELDS:
            v = u.get(f)
            if v is None or v == "":
                continue
            if f == "experience_years":
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    continue
            elif f == "relocation":
                v = 1 if v in (True, "true", "True", 1) else 0
            elif f == "desired_format" and v not in ("удалёнка", "гибрид", "офис"):
                continue
            else:
                v = clean(v, "\n" if f in ("employment_history", "education") else ", ")
            values[f] = v
        values.update(title=title, about=about, skills=skills)
        published.append((rid, title))
        if dry:
            continue
        sets = ", ".join(f"{k}=?" for k in values)
        c.execute(f"update resumes set {sets}, status='approved', published=1, moderation_note='', "
                  f"submitted_at=coalesce(submitted_at, ?), updated_at=? where id=?",
                  (*values.values(), now, now, rid))
        c.execute("insert into notifications (user_id, kind, title, body, link, read_at, created_at) "
                  "values (?, 'resume', 'CV опубликован', "
                  "'Мы структурировали ваше CV в анонимный профиль и опубликовали его в базе работодателей. "
                  "Проверьте текст в личном кабинете и поправьте, если что-то не так.', ?, '', ?)",
                  (row["user_id"], f"/resume/{rid}", now))
    if not dry:
        c.commit()
    print(f"{'DRY ' if dry else ''}published {len(published)}, held {len(held)}")
    for rid, t in published:
        print("  +", rid, t)
    for rid, note in held:
        print("  -", rid, note)


if __name__ == "__main__":
    main()
