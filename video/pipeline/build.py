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
N_JOBS = 5
EMPLOYMENT = {"FULL_TIME": "полная занятость", "PART_TIME": "частичная", "CONTRACTOR": "контракт", "INTERN": "стажировка"}
GRADES = [("junior", "Junior"), ("middle", "Middle"), ("senior", "Senior"), ("lead", "Lead")]


def grade_bars(sal: dict, region: str = "mt_cy") -> list[dict]:
    bars = [{"label": lbl, "lo": sal[region][g][0], "hi": sal[region][g][1]} for g, lbl in GRADES if g in sal[region]]
    mx = max(b["hi"] for b in bars)
    for b in bars:
        b["text"] = f"${b['lo']:,}–{b['hi']:,}".replace(",", " ")
        b["pct"] = round(b["hi"] / mx, 3)
    return bars


def top_locations(queries: list[str], family: str, n: int = 3) -> tuple[list[dict], str]:
    """Где чаще всего ищут эту роль — по живым вакансиям сайта. Если по самой роли вакансий мало,
    берём всё направление (family): там сотни строк и статистика честная."""
    from collections import Counter
    jobs, scope = [], ""
    for q in queries:
        jobs = api_jobs(pages=2, q=q)
        if len(jobs) >= 8:
            scope = "по этой роли"
            break
    if len(jobs) < 8:
        jobs = api_jobs(pages=6, category=family)
        scope = f"направление «{family.lower()}»"
    cnt = Counter()
    for j in jobs:
        key = "Удалёнка" if "удал" in (j.get("format") or "").lower() else (j.get("country") or "").strip()
        if len(key) >= 4 and key.lower() not in US and not key.isascii():
            cnt[key] += 1
        elif key == "Удалёнка":
            cnt[key] += 1
    top = cnt.most_common(n)
    mx = top[0][1] if top else 1
    return [{"label": k, "text": f"{v} вак.", "pct": round(v / mx, 3), "n": v} for k, v in top], scope


def us_office(j: dict) -> bool:
    """Офис в США — без визы недоступен русскоязычной аудитории, в подборку дня не берём."""
    return (j.get("country") or "").strip().lower() in US and "удал" not in (j.get("format") or "").lower()


