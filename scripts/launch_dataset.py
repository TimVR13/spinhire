#!/usr/bin/env python3
"""Датасет для Hugging Face, Kaggle и data.world — из живого индекса вакансий.

    python3 scripts/launch_dataset.py                  # выгрузка в data/launch-dataset/
    python3 scripts/launch_dataset.py --limit 500      # быстрый прогон на пробу
    python3 scripts/launch_dataset.py --base http://127.0.0.1:8000

Каталоги данных — единственная площадка, где мы заведомо первые: открытого среза
рынка труда iGaming больше никто не публикует. Готовим три файла и карточку датасета,
дальше их остаётся залить через веб-форму Hugging Face или Kaggle.

Запускать **после деплоя**: до него `?lang=en` отдаёт русские значения полей, и в
датасете окажется «офис» вместо «office».
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date

DEFAULT_BASE = "https://spinhire.io"
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "launch-dataset")
PAGE_SIZE = 200
TIMEOUT = 60

FIELDS = ["id", "title", "company", "company_slug", "category", "country", "location",
          "format", "salary", "salary_min", "salary_max", "salary_currency", "salary_unit",
          "employment_type", "languages", "tags", "posted_at", "valid_through", "url"]


def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "spinhire-launch-dataset/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def collect_jobs(base: str, limit: int | None) -> list[dict]:
    rows, page, total = [], 1, None
    while True:
        payload = fetch(f"{base}/api/jobs?lang=en&limit={PAGE_SIZE}&page={page}")
        batch = payload.get("jobs") or []
        rows.extend(batch)
        if total is None:
            # сервер режет limit по своему потолку — ориентируемся на total, а не на размер страницы
            total = payload.get("total") or 0
        print(f"  страница {page}: {len(batch)} вакансий (всего {len(rows)} из {total})",
              file=sys.stderr)
        if limit and len(rows) >= limit:
            return rows[:limit]
        if not batch or (total and len(rows) >= total):
            return rows
        page += 1


def flatten(job: dict) -> dict:
    row = {key: job.get(key, "") for key in FIELDS}
    for key in ("languages", "tags"):
        value = job.get(key) or []
        row[key] = "; ".join(value) if isinstance(value, list) else (value or "")
    return row


def write_jobs(rows: list[dict]) -> None:
    with open(os.path.join(OUT_DIR, "jobs.csv"), "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for job in rows:
            writer.writerow(flatten(job))
    with open(os.path.join(OUT_DIR, "jobs.jsonl"), "w", encoding="utf-8") as fh:
        for job in rows:
            fh.write(json.dumps(job, ensure_ascii=False) + "\n")


def write_history(base: str) -> list[dict]:
    months = fetch(f"{base}/api/market-history").get("months") or []
    columns = ["ym", "label_en", "open_jobs", "companies", "new_jobs", "salary_pct", "current"]
    with open(os.path.join(OUT_DIR, "market_history.csv"), "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for month in months:
            writer.writerow(month)
    return months


CARD = """---
license: cc-by-4.0
language:
  - en
tags:
  - job-postings
  - labour-market
  - igaming
  - gambling-industry
  - hiring
pretty_name: SpinHire iGaming Jobs
size_categories:
  - 1K<n<10K
source_datasets:
  - original
---

# SpinHire iGaming Jobs

An open snapshot of the iGaming labour market: {jobs} live vacancies from {companies} companies
across online casinos, sportsbooks, game studios, affiliate networks and payment providers,
collected on {today}.

The industry hires constantly and pays in EUR, but its job market is closed: existing boards keep
the index behind a login. This dataset is the same index SpinHire serves publicly — no key, no
scraping needed.

## Files

| File | Rows | What it is |
|---|---|---|
| `jobs.csv` | {jobs} | One row per live vacancy, flat columns |
| `jobs.jsonl` | {jobs} | The same records as returned by the API, one JSON object per line |
| `market_history.csv` | {months} | Monthly aggregates: open jobs, hiring companies, new postings, share with a salary range |

## Columns in `jobs.csv`

`id`, `title`, `company`, `company_slug`, `category` (one of ~10 industry verticals),
`country`, `location`, `format` (office / hybrid / remote), `salary` (as published),
`salary_min`, `salary_max`, `salary_currency`, `salary_unit`, `employment_type`,
`languages` (semicolon-separated), `tags`, `posted_at`, `valid_through`, `url`.

## How it is collected

Employer career pages and ATS feeds are crawled every 6 hours; every record links back to the
original posting. Vacancies that disappear at the source are archived, so the snapshot is live
rather than cumulative. Employer-posted jobs go through human moderation and are published only
with a salary range.

**Salary coverage is partial.** Only about 9% of the index discloses a range — that is the
industry, not a gap in the data. Treat `salary_min` / `salary_max` as a biased sample, not as a
market average.

## Live sources

- API (no key): <https://spinhire.io/en/api/jobs>
- Market statistics: <https://spinhire.io/en/market> · CSV: <https://spinhire.io/market.csv>
- MCP server for agents: `https://spinhire.io/mcp`
- Methodology and press kit: <https://spinhire.io/en/press.html>

## Licence and citation

CC BY 4.0. Attribution to spinhire.io.

```
SpinHire iGaming Jobs dataset, {today}. https://spinhire.io/en/market (CC BY 4.0)
```
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--limit", type=int, default=0, help="ограничить число вакансий")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    os.makedirs(OUT_DIR, exist_ok=True)
    try:
        print(f"Собираем вакансии с {base} …", file=sys.stderr)
        jobs = collect_jobs(base, args.limit or None)
        write_jobs(jobs)
        months = write_history(base)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"Не достучались до {base}: {e}", file=sys.stderr)
        return 1

    companies = len({job.get("company_slug") or job.get("company") for job in jobs})
    card = CARD.format(jobs=f"{len(jobs):,}".replace(",", " "), companies=companies,
                       months=len(months), today=date.today().isoformat())
    with open(os.path.join(OUT_DIR, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(card)

    russian = [job for job in jobs if any(
        "а" <= ch.lower() <= "я" for ch in (job.get("format") or ""))]
    print(f"\nГотово: {OUT_DIR}")
    print(f"  jobs.csv / jobs.jsonl   {len(jobs)} вакансий, {companies} компаний")
    print(f"  market_history.csv      {len(months)} месяцев")
    print("  README.md               карточка датасета (front matter Hugging Face)")
    if russian:
        print(f"\n⚠ У {len(russian)} записей поле format осталось русским — значит, ветка с"
              " англоязычным API ещё не выкачена. Залейте деплой и соберите датасет заново.")
    print("\nКуда заливать:")
    print("  Hugging Face  https://huggingface.co/new-dataset (README.md идёт карточкой)")
    print("  Kaggle        https://www.kaggle.com/datasets — «New Dataset», к нему notebook")
    print("  data.world    https://data.world — зеркало CSV")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
