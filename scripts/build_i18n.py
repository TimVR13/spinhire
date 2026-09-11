#!/usr/bin/env python3
"""Собрать словари интерфейса: русский оригинал → все языки сайта.

Строки берём из шаблонов, статических страниц и скриптов — то есть из того,
что реально видит посетитель. Тексты статей сюда не входят: они лежат в
server/i18n/<код>.articles.json и переводятся отдельно.

    python3 scripts/build_i18n.py            # все языки сайта
    python3 scripts/build_i18n.py de pl      # только эти

Словари ложатся в server/i18n/<код>.ui.json и подхватываются сервером и
клиентом из одного места (роут /js/i18n-<код>.js).
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("en", "de", "pl", "fr", "es", "pt", "it", "el", "ro", "bg", "uk")
SKIP_FILES = {"brand-board.html", "logo-concepts.html", "logo-round3.html"}
SKIP_TEMPLATES = {"admin.html", "admin_edit.html"}
SKIP_SELECTOR = ".job-card, .job-body, [data-no-translate]"
CYRILLIC = re.compile(r"[А-Яа-яЁё]")
QUOTED = re.compile(r"(?P<quote>['\"`])(?P<value>[^'\"`\n]*[А-Яа-яЁё][^'\"`\n]*)\1")
SPLIT = "\n__SPINHIRE_TRANSLATION_SPLIT__\n"

# Названия языков остаются на языке оригинала: машинный перевод переворачивал
# «Українська» в «Русский» и ломал переключатель языка в футере.
LANGUAGE_NAMES = {
    "Русский", "Українська", "Російська", "Українською", "Английский",
    "Украинский", "Русском",
}


JINJA_TAG = re.compile(r"{%.*?%}", re.S)
JINJA_VAR = re.compile(r"{{.*?}}", re.S)
JINJA_COMMENT = re.compile(r"{#.*?#}", re.S)


def is_copy(value: str) -> bool:
    value = " ".join(value.split())
    if value in LANGUAGE_NAMES:
        return False
    return bool(value and CYRILLIC.search(value) and "{{" not in value and "{%" not in value)


def copy_variants(value: str):
    """Кусок шаблона → видимые строки, где подстановка заменена на «#».

    «Вакансии iGaming — {{ total }} живых вакансий» уезжает в словарь как
    «Вакансии iGaming — # живых вакансий»: число подставит сервер. Без этого
    все заголовки со счётчиком оставались русскими на каждой языковой версии.
    """
    for chunk in JINJA_TAG.split(JINJA_COMMENT.sub(" ", value)):
        text = " ".join(JINJA_VAR.sub("#", chunk).split())
        # остатки кода шаблона («'Операции казино': '<svg…») в словарь не берём
        if "{" in text or "}" in text or "': '" in text:
            continue
        if text and CYRILLIC.search(text) and text.strip("#·—-|, "):
            yield text


def collect_html(path: Path, strings: set[str]) -> None:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    for element in soup.select(SKIP_SELECTOR):
        element.decompose()
    for element in soup.select("script, style"):
        if element.name == "script" and element.string:
            for match in QUOTED.finditer(element.string):
                value = " ".join(match.group("value").split())
                if is_copy(value):
                    strings.add(value)
        element.decompose()
    for value in soup.stripped_strings:
        for variant in copy_variants(value):
            strings.add(variant)
    for element in soup.select("[placeholder], [aria-label], [title], meta[content]"):
        for attribute in ("placeholder", "aria-label", "title", "content"):
            value = " ".join((element.get(attribute) or "").split())
            if is_copy(value):
                strings.add(value)
    if soup.title and soup.title.string:
        for variant in copy_variants(soup.title.string):
            strings.add(variant)


def collect_json(path: Path, strings: set[str]) -> None:
    """Русский текст из справочников (data/professions.json) — это тоже витрина.

    Картотека профессий живёт в JSON, а не в шаблоне, поэтому в словарь она не
    попадала: 35 страниц на девяти языках оставались полностью русскими.
    """
    def walk(node) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str) and is_copy(node):
            strings.add(" ".join(node.split()))

    try:
        walk(json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:                                    # noqa: BLE001
        print(f"{path.name}: пропущен ({exc})")


def collect_strings() -> list[str]:
    strings: set[str] = set()
    collect_json(ROOT / "data" / "professions.json", strings)
    for path in ROOT.glob("*.html"):
        # post-*.html — тексты статей, у них свои словари <код>.articles.json
        if path.name not in SKIP_FILES and not path.name.startswith("post-"):
            collect_html(path, strings)
    for path in (ROOT / "server" / "templates").glob("*.html"):
        if path.name not in SKIP_TEMPLATES:
            collect_html(path, strings)
    for path in (ROOT / "js").glob("*.js"):
        if path.name in {"legal-pages.js"} or path.name.startswith("i18n-"):
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        for match in QUOTED.finditer(source):
            value = " ".join(match.group("value").split())
            if is_copy(value):
                strings.add(value)
    return sorted(strings, key=lambda value: (len(value), value))


def batches(strings: list[str], max_chars: int = 2800):
    batch: list[str] = []
    size = 0
    for value in strings:
        addition = len(value) + len(SPLIT)
        if batch and size + addition > max_chars:
            yield batch
            batch, size = [], 0
        batch.append(value)
        size += addition
    if batch:
        yield batch


def translate_batch(values: list[str], target: str) -> list[str]:
    query = SPLIT.join(hint_source(value) for value in values)
    params = urllib.parse.urlencode({"client": "gtx", "sl": "ru", "tl": target, "dt": "t", "q": query})
    request = urllib.request.Request(
        "https://translate.googleapis.com/translate_a/single?" + params,
        headers={"User-Agent": "SpinHire-i18n-builder/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read())
    translated = "".join(part[0] for part in payload[0]).split(SPLIT)
    if len(translated) != len(values):
        raise RuntimeError(f"Translation split failed: {len(values)} inputs, {len(translated)} outputs")
    return [" ".join(value.split()) for value in translated]


# Машинный переводчик не знает нашего словаря: «вакансия» он переводит как
# vacancy, а борд везде говорит job. Правим термины в переводе, не в оригинале.
TERMINOLOGY = {
    "en": [(r"\bvacanc(y|ies)\b", lambda m: "job" if m.group(1) == "y" else "jobs"),
           (r"\bbread crumbs\b", "breadcrumbs"),
           (r"\bCV database\b", "resume database")],
    "de": [(r"\bVakanz(en)?\b", lambda m: "Jobs" if m.group(1) else "Job")],
    "pl": [(r"\bwakat(y|ów)?\b", lambda m: "oferty pracy" if m.group(1) else "oferta pracy")],
    "fr": [(r"\bvacance(s)?\b", lambda m: "offres d’emploi" if m.group(1) else "offre d’emploi")],
    "es": [(r"\bvacante(s)?\b", lambda m: "empleos" if m.group(1) else "empleo")],
    "pt": [(r"\bvaga(s)?\b", lambda m: "vagas" if m.group(1) else "vaga")],
    "it": [(r"\bposto vacante\b", "offerta di lavoro")],
}


# Отраслевой сленг машинный переводчик понимает буквально: «вилка» становится
# fork, «картотека» — card index, «грейд» — grade. Правим ИСХОДНИК перед
# отправкой (ключ словаря остаётся прежним) — тогда выигрывают все языки сразу,
# а не только тот, чей перевод мы смогли вычитать.
SOURCE_HINTS = [
    (r"\bВилки\b", "Диапазоны зарплат"), (r"\bвилки\b", "диапазоны зарплат"),
    (r"\bВилка\b", "Диапазон зарплаты"), (r"\bвилка\b", "диапазон зарплаты"),
    (r"\bвилку\b", "диапазон зарплаты"), (r"\bвилке\b", "диапазоне зарплаты"),
    (r"\bвилкой\b", "диапазоном зарплаты"), (r"\bвилках\b", "диапазонах зарплат"),
    (r"\bКартотека\b", "Справочник"), (r"\bкартотека\b", "справочник"),
    (r"\bкартотеки\b", "справочника"), (r"\bкартотеке\b", "справочнике"),
    (r"\bкартотеку\b", "справочник"),
    (r"\bГрейд\b", "Уровень"), (r"\bгрейд\b", "уровень"),
    (r"\bгрейда\b", "уровня"), (r"\bгрейды\b", "уровни"),
    (r"\bгрейдам\b", "уровням"), (r"\bгрейдах\b", "уровнях"),
    (r"\bЖивая база\b", "Живая база данных"),
]


def hint_source(value: str) -> str:
    """Русский оригинал → однозначный русский для машинного переводчика."""
    for pattern, replacement in SOURCE_HINTS:
        value = re.sub(pattern, replacement, value)
    return value


def needs_hint(value: str) -> bool:
    return any(re.search(pattern, value) for pattern, _ in SOURCE_HINTS)


def fix_terminology(value: str, target: str) -> str:
    for pattern, replacement in TERMINOLOGY.get(target, ()):
        value = re.sub(pattern, replacement, value, flags=re.I)
    # переводчик иногда съедает пробел вокруг подстановки: «#Employers Hiring»
    value = re.sub(r"#(?=[^\W\d_])", "# ", value)
    return re.sub(r"(?<=[^\W\d_])#", " #", value)


def build(strings: list[str], target: str) -> dict[str, str]:
    result: dict[str, str] = {}
    work = list(batches(strings))
    for index, batch in enumerate(work, 1):
        for attempt in range(3):
            try:
                translated = translate_batch(batch, target)
                result.update(zip(batch, (fix_terminology(v, target) for v in translated)))
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(1.5 * (attempt + 1))
        print(f"{target}: batch {index}/{len(work)}")
        time.sleep(0.15)
    return result


def main() -> None:
    targets = [x for x in sys.argv[1:] if not x.startswith("-")] or list(TARGETS)
    unknown = [x for x in targets if x not in TARGETS]
    if unknown:
        raise SystemExit(f"неизвестный язык: {unknown}")
    strings = collect_strings()
    print(f"строк интерфейса: {len(strings)}")
    output_dir = ROOT / "server" / "i18n"
    output_dir.mkdir(exist_ok=True)
    for target in targets:
        output = output_dir / f"{target}.ui.json"
        # уже переведённое не переводим заново: правки руками не затираются,
        # а повторный запуск после новой страницы стоит один-два батча
        existing = {}
        if output.exists():
            existing = json.loads(output.read_text(encoding="utf-8"))
        # строки с отраслевым сленгом переводим заново: прошлые сборки шли без
        # подсказок и оставили в словаре «fork» вместо «range»
        fresh = [value for value in strings
                 if value not in existing or needs_hint(value)]
        print(f"{target}: {len(fresh)} новых из {len(strings)}")
        if fresh:
            existing.update(build(fresh, target))
        # выпавшие из вёрстки строки не тащим дальше; термины правим и в старых
        # переводах — иначе «вакансия» так и останется vacancy с прошлых сборок
        dictionary = {key: fix_terminology(existing[key], target)
                      for key in strings if key in existing}
        output.write_text(json.dumps(dictionary, ensure_ascii=False, indent=1,
                                     sort_keys=True) + "\n", encoding="utf-8")
        print(f"{output.relative_to(ROOT)}: {len(dictionary)} строк")


if __name__ == "__main__":
    main()
