#!/usr/bin/env python3
"""Экспорт открытого датасета «iGaming job market» для Kaggle / Hugging Face.

    python3 scripts/export_dataset.py            # data/dataset/ — jobs.csv, jobs.jsonl, market_monthly.csv, README.md

Берёт данные из публичного API spinhire.io (или локального сервера через SPINHIRE_BASE),
поэтому в выгрузку попадает ровно то, что и так открыто: без описаний, контактов и
персональных данных. Лицензия CC BY 4.0.
"""
import csv
import datetime
import json
import os
import sys
import urllib.request

BASE = os.environ.get("SPINHIRE_BASE", "https://spinhire.io")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "dataset")
FIELDS = ["id", "title", "company", "company_slug", "location", "country", "format", "category",
          "salary", "salary_min", "salary_max", "salary_currency", "salary_unit", "employment_type",
          "languages", "tags", "posted_at", "valid_through", "url", "source_url"]


def fetch(path: str):
    with urllib.request.urlopen(BASE + path, timeout=120) as response:
        return json.load(response)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    jobs, page = [], 1
    while True:
        chunk = fetch(f"/api/jobs?limit=100&page={page}")
        jobs += chunk["jobs"]
        print(f"page {page}/{chunk['pages']}: {len(jobs)} jobs", file=sys.stderr)
        if page >= chunk["pages"]:
            break
        page += 1
    with open(os.path.join(OUT, "jobs.csv"), "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for job in jobs:
            row = {k: job.get(k) for k in FIELDS}
            row["languages"] = "|".join(job.get("languages") or [])
            row["tags"] = "|".join(job.get("tags") or [])
            writer.writerow(row)
    with open(os.path.join(OUT, "jobs.jsonl"), "w", encoding="utf-8") as fh:
        for job in jobs:
            fh.write(json.dumps({k: job.get(k) for k in FIELDS}, ensure_ascii=False) + "\n")
    history = fetch("/api/market-history")
    with open(os.path.join(OUT, "market_monthly.csv"), "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["month", "open_jobs_end_of_month", "companies_hiring", "new_jobs", "share_with_salary_pct"])
        for m in history["months"]:
            writer.writerow([m["ym"], m["open_jobs"], m["companies"], m["new_jobs"], m["salary_pct"]])
    with open(os.path.join(OUT, "market_daily.csv"), "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["date", "open_jobs", "new_this_week", "companies_hiring", "share_with_salary_pct"])
        for day, snap in sorted(history["days"].items()):
            writer.writerow([day, snap["live_jobs"], snap["new_this_week"], snap["companies"], snap["with_salary_pct"]])
    stats = fetch("/api/market-stats")
    today = datetime.date.today().isoformat()
    readme = f"""# iGaming Job Market — open vacancies index by SpinHire

**Snapshot date:** {today} · **Open jobs:** {len(jobs)} · **Companies:** {stats['companies']} · **License:** CC BY 4.0

Live job postings in the iGaming industry (online casino, sports betting, game studios, affiliates,
payments, compliance) aggregated by [SpinHire](https://spinhire.io) from employer career pages, ATS feeds
and public channels. The index is refreshed every 6 hours; jobs that disappear at the source are archived.
This dataset is a point-in-time export of the public API (`https://spinhire.io/api/jobs`).

## Files

- `jobs.csv` / `jobs.jsonl` — one row per open job: title, company, location, country, work format,
  department, salary (raw string plus parsed min/max/currency/unit when the employer published it),
  employment type, working languages, tags, posting and expiry dates, SpinHire URL and the original posting URL.
- `market_monthly.csv` — open jobs at month end, hiring companies, new postings and the share with a
  published salary, reconstructed from each job's open/close dates. Source: https://spinhire.io/market
- `market_daily.csv` — daily snapshots stored from September 2026.

## Notes

- Only about 5% of iGaming employers publish a salary in the posting; `salary_min`/`salary_max` are empty otherwise.
- `country` is derived from the free-text location; `Remote` is a separate category.
- No job descriptions, contact details or personal data are included.
- Department names are in Russian in the API (`category`); English equivalents: Операции казино = Casino operations,
  Разработка игр = Game development, Маркетинг и CRM = Marketing & CRM, Комплаенс и AML = Compliance & AML,
  Аффилейты и медиабаинг = Affiliates & media buying, Платежи и антифрод = Payments & anti-fraud,
  Поддержка игроков = Player support, Данные и BI = Data & BI, Финансы, право и HР = Finance, legal & HR,
  Топ-менеджмент = Executive, Беттинг и трейдинг = Betting & trading.

## Citation

SpinHire (2026). *iGaming Job Market — open vacancies index*. https://spinhire.io/market — CC BY 4.0.

Methodology and live figures: https://spinhire.io/en/market · API docs: https://spinhire.io/docs
"""
    with open(os.path.join(OUT, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(readme)
    print(f"done: {len(jobs)} jobs → {OUT}")


if __name__ == "__main__":
    main()
