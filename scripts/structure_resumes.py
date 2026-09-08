#!/usr/bin/env python3
"""Структурирует загруженные CV в поля анонимного профиля через Gemini (Vertex).

Вход:  pending_resumes.json (поля из БД) + cv_texts.json (текст PDF) — оба из scratchpad.
Выход: resume_updates.json — {id: {поля…, "verdict": "publish|hold", "reason": "…"}}

    python3 scripts/structure_resumes.py <pending.json> <texts.json> <out.json>

Правило анонимности: в публичных полях не должно быть имени, телефона, почты,
ссылок на соцсети и точного адреса — контакт открывает работодатель за SpinCoins.
"""
import json
import re
import sys
import time

import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request

SA = "/Users/afin/Desktop/planner/.data/vertex-sa.json"
PROJECT, LOCATION, MODEL = "skillproof-502320", "global", "gemini-2.5-flash"

PROMPT = """Today is 8 September 2026: dates in 2024, 2025 and 2026 are the past or the present, never the future.
You structure a candidate's CV into an ANONYMOUS public profile for SpinHire, an iGaming job board.
Return ONLY a JSON object with these keys:
- title: concise role headline in English (e.g. "Customer Support Team Lead", "Python Backend Developer"); if the person targets iGaming support/VIP/KYC/etc., reflect it.
- location: city, country (English), or "" if unknown.
- experience_years: integer, total relevant experience.
- skills: comma-separated list, 8–20 items, most relevant first (tools, domains, languages of programming). No soft-skill fluff.
- about: 400–900 characters, third person, no name, no contacts, no employer-identifying personal data beyond company names; what the person does, strongest results with numbers, industries (mark iGaming/betting/casino experience explicitly if present), what role they look for.
- languages: comma-separated, with level if known (e.g. "English C1, Russian native").
- employment_history: 3–8 lines, each "Role — Company — years: 1–2 key facts". Newest first. No personal data.
- education: 1–3 lines or "".
- desired_format: one of "удалёнка", "гибрид", "офис" (remote/hybrid/office; default "удалёнка" if unclear).
- preferred_locations: comma-separated countries/cities the person is open to, or "".
- relocation: true/false.
- igaming_experience: true/false — has the person worked in online casino / betting / gambling / affiliates for that industry.
- quality: "publish" if the CV text gives enough to fill title, skills and about credibly; otherwise "hold".
- reason: one short sentence (in Russian) why hold, or "" if publish.
Never include phone numbers, emails, URLs, or the person's name anywhere in the values. Keep the person's original language of skills but write about/history in English (if the CV is Russian/Ukrainian, still write English).

Existing profile fields the candidate typed themselves (may be empty or placeholder):
{fields}

CV text:
{cv}
"""


def token() -> str:
    creds = service_account.Credentials.from_service_account_file(
        SA, scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    return creds.token


def ask(prompt: str) -> dict:
    url = (f"https://aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/{LOCATION}"
           f"/publishers/google/models/{MODEL}:generateContent")
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096,
                                 "responseMimeType": "application/json"}}
    for attempt in range(5):
        r = requests.post(url, headers={"Authorization": "Bearer " + token()}, json=body, timeout=120)
        if r.status_code == 429:
            time.sleep(15 * (attempt + 1))   # квота Vertex на минуту — ждём и повторяем
            continue
        r.raise_for_status()
        break
    r.raise_for_status()
    cand = (r.json().get("candidates") or [{}])[0]
    parts = cand.get("content", {}).get("parts")
    if not parts:
        raise ValueError(f"empty answer: {cand.get('finishReason')}")
    text = "".join(p.get("text", "") for p in parts)
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(text, strict=False)   # strict=False: переводы строк внутри значений
    except json.JSONDecodeError:
        # модель иногда обрывает вывод — берём всё до последнего закрытого поля
        cut = text[:text.rfind('",')] + '"}' if '",' in text else text
        return json.loads(cut, strict=False)


PII_RE = re.compile(r"(\+?\d[\d\s().-]{8,}\d)|([\w.+-]+@[\w-]+\.[\w.]+)|(https?://\S+|www\.\S+|linkedin\.com/\S+|t\.me/\S+)", re.I)


def scrub(value):
    if isinstance(value, str):
        return PII_RE.sub("", value).strip()
    return value


def main():
    pending = {r["id"]: r for r in json.load(open(sys.argv[1], encoding="utf-8"))}
    texts = json.load(open(sys.argv[2], encoding="utf-8"))
    out_path = sys.argv[3]
    try:
        out = json.load(open(out_path, encoding="utf-8"))
    except (OSError, ValueError):
        out = {}
    for rid, row in pending.items():
        if str(rid) in out:
            continue
        cv = (texts.get(str(rid)) or {}).get("text", "") or ""
        fields = {k: row.get(k) for k in ("title", "location", "experience_years", "skills", "about",
                                           "languages", "employment_history", "education",
                                           "salary_expect", "desired_format", "preferred_locations")}
        if len(cv) < 300 and len((row.get("about") or "")) < 200:
            out[str(rid)] = {"quality": "hold", "reason": "Файл CV не читается и профиль пустой", "cv_chars": len(cv)}
            print(rid, "hold (no text)")
            continue
        try:
            res = ask(PROMPT.format(fields=json.dumps(fields, ensure_ascii=False), cv=cv[:11000]))
            res = {k: scrub(v) for k, v in res.items()}
            res["cv_chars"] = len(cv)
            if res.get("quality") not in ("publish", "hold"):
                res["quality"] = "publish" if (res.get("title") and len(res.get("about") or "") > 200) else "hold"
            out[str(rid)] = res
            print(rid, res.get("quality"), "|", res.get("title"), "|", res.get("location"), "|", res.get("reason", ""))
        except Exception as exc:  # noqa: BLE001
            print(rid, "ERROR", str(exc)[:160])
        json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        time.sleep(4)


if __name__ == "__main__":
    main()