def clean_title(t: str) -> str:
    t = re.sub(r"\s*\([^)]*\)", "", t)                    # (React.js + Python)
    # двуязычные названия «Informācijas … Inženieris/Information System» — берём английскую (ASCII) часть
    parts = [x.strip() for x in re.split(r"\s*[|/]\s*", t) if x.strip()]
    ascii_parts = [x for x in parts if x.isascii()]
    if ascii_parts and len(parts) > 1:
        t = max(ascii_parts, key=len)
    t = re.split(r"\s+[-–—]\s+", t)[0]                    # хвост после « - »
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
    if len(cands) < N_JOBS:  # тихий день — берём свежие за неделю и порог ниже
        for j in api_jobs(pages=8):
            lo, hi = monthly(j)
            if hi and usd_equiv(hi, j["salary_currency"]) >= 3000 and not us_office(j) and j not in [c[3] for c in cands]:
                cands.append((usd_equiv(hi, j["salary_currency"]), lo, hi, j))
    cands.sort(key=lambda c: -c[0])
    picked, companies = [], set()
    for c in cands:
        if c[3]["company"] in companies:
            continue
        companies.add(c[3]["company"])
        picked.append(c)
        if len(picked) == N_JOBS:
            break
    n = len(picked)
    NUM = {3: "Три горячие вакансии", 4: "Четыре горячие вакансии", 5: "Пять горячих вакансий"}
    scenes = [{"id": "hook", "type": "hook", "kicker": "Вакансии дня", "title": f"{n} вакансий дня" if n != 4 else "4 вакансии дня",
               "sub": f"с зарплатой {fmt_range(None, picked[0][2], picked[0][3]['salary_currency'])} в месяц"}]
    phrases = [{"id": "hook", "scene": "hook", "text": f"{NUM.get(n, 'Горячие вакансии')} дня в iGaming. Максимум — {say_money(picked[0][2], picked[0][3]['salary_currency'])} в месяц."}]
    words = ["Первая", "Вторая", "Третья", "Четвёртая", "Пятая"]
    for i, (_, lo, hi, j) in enumerate(picked):
        where = ("удалёнка" if "удал" in (j["format"] or "").lower() else j["country"])
        note = " · ".join(x for x in [", ".join((j.get("languages") or [])[:2]), EMPLOYMENT.get(j.get("employment_type") or "", "")] if x)
        scenes.append({"id": f"job{i}", "type": "job", "n": i + 1, "total": n, "title": clean_title(j["title"]), "company": j["company"],
                       "where": where.capitalize(), "salary": fmt_range(lo, hi, j["salary_currency"]), "tag": j["category"] or "iGaming",
                       "note": note, "url": j["url"]})
        sal_say = f"от {say_money(lo, j['salary_currency'])} до {say_money(hi, j['salary_currency'])}" if lo and lo != hi else f"до {say_money(hi, j['salary_currency'])}"
        phrases.append({"id": f"job{i}", "scene": f"job{i}", "text": f"{words[i]}. {clean_title(j['title'])} в {j['company']}, {where}."})
        phrases.append({"id": f"job{i}s", "scene": f"job{i}", "text": f"Платят {sal_say} в месяц."})
    scenes.append({"id": "cta", "type": "cta", "line": "Все вакансии с зарплатами", "url": "spinhire.io/jobs"})
    phrases.append({"id": "cta", "scene": "cta", "text": "Ссылки на все — в описании. Ещё шесть тысяч вакансий на spinhire.io."})
    links = "\n".join(f"{i + 1}. {j['title']} — {j['company']}: {j['url']}" for i, (_, _, _, j) in enumerate(picked))
    day = dt.date.today()
    MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    title = f"Вакансии iGaming с зарплатой {fmt_range(None, picked[0][2], picked[0][3]['salary_currency'])}: топ-{n} за {day.day} {MONTHS[day.month - 1]} | работа в гемблинге"
    desc = (f"Самые высокооплачиваемые вакансии за сегодня в гемблинге.\n\n{links}\n\n"
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
        {"id": "grades", "type": "bars", "title": "По грейдам", "sub": "Мальта и Кипр, $ в месяц", "bars": grade_bars(sal)},
        {"id": "big", "type": "big", "kicker": "Мальта и Кипр", "number": f"до ${lead:,}".replace(",", " "), "label": f"тимлид · сеньор до ${sen:,}".replace(",", " ")},
        {"id": "cta", "type": "cta", "line": "Вилки по 35 профессиям", "url": "spinhire.io/professions"},
    ]
    phrases = [
        {"id": "hook", "scene": "hook", "text": f"Сколько платят {dative} в iGaming?"},
        {"id": "b1", "scene": "bars", "text": f"На Мальте и Кипре мидл получает от {say_money(bars[0]['lo'], 'USD')} до {say_money(bars[0]['hi'], 'USD')} в месяц."},
        {"id": "b2", "scene": "bars", "text": f"В Польше, Румынии и Балтии — от {say_money(bars[1]['lo'], 'USD')} до {say_money(bars[1]['hi'], 'USD')}."},
        {"id": "b3", "scene": "bars", "text": f"На удалёнке — от {say_money(bars[2]['lo'], 'USD')} до {say_money(bars[2]['hi'], 'USD')}."},
        {"id": "g1", "scene": "grades", "text": f"Джуниор стартует с {say_money(sal['mt_cy']['junior'][0], 'USD')}."},
        {"id": "g2", "scene": "grades", "text": f"Мидл — до {say_money(sal['mt_cy']['middle'][1], 'USD')}."},
        {"id": "g3", "scene": "grades", "text": f"Сеньор — до {say_money(sen, 'USD')}."},
        {"id": "g4", "scene": "grades", "text": f"Тимлид — до {say_money(lead, 'USD')}."},
        {"id": "big", "scene": "big", "text": f"Итого потолок на Мальте — {say_money(lead, 'USD')} в месяц. Плюс бонусы: {(lambda b: b[:1].lower() + b[1:])(first_sentence(r.get('bonus', '') or 'зависят от компании'))}"},
        {"id": "cta", "scene": "cta", "text": "Вилки по тридцати пяти профессиям — на spinhire.io, ссылка в описании."},
    ]
    title = f"Сколько платят {dative} в iGaming 2026: зарплаты на Мальте, Кипре, в Европе и на удалёнке"
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
    skills = [short_item(x, 58) for x in r["hard_skills"][:3]]
    sal = r["salary"]
    locs, loc_scope = top_locations([r["title_en"]] + [a for a in r.get("aliases", []) if a.isascii()], r["family"])
    scenes = [
        {"id": "hook", "type": "hook", "kicker": "Профессия за минуту", "title": r["title"], "sub": r["title_en"]},
        {"id": "lead", "type": "quote", "text": first_sentence(r["lead"])},
        {"id": "do", "type": "bullets", "title": "Что делает", "items": items},
        {"id": "grades", "type": "bars", "title": "Сколько платят", "sub": "Мальта и Кипр, $ в месяц", "bars": grade_bars(sal)},
        {"id": "skills", "type": "bullets", "title": "Что нужно уметь", "items": skills},
        *([{"id": "locs", "type": "bars", "title": "Где ищут", "sub": loc_scope, "bars": locs}] if locs else []),
        {"id": "entry", "type": "quote", "kicker": "Как войти", "text": entry},
        {"id": "cta", "type": "cta", "line": "Полный разбор профессии", "url": f"spinhire.io/professions/{r['slug']}"},
    ]
    loc_say = ", ".join(f"{l['label']} — {l['n']}" for l in locs)
    phrases = [
        {"id": "hook", "scene": "hook", "text": f"{r['title']} в iGaming за минуту: что делает, сколько получает и как войти."},
        {"id": "lead", "scene": "lead", "text": first_sentence(r["lead"])},
        {"id": "do0", "scene": "do", "text": "Что делает. " + items[0].rstrip("…") + "."},
        {"id": "do1", "scene": "do", "text": items[1].rstrip("…") + "."},
        {"id": "do2", "scene": "do", "text": items[2].rstrip("…") + "."},
        {"id": "g1", "scene": "grades", "text": f"Зарплаты на Мальте и Кипре. Джуниор — от {say_money(sal['mt_cy']['junior'][0], 'USD')}."},
        {"id": "g2", "scene": "grades", "text": f"Мидл — от {say_money(lo, 'USD')} до {say_money(hi, 'USD')}."},
        {"id": "g3", "scene": "grades", "text": f"Сеньор — до {say_money(sal['mt_cy']['senior'][1], 'USD')}."},
        {"id": "g4", "scene": "grades", "text": f"Тимлид — до {say_money(sal['mt_cy']['lead'][1], 'USD')} в месяц."},
        {"id": "s0", "scene": "skills", "text": "Что нужно уметь. " + skills[0].rstrip("…") + "."},
        {"id": "s1", "scene": "skills", "text": skills[1].rstrip("…") + "."},
        {"id": "s2", "scene": "skills", "text": skills[2].rstrip("…") + "."},
        *([{"id": "locs", "scene": "locs", "text": f"Где ищут прямо сейчас, {loc_scope}: {loc_say} вакансий."}] if locs else []),
        {"id": "entry", "scene": "entry", "text": "Как войти. " + entry},
        {"id": "cta", "scene": "cta", "text": "Полный разбор профессии, навыки и вакансии — на spinhire.io, ссылка в описании."},
    ]
    title = f"Кто такой {r['title'].lower()} в iGaming: обязанности, зарплата, как стать | профессии гемблинга"
    desc = (f"{r['lead']}\n\nЧто делает:\n" + "\n".join(f"• {x}" for x in r["responsibilities"][:5])
            + f"\n\nЗарплата (Мальта/Кипр, $ в месяц):\n" + "\n".join(f"• {b['label']}: {b['text']}" for b in grade_bars(sal))
            + "\n\nЧто нужно уметь:\n" + "\n".join(f"• {x}" for x in r["hard_skills"][:5])
            + ("\n\nГде ищут: " + ", ".join(f"{l['label']} ({l['n']})" for l in locs) if locs else "") + "\n\n"
            f"Полный разбор профессии → {SITE}/professions/{r['slug']}\nВакансии → {SITE}/jobs?q={r['title_en'].replace(' ', '+')}\n"
            f"Telegram → {TG}\n\n{HASHTAGS} #профессии").replace(",", " ")
    return {"format": "profession", "playlist": "profession", "mood": "bright", "bg": "hero-v2.jpg", "scenes": scenes, "phrases": phrases,
            "title": title[:100], "description": desc, "tags": ["igaming", "профессии", r["title"], r["title_en"], "карьера", "spinhire"]}


