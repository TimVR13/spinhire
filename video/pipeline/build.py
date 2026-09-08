"""Сборка спецификации ролика: данные → сцены + фразы → озвучка → props для Remotion.

  python3 pipeline/build.py hot_jobs 2026-09-09-morning
  python3 pipeline/build.py salary   2026-09-09-day   --slug affiliate-manager
  python3 pipeline/build.py profession 2026-09-09-evening --slug bonus-manager

Результат: public/renders/<id>/props.json + voice.mp3 и out/<id>.meta.json (заголовок, описание, теги, плейлист).
"""
import argparse
import datetime as dt
import json
import re
from pathlib import Path

from common import (OUT, RENDERS, SITE, TG, api_jobs, fmt_range, monthly, pick_track, professions, role,
                    say_money)
from tts import voice_track

HASHTAGS = "#igaming #вакансии #гемблинг #работа #карьера #shorts"


def first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s", text.strip())[0]


def short_item(text: str, limit: int = 64) -> str:
    """Пункт обязанностей до двоеточия/запятой, чтобы влезал в строку."""
    head = re.split(r"[:—;]", text)[0].strip()
    if len(head) > limit:
        head = head[:limit].rsplit(" ", 1)[0] + "…"
    return head


US = {"сша", "us", "usa", "united states"}


def us_office(j: dict) -> bool:
    """Офис в США — без визы недоступен русскоязычной аудитории, в подборку дня не берём."""
    return (j.get("country") or "").strip().lower() in US and "удал" not in (j.get("format") or "").lower()


def clean_title(t: str) -> str:
    t = re.sub(r"\s*\([^)]*\)", "", t)                    # (React.js + Python)
    t = re.split(r"\s+[-–—|/]\s+", t)[0]                   # хвост после « - », « / », « | »
    t = re.sub(r"\b(on-?site|remote|hybrid)\b.*$", "", t, flags=re.I)  # «On-site Bucharest»
    t = t.strip(" ,·")
    if t.isupper():
        t = t.title()
    return t[:60]


def usd_equiv(hi: int | None, cur: str) -> int:
    rate = {"USD": 1, "EUR": 1.08, "GBP": 1.27}.get(cur, 1)
    return int((hi or 0) * rate)


# ---------- форматы ----------

def build_hot_jobs(seed: str, args) -> dict:
    today = dt.date.today()
    jobs = api_jobs(pages=4)
    cands = []
    for j in jobs:
        lo, hi = monthly(j)
        if not hi:
            continue
        age = (today - dt.date.fromisoformat(j["posted_at"])).days
        if age > 2 or usd_equiv(hi, j["salary_currency"]) < 4000 or us_office(j):
            continue
        cands.append((usd_equiv(hi, j["salary_currency"]), lo, hi, j))
    if len(cands) < 3:  # тихий день — расширяем окно до недели
        for j in jobs:
            lo, hi = monthly(j)
            if hi and usd_equiv(hi, j["salary_currency"]) >= 4000 and not us_office(j) and j not in [c[3] for c in cands]:
                cands.append((usd_equiv(hi, j["salary_currency"]), lo, hi, j))
    cands.sort(key=lambda c: -c[0])
    picked, companies = [], set()
    for c in cands:
        if c[3]["company"] in companies:
            continue
        companies.add(c[3]["company"])
        picked.append(c)
        if len(picked) == 3:
            break
    top = picked[0][0]
    scenes = [{"id": "hook", "type": "hook", "kicker": "Вакансии дня", "title": "3 вакансии дня",
               "sub": f"с зарплатой {fmt_range(None, picked[0][2], picked[0][3]['salary_currency'])} в месяц"}]
    phrases = [{"id": "hook", "scene": "hook", "text": f"Три горячие вакансии дня в iGaming. Максимум — {say_money(picked[0][2], picked[0][3]['salary_currency'])} в месяц."}]
    words = ["Первая", "Вторая", "Третья"]
    for i, (_, lo, hi, j) in enumerate(picked):
        where = ("удалёнка" if "удал" in (j["format"] or "").lower() else j["country"])
        scenes.append({"id": f"job{i}", "type": "job", "n": i + 1, "total": 3, "title": clean_title(j["title"]), "company": j["company"],
                       "where": where.capitalize(), "salary": fmt_range(lo, hi, j["salary_currency"]), "tag": j["category"] or "iGaming",
                       "url": j["url"]})
        sal_say = f"от {say_money(lo, j['salary_currency'])} до {say_money(hi, j['salary_currency'])}" if lo and lo != hi else f"до {say_money(hi, j['salary_currency'])}"
        phrases.append({"id": f"job{i}", "scene": f"job{i}", "text": f"{words[i]}. {clean_title(j['title'])} в {j['company']}, {where}."})
        phrases.append({"id": f"job{i}s", "scene": f"job{i}", "text": f"Платят {sal_say} в месяц."})
    scenes.append({"id": "cta", "type": "cta", "line": "Все вакансии с зарплатами", "url": "spinhire.io/jobs"})
    phrases.append({"id": "cta", "scene": "cta", "text": "Ссылки на все три — в описании. Ещё шесть тысяч вакансий на spinhire.io."})
    links = "\n".join(f"{i + 1}. {j['title']} — {j['company']}: {j['url']}" for i, (_, _, _, j) in enumerate(picked))
    title = f"3 вакансии дня в iGaming: {fmt_range(None, picked[0][2], picked[0][3]['salary_currency'])} в месяц #Shorts"
    desc = (f"Три самые высокооплачиваемые вакансии за сегодня в гемблинге.\n\n{links}\n\n"
            f"Все вакансии с зарплатами → {SITE}/jobs\nTelegram с горячими вакансиями → {TG}\n\n{HASHTAGS}")
    return {"format": "hot_jobs", "playlist": "jobs", "mood": "dramatic", "bg": "hero-v.jpg", "scenes": scenes, "phrases": phrases,
            "title": title[:100], "description": desc, "tags": ["igaming", "вакансии", "гемблинг", "работа", "зарплата", "spinhire"]}


