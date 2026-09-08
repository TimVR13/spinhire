#!/usr/bin/env python3
"""Дозаполнить вилки у вакансий Djinni: страница вакансии отдаёт baseSalary в JSON-LD.

Запуск на проде: nohup ./venv/bin/python3 scripts/backfill_djinni_salary.py > data/backfill-djinni.log 2>&1 &
Идёт с паузой 1 c между запросами, останавливается после 5 подряд ошибок сети/429.
"""
import json
import re
import sqlite3
import sys
import time
import urllib.request

sys.path.insert(0, ".")
from server.crawler import salary_from_jsonld  # noqa: E402

DB = "data/spinhire.db"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def fetch_salary(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=25) as r:
        page = r.read().decode("utf-8", "replace")
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        try:
            d = json.loads(block)
        except Exception:  # noqa: BLE001
            continue
        items = d if isinstance(d, list) else [d]
        for it in items:
            if isinstance(it, dict) and "JobPosting" in str(it.get("@type")):
                return salary_from_jsonld(it)
    return ""


def main():
    c = sqlite3.connect(DB, timeout=60)
    rows = c.execute("select id, source_url from jobs where source='djinni' and status='approved' "
                     "and (salary is null or salary in ('', 'по запросу')) order by id desc").fetchall()
    print(f"to check: {len(rows)}", flush=True)
    done = filled = errors = 0
    for jid, url in rows:
        try:
            sal = fetch_salary(url)
            errors = 0
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"{jid} ERR {exc}", flush=True)
            if "404" in str(exc) or "410" in str(exc):
                c.execute("update jobs set status='archived' where id=?", (jid,))
                c.commit()
                errors = 0
            elif errors >= 5:
                print("too many errors, stop", flush=True)
                break
            time.sleep(5)
            continue
        done += 1
        if sal:
            filled += 1
            c.execute("update jobs set salary=? where id=?", (sal, jid))
            c.commit()
            print(f"{jid} {sal}", flush=True)
        if done % 100 == 0:
            print(f"progress {done}/{len(rows)}, filled {filled}", flush=True)
        time.sleep(1.0)
    print(f"done {done}, filled {filled}", flush=True)


if __name__ == "__main__":
    main()