def build_market_stat(seed: str, args) -> dict:
    """«Цифра дня»: рынок в одной цифре + топ направлений."""
    from common import market_stats
    m = market_stats()
    dirs = m.get("directions", [])[:4]
    mx = dirs[0]["jobs"] if dirs else 1
    bars = [{"label": d["name"], "text": f"{d['jobs']:,}".replace(",", " "), "pct": round(d["jobs"] / mx, 3)} for d in dirs]
    live, new, comp = m.get("live_jobs", 0), m.get("new_this_week", 0), m.get("companies", 0)
    fmt_n = lambda n: f"{n:,}".replace(",", " ")
    scenes = [
        {"id": "hook", "type": "hook", "kicker": "Цифра дня", "title": f"+{fmt_n(new)} вакансий", "sub": "в iGaming за неделю"},
        {"id": "big", "type": "big", "kicker": "Сейчас открыто", "number": fmt_n(live), "label": f"вакансий от {fmt_n(comp)} компаний"},
        {"id": "dirs", "type": "bars", "title": "Где больше всего", "sub": "открытых вакансий по направлениям", "bars": bars},
        {"id": "cta", "type": "cta", "line": "Живая статистика рынка", "url": "spinhire.io/jobs"},
    ]
    phrases = [
        {"id": "hook", "scene": "hook", "text": f"Цифра дня. За неделю в iGaming появилось {fmt_n(new)} новых вакансий."},
        {"id": "big", "scene": "big", "text": f"Всего сейчас открыто {fmt_n(live)} вакансий от {fmt_n(comp)} компаний."},
    ] + [{"id": f"d{i}", "scene": "dirs", "text": f"{d['name']} — {fmt_n(d['jobs'])}." if i else f"Больше всего ищут в направлении «{d['name']}» — {fmt_n(d['jobs'])} вакансий."}
         for i, d in enumerate(dirs)] + [
        {"id": "cta", "scene": "cta", "text": "Полная статистика и все вакансии — на spinhire.io, ссылка в описании."},
    ]
    day = dt.date.today()
    title = f"Рынок iGaming сегодня: {fmt_n(live)} вакансий, +{fmt_n(new)} за неделю | статистика найма в гемблинге"
    desc = (f"Живая статистика рынка труда iGaming на {day.isoformat()}:\n• открыто вакансий: {fmt_n(live)}\n• новых за неделю: {fmt_n(new)}\n"
            f"• компаний нанимают: {fmt_n(comp)}\n\nПо направлениям:\n" + "\n".join(f"• {d['name']}: {fmt_n(d['jobs'])}" for d in dirs)
            + f"\n\nВсе вакансии → {SITE}/jobs\nTelegram → {TG}\n\n{HASHTAGS} #рыноктруда")
    return {"format": "market_stat", "playlist": "jobs", "mood": "dramatic", "bg": "hero.jpg", "scenes": scenes, "phrases": phrases,
            "title": title[:100], "description": desc, "tags": ["igaming", "вакансии", "рынок труда", "гемблинг", "статистика", "spinhire"]}