def build_salary(seed: str, args) -> dict:
    r = role(args.slug)
    regions = professions()["regions"]
    sal = r["salary"]
    dat = r["title"].lower()
    dative = args.dative or dat  # «аффилиат-менеджеру»
    bars = []
    for key in ("mt_cy", "eu", "remote"):
        lo, hi = sal[key]["middle"]
        bars.append({"label": regions[key].split(" · ")[0], "lo": lo, "hi": hi, "text": f"${lo:,}–{hi:,}".replace(",", " ")})
    mx = max(b["hi"] for b in bars)
    for b in bars:
        b["pct"] = round(b["hi"] / mx, 3)
    sen = sal["mt_cy"]["senior"][1]
    lead = sal["mt_cy"]["lead"][1]
    scenes = [
        {"id": "hook", "type": "hook", "kicker": "Зарплаты", "title": f"Сколько платят {dative}?", "sub": "middle · в месяц · после налогов зависит от страны"},
        {"id": "bars", "type": "bars", "title": r["title"], "sub": "Мидл, $ в месяц", "bars": bars},
        {"id": "big", "type": "big", "kicker": "Мальта и Кипр", "number": f"до ${lead:,}".replace(",", " "), "label": f"тимлид · сеньор до ${sen:,}".replace(",", " ")},
        {"id": "cta", "type": "cta", "line": "Вилки по 35 профессиям", "url": "spinhire.io/professions"},
    ]
    phrases = [
        {"id": "hook", "scene": "hook", "text": f"Сколько платят {dative} в iGaming?"},
        {"id": "b1", "scene": "bars", "text": f"На Мальте и Кипре мидл получает от {say_money(bars[0]['lo'], 'USD')} до {say_money(bars[0]['hi'], 'USD')} в месяц."},
        {"id": "b2", "scene": "bars", "text": f"В Польше, Румынии и Балтии — от {say_money(bars[1]['lo'], 'USD')} до {say_money(bars[1]['hi'], 'USD')}."},
        {"id": "b3", "scene": "bars", "text": f"На удалёнке — от {say_money(bars[2]['lo'], 'USD')} до {say_money(bars[2]['hi'], 'USD')}."},
        {"id": "big", "scene": "big", "text": f"Сеньор на Мальте — до {say_money(sen, 'USD')}, тимлид — до {say_money(lead, 'USD')}."},
        {"id": "cta", "scene": "cta", "text": "Вилки по тридцати пяти профессиям — на spinhire.io, ссылка в описании."},
    ]
    title = f"Сколько платят {dative} в iGaming? Зарплаты 2026 #Shorts"
    desc = (f"Зарплата {r['title']} в iGaming по регионам (middle, $ в месяц):\n"
            + "\n".join(f"• {b['label']}: {b['text']}" for b in bars)
            + f"\n• Senior (Мальта/Кипр): до ${sen:,}\n• Lead: до ${lead:,}\n\n"
            f"Подробно о профессии, навыках и входе → {SITE}/professions/{r['slug']}\n"
            f"Вакансии {r['title']} → {SITE}/jobs?q={r['title_en'].replace(' ', '+')}\nTelegram → {TG}\n\n{HASHTAGS} #зарплата").replace(",", " ")
    return {"format": "salary", "playlist": "salary", "mood": "inspirational", "bg": "hero.jpg", "scenes": scenes, "phrases": phrases,
            "title": title[:100], "description": desc, "tags": ["igaming", "зарплата", r["title"], r["title_en"], "гемблинг", "spinhire"]}


