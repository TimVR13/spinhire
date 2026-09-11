#!/usr/bin/env python3
"""Аудит языковых версий: ищет русский текст там, где его быть не должно.

Проверяет две вещи на каждой языковой версии страницы:

* латиница/греческий (en, de, pl, fr, es, pt, it, el, ro) — кириллица в видимом
  тексте или в переводимых атрибутах это утечка;
* кириллические языки (bg, uk) — утечка это текстовый узел, дословно совпавший
  с русской версией той же страницы (значит, словарь его не поймал).

Запуск:
    python3 scripts/i18n_audit.py                  # выборка страниц каждого типа
    python3 scripts/i18n_audit.py --full           # все вакансии и компании
    python3 scripts/i18n_audit.py --langs en,de --sample 40
    python3 scripts/i18n_audit.py --json out.json  # машинный отчёт
    python3 scripts/i18n_audit.py --from-db        # покрытие словарём значений базы

Код возврата 1, если утечки есть — годится для CI и для деплой-гейта.
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

BASE = "https://spinhire.io"
LATIN_LANGS = ["en", "de", "pl", "fr", "es", "pt", "it", "el", "ro"]
CYRILLIC_LANGS = ["bg", "uk"]
ALL_LANGS = LATIN_LANGS + CYRILLIC_LANGS

CYR_RE = re.compile(r"[А-Яа-яЁё]")
SKIP_BLOCK_RE = re.compile(r"<(script|style|textarea)\b.*?</\1>", re.S | re.I)
TEXT_RE = re.compile(r">([^<>]+)<")
ATTR_RE = re.compile(r'(?:placeholder|aria-label|title|alt)="([^"]+)"')
META_RE = re.compile(r'<meta[^>]+(?:name="description"|property="og:[a-z]+")[^>]*content="([^"]+)"')
TITLE_RE = re.compile(r"<title>([^<]*)</title>", re.I)
ENTITY_RE = re.compile(r"&(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);")

# Кириллица, которая на иноязычной версии законна: названия языков в их
# собственном написании и имена собственные, которые не переводятся.
ALLOWED = {
    "Русский", "Українська", "Български", "Русский язык",
}


def fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": "SpinHire-i18n-audit/1.0 (+https://spinhire.io)",
        "Accept-Language": "en",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except Exception as exc:                                    # noqa: BLE001
        return f"<!--fetch-error {exc}-->"


def strings_of(html: str) -> list:
    """Видимый текст и переводимые атрибуты страницы, без скриптов и стилей."""
    body = SKIP_BLOCK_RE.sub(" ", html)
    out = []
    for chunk in TEXT_RE.findall(body):
        value = ENTITY_RE.sub(" ", chunk)
        value = " ".join(value.split())
        if value:
            out.append(value)
    for pattern in (ATTR_RE, META_RE, TITLE_RE):
        for chunk in pattern.findall(html):
            value = " ".join(ENTITY_RE.sub(" ", chunk).split())
            if value:
                out.append(value)
    return out


def leaks_for(lang: str, html: str, ru_strings: set) -> list:
    """Строки страницы, оставшиеся русскими."""
    found = []
    for value in strings_of(html):
        if value in ALLOWED or not CYR_RE.search(value):
            continue
        if lang in CYRILLIC_LANGS and value not in ru_strings:
            continue        # болгарский/украинский перевод — своя кириллица, это норма
        found.append(value)
    return found


def sitemap_paths(base: str) -> dict:
    """Пути из sitemap, разложенные по типам страниц."""
    xml = fetch(f"{base}/sitemap.xml")
    # в sitemap всегда боевой домен, даже когда сайт поднят локально —
    # берём путь разбором URL, а не отрезанием базы
    paths = [urllib.parse.urlsplit(u).path or "/" for u in re.findall(r"<loc>([^<]+)</loc>", xml)]
    groups = defaultdict(list)
    for path in paths:
        head = path.strip("/").split("/")[0]
        if head in ALL_LANGS:
            continue                                   # языковые копии проверяем сами
        groups[head or "root"].append(path)
    return groups


def pick(groups: dict, sample: int, full: bool) -> list:
    """Хотя бы по одной странице каждого типа плюс выборка вакансий и компаний."""
    urls = []
    for kind, paths in sorted(groups.items()):
        if kind in ("job", "company", "resume") and not full:
            step = max(1, len(paths) // sample)
            urls += paths[::step][:sample]
        elif kind in ("blog", "profession", "jobs") and not full:
            urls += paths[:sample]
        else:
            urls += paths
    return list(dict.fromkeys(urls))


def db_coverage() -> int:
    """Проверить, что каждое значение из базы переводится на все языки сайта.

    Краулер каждый день приносит новые страны, теги и форматы. Без этой проверки
    новая страна тихо остаётся русской на всех одиннадцати версиях — ровно так
    на сайт попали «Кения», «ОАЭ» и «Остров Мэн».
    """
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from server import terms
    from server.app import Job, SessionLocal, country_of

    session = SessionLocal()
    try:
        rows = session.query(Job.location, Job.fmt, Job.category, Job.tags,
                             Job.salary).filter(Job.status == "approved").all()
    finally:
        session.close()

    # каждое поле переводится своей функцией — проверяем ровно то, что увидит
    # посетитель, а не «как если бы всё шло через общий словарь»
    values = Counter()
    for location, fmt, category, tags, salary in rows:
        values[("country", country_of(location or ""))] += 1
        if location:
            values[("location", location)] += 1
        for field, value in (("term", fmt), ("term", category), ("salary", salary)):
            if value:
                values[(field, value)] += 1
        for value in (tags or "").split(","):
            if value.strip():
                values[("term", value.strip())] += 1

    def rendered(field: str, value: str, lang: str) -> str:
        if field == "salary":
            return terms.salary_label(value, lang)
        if field == "location":
            return terms.translate_terms(terms.location_label(value, lang), lang)
        return terms.translate_terms(value, lang)

    gaps = Counter()
    for (field, value), count in values.items():
        if not CYR_RE.search(value):
            continue
        for lang in LATIN_LANGS:
            if CYR_RE.search(rendered(field, value, lang)):
                gaps[(field, value)] = count
                break

    print("=" * 72)
    print("ПОКРЫТИЕ СЛОВАРЁМ: значения базы, остающиеся русскими на латинских версиях")
    print("=" * 72)
    print(f"вакансий: {len(rows)} · различных значений: {len(values)} · без перевода: {len(gaps)}")
    for (field, value), count in gaps.most_common(80):
        print(f"    {count:6d}  [{field}] {value!r}")
    if gaps:
        print("\nСлова площадки — в server/terms.py (страны — в scripts/build_geo_terms.py).")
        print("Мусор вида «в USDT» или «ТОЛЬКО ОФИС» — это плохой разбор источника,")
        print("его чинят в краулере, а не словарём.")
    return 1 if gaps else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--langs", default=",".join(ALL_LANGS))
    ap.add_argument("--sample", type=int, default=12, help="страниц каждого типа")
    ap.add_argument("--full", action="store_true", help="все вакансии и компании")
    ap.add_argument("--json", dest="json_out", default="")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--max-report", type=int, default=25)
    ap.add_argument("--from-db", action="store_true",
                    help="без запросов к сайту: покрытие значений базы словарём")
    args = ap.parse_args()
    if args.from_db:
        return db_coverage()

    langs = [x.strip() for x in args.langs.split(",") if x.strip()]
    groups = sitemap_paths(args.base)
    paths = pick(groups, args.sample, args.full)
    print(f"страниц: {len(paths)} · языков: {len(langs)} · запросов: {len(paths) * (len(langs) + 1)}",
          file=sys.stderr)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        ru_pages = dict(zip(paths, pool.map(lambda p: fetch(args.base + p), paths)))
        ru_sets = {p: set(strings_of(h)) for p, h in ru_pages.items()}

        by_lang, by_string = {}, defaultdict(Counter)
        where = defaultdict(set)
        broken = 0
        for lang in langs:
            pages = dict(zip(paths, pool.map(
                lambda p, l=lang: fetch(f"{args.base}/{l}{'' if p == '/' else p}"), paths)))
            total = Counter()
            for path, html in pages.items():
                if html.startswith("<!--fetch-error"):
                    # молча зачесть страницу как чистую — худший вид зелёного отчёта
                    print(f"    не открылась /{lang}{path}: {html[:80]}", file=sys.stderr)
                    broken += 1
                    continue
                for value in leaks_for(lang, html, ru_sets[path]):
                    total[value] += 1
                    by_string[lang][value] += 1
                    if len(where[(lang, value)]) < 3:
                        where[(lang, value)].add(f"/{lang}{path}")
            by_lang[lang] = total
            print(f"  {lang}: {sum(total.values())} утечек, {len(total)} уникальных строк",
                  file=sys.stderr)

    print("\n" + "=" * 72)
    print("АУДИТ ЯЗЫКОВЫХ ВЕРСИЙ")
    print("=" * 72)
    grand = 0
    for lang in langs:
        total = by_lang[lang]
        grand += sum(total.values())
        mark = "OK " if not total else "ПЛОХО"
        print(f"\n{mark} /{lang}/ — {sum(total.values())} утечек, {len(total)} уникальных")
        for value, count in total.most_common(args.max_report):
            sample_url = sorted(where[(lang, value)])[0] if where[(lang, value)] else ""
            print(f"    {count:5d}  {value[:90]!r}  {sample_url}")
        if len(total) > args.max_report:
            print(f"    … ещё {len(total) - args.max_report} строк")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump({lang: dict(c.most_common()) for lang, c in by_string.items()},
                      fh, ensure_ascii=False, indent=1)
        print(f"\nотчёт: {args.json_out}")
    if broken:
        print(f"\nНЕ ОТКРЫЛИСЬ: {broken} страниц — отчёт неполный")
    print(f"\nВСЕГО: {grand}")
    return 1 if grand or broken else 0


if __name__ == "__main__":
    sys.exit(main())