BUILDERS = {"hot_jobs": build_hot_jobs, "salary": build_salary, "profession": build_profession, "market_stat": build_market_stat}


def apply_script(spec: dict, path: str) -> dict:
    """Правки агента поверх автосборки: {"phrases": [...], "scenes": [...], "title": "...", "description": "...", "tags": [...]}.
    Фразы заменяются целиком (id/scene обязаны совпадать со сценами), сцены — по id (обновляются поля)."""
    over = json.load(open(path, encoding="utf-8"))
    if over.get("phrases"):
        ids = {s["id"] for s in spec["scenes"]}
        bad = [p for p in over["phrases"] if p.get("scene") not in ids]
        if bad:
            raise SystemExit(f"фразы ссылаются на несуществующие сцены: {bad}")
        spec["phrases"] = over["phrases"]
    for sc in over.get("scenes", []):
        for cur in spec["scenes"]:
            if cur["id"] == sc["id"]:
                cur.update(sc)
    for k in ("title", "description", "tags", "mood", "bg"):
        if over.get(k):
            spec[k] = over[k]
    return spec


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
    ap.add_argument("--script", default="", help="JSON с правками агента (фразы/сцены/заголовок)")
    ap.add_argument("--spec-only", action="store_true", help="только собрать spec в stdout, без озвучки")
    a = ap.parse_args()
    spec = BUILDERS[a.format](a.id, a)
    if a.spec_only:
        print(json.dumps(spec, ensure_ascii=False, indent=1)); raise SystemExit
    if a.script:
        spec = apply_script(spec, a.script)
    props = assemble(spec, a.id)
    print(json.dumps({"id": a.id, "duration": props["duration"], "scenes": [(s["id"], s["start"], s["end"]) for s in props["scenes"]],
                      "title": spec["title"]}, ensure_ascii=False))