def build_profession(seed: str, args) -> dict:
    r = role(args.slug)
    items = [short_item(x) for x in r["responsibilities"][:3]]
    lo, hi = r["salary"]["mt_cy"]["middle"]
    entry = first_sentence(r["entry"])
    scenes = [
        {"id": "hook", "type": "hook", "kicker": "Профессия за 30 секунд", "title": r["title"], "sub": r["title_en"]},
        {"id": "lead", "type": "quote", "text": first_sentence(r["lead"])},
        {"id": "do", "type": "bullets", "title": "Что делает", "items": items},
        {"id": "big", "type": "big", "kicker": "Мальта и Кипр · middle", "number": f"${lo:,}–{hi:,}".replace(",", " "), "label": "в месяц"},
        {"id": "entry", "type": "quote", "kicker": "Как войти", "text": entry},
        {"id": "cta", "type": "cta", "line": "Полный разбор профессии", "url": f"spinhire.io/professions/{r['slug']}"},
    ]
    phrases = [
        {"id": "hook", "scene": "hook", "text": f"{r['title']} за тридцать секунд."},
        {"id": "lead", "scene": "lead", "text": first_sentence(r["lead"])},
        {"id": "do0", "scene": "do", "text": "Что делает: " + items[0].rstrip("…") + "."},
        {"id": "do1", "scene": "do", "text": items[1].rstrip("…") + "."},
        {"id": "do2", "scene": "do", "text": items[2].rstrip("…") + "."},
        {"id": "big", "scene": "big", "text": f"Мидл на Мальте и Кипре получает от {say_money(lo, 'USD')} до {say_money(hi, 'USD')} в месяц."},
        {"id": "entry", "scene": "entry", "text": entry},
        {"id": "cta", "scene": "cta", "text": "Полный разбор профессии, навыки и вакансии — на spinhire.io, ссылка в описании."},
    ]
    title = f"{r['title']} в iGaming: что делает и сколько получает #Shorts"
    desc = (f"{r['lead']}\n\nЧто делает:\n" + "\n".join(f"• {x}" for x in r["responsibilities"][:5])
            + f"\n\nЗарплата middle (Мальта/Кипр): ${lo:,}–{hi:,} в месяц\n\n"
            f"Полный разбор профессии → {SITE}/professions/{r['slug']}\nВакансии → {SITE}/jobs?q={r['title_en'].replace(' ', '+')}\n"
            f"Telegram → {TG}\n\n{HASHTAGS} #профессии").replace(",", " ")
    return {"format": "profession", "playlist": "profession", "mood": "bright", "bg": "hero-v2.jpg", "scenes": scenes, "phrases": phrases,
            "title": title[:100], "description": desc, "tags": ["igaming", "профессии", r["title"], r["title_en"], "карьера", "spinhire"]}


BUILDERS = {"hot_jobs": build_hot_jobs, "salary": build_salary, "profession": build_profession}


def assemble(spec: dict, vid: str) -> dict:
    """Озвучка → тайминги → сцены по фразам → props."""
    work = RENDERS / vid
    voice, timings = voice_track(spec["phrases"], work)
    total = timings[-1]["end"] + 1.4
    by_scene = {}
    for t in timings:
        by_scene.setdefault(t["scene"], []).append(t)
    scenes = []
    for i, sc in enumerate(spec["scenes"]):
        ph = by_scene.get(sc["id"], [])
        start = max(0.0, ph[0]["start"] - 0.25) if ph else (scenes[-1]["end"] if scenes else 0.0)
        scenes.append({**sc, "start": round(start, 3)})
    for i, sc in enumerate(scenes):
        sc["end"] = round(scenes[i + 1]["start"], 3) if i + 1 < len(scenes) else round(total, 3)
    scenes[0]["start"] = 0.0
    props = {
        "id": vid, "format": spec["format"], "bg": spec["bg"],
        "music": pick_track(spec["mood"], vid), "voice": f"renders/{vid}/voice.mp3",
        "duration": round(total, 3), "scenes": scenes,
        "captions": [{"text": t["text"], "start": t["start"], "end": t["end"]} for t in timings],
    }
    (work / "props.json").write_text(json.dumps(props, ensure_ascii=False, indent=1))
    OUT.mkdir(exist_ok=True)
    meta = {k: spec[k] for k in ("format", "playlist", "title", "description", "tags")}
    meta.update({"id": vid, "duration": props["duration"], "music": props["music"], "props": str(work / "props.json")})
    (OUT / f"{vid}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    return props


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("format", choices=BUILDERS)
    ap.add_argument("id")
    ap.add_argument("--slug", default="")
    ap.add_argument("--dative", default="", help="профессия в дательном падеже для заголовка «сколько платят …»")
    a = ap.parse_args()
    spec = BUILDERS[a.format](a.id, a)
    props = assemble(spec, a.id)
    print(json.dumps({"id": a.id, "duration": props["duration"], "scenes": [(s["id"], s["start"], s["end"]) for s in props["scenes"]],
                      "title": spec["title"]}, ensure_ascii=False))
