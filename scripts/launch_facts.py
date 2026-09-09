#!/usr/bin/env python3
"""Факт-лист для подачи на Product Hunt и другие каталоги — по живым цифрам сайта.

    python3 scripts/launch_facts.py                 # таблица + готовые формулировки
    python3 scripts/launch_facts.py --json          # то же машиночитаемо
    python3 scripts/launch_facts.py --base http://127.0.0.1:8000

Цифры в текстах запуска устаревают за неделю (в сентябре 2026 число компаний
в старом ките разошлось с реальностью вдвое), поэтому перед каждой подачей
факты берём отсюда, а не из документа.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import date

DEFAULT_BASE = "https://spinhire.io"
TIMEOUT = 30

# Постоянные факты: меняются вместе с продуктом, а не с индексом.
CONSTANTS = {
    "professions": 35,
    "languages": 12,
    "refresh_hours": 6,
    "price_single_eur": 49,
    "price_unlimited_month_eur": 599,
    "price_contact_from_eur": 4,
    "data_license": "CC BY 4.0",
    "launched": 2026,
    "contact": "hello@spinhire.io",
}


def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "spinhire-launch-facts/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def collect(base: str) -> dict:
    base = base.rstrip("/")
    stats = fetch(f"{base}/api/market-stats")
    jobs = fetch(f"{base}/api/jobs?limit=1")
    countries = [c for c in stats.get("countries", []) if c.get("name")]
    return {
        "as_of": date.today().isoformat(),
        "base": base,
        "live_jobs": stats["live_jobs"],
        "companies": stats["companies"],
        "new_this_week": stats["new_this_week"],
        "with_salary": stats.get("with_salary"),
        "with_salary_pct": stats.get("with_salary_pct"),
        "api_total": jobs.get("total"),
        "countries_in_top_slice": len(countries),
        "top_countries": [c["name"] for c in countries[:5]],
        "top_directions": [d["name"] for d in stats.get("directions", [])[:5]],
        **CONSTANTS,
    }


def human(n: int) -> str:
    """Английская запись числа: 6,103."""
    return f"{n:,}"


def ru_num(n: int) -> str:
    """Русская запись числа: 6 103."""
    return f"{n:,}".replace(",", " ")


def render(f: dict) -> str:
    rounded_jobs = f["live_jobs"] // 100 * 100
    rounded_companies = f["companies"] // 10 * 10
    lines = [
        f"SpinHire — факты на {f['as_of']} (источник: {f['base']})",
        "",
        f"  Живых вакансий          {human(f['live_jobs'])}",
        f"  Компаний нанимают       {human(f['companies'])}",
        f"  Новых за неделю         {human(f['new_this_week'])}",
        f"  Отдаёт /api/jobs        {human(f['api_total'] or 0)}",
        f"  С раскрытой зарплатой   {human(f['with_salary'] or 0)} ({f['with_salary_pct']}%)",
        f"  Стран в топ-срезе       {f['countries_in_top_slice']} (полная география — на /market)",
        f"  Профессий с вилками     {f['professions']}",
        f"  Языков интерфейса       {f['languages']}",
        f"  Обновление индекса      каждые {f['refresh_hours']} часов",
        f"  Лицензия данных         {f['data_license']}",
        "",
        "Готовые формулировки (EN):",
        "",
        f"  tagline    Open-data job board for the iGaming industry",
        f"  short      {human(rounded_jobs)}+ live iGaming jobs from {human(rounded_companies)}+ companies, "
        f"refreshed every {f['refresh_hours']} hours. The whole index is an open API — no key, {f['data_license']}.",
        f"  citation   \"According to SpinHire, {human(f['live_jobs'])} iGaming jobs were open at "
        f"{human(f['companies'])} companies as of {f['as_of']}\" — {f['base']}/en/market",
        "",
        "Готовые формулировки (RU):",
        "",
        f"  короткое   {ru_num(rounded_jobs)}+ живых вакансий iGaming от {ru_num(rounded_companies)}+ компаний, "
        f"обновление каждые {f['refresh_hours']} часов. Весь индекс открыт: API без ключа, {f['data_license']}.",
        "",
        "Осторожно с формулировками:",
        "",
        f"  Зарплата раскрыта у {f['with_salary_pct']}% вакансий индекса — писать «salaries are open»",
        "  про весь индекс нельзя. Верная формулировка: «salary ranges wherever the employer",
        "  discloses them; employer-posted jobs are published only with a range».",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=DEFAULT_BASE, help=f"адрес сайта (по умолчанию {DEFAULT_BASE})")
    ap.add_argument("--json", action="store_true", help="выдать JSON вместо таблицы")
    args = ap.parse_args()
    try:
        facts = collect(args.base)
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError) as e:
        print(f"не получилось собрать факты с {args.base}: {e}", file=sys.stderr)
        return 1
    print(json.dumps(facts, ensure_ascii=False, indent=2) if args.json else render(facts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
