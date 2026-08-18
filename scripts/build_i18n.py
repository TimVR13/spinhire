#!/usr/bin/env python3
"""Build complete client-side RU -> UK/EN dictionaries for public site copy."""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("uk", "en")
SKIP_FILES = {"brand-board.html", "logo-concepts.html", "logo-round3.html"}
SKIP_TEMPLATES = {"admin.html", "admin_edit.html"}
SKIP_SELECTOR = ".job-card, .job-body, [data-no-translate]"
CYRILLIC = re.compile(r"[А-Яа-яЁё]")
QUOTED = re.compile(r"(?P<quote>['\"`])(?P<value>[^'\"`\n]*[А-Яа-яЁё][^'\"`\n]*)\1")
SPLIT = "\n__SPINHIRE_TRANSLATION_SPLIT__\n"


def is_copy(value: str) -> bool:
    value = " ".join(value.split())
    return bool(value and CYRILLIC.search(value) and "{{" not in value and "{%" not in value)


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
        value = " ".join(value.split())
        if is_copy(value):
            strings.add(value)
    for element in soup.select("[placeholder], [aria-label], [title], meta[content]"):
        for attribute in ("placeholder", "aria-label", "title", "content"):
            value = " ".join((element.get(attribute) or "").split())
            if is_copy(value):
                strings.add(value)
    if soup.title and soup.title.string:
        value = " ".join(soup.title.string.split())
        if is_copy(value):
            strings.add(value)


def collect_strings() -> list[str]:
    strings: set[str] = set()
    for path in ROOT.glob("*.html"):
        if path.name not in SKIP_FILES:
            collect_html(path, strings)
    for path in (ROOT / "server" / "templates").glob("*.html"):
        if path.name not in SKIP_TEMPLATES:
            collect_html(path, strings)
    for path in (ROOT / "js").glob("*.js"):
        if path.name in {"legal-pages.js"}:
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
    query = SPLIT.join(values)
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


def build(strings: list[str], target: str) -> dict[str, str]:
    result: dict[str, str] = {}
    work = list(batches(strings))
    for index, batch in enumerate(work, 1):
        for attempt in range(3):
            try:
                translated = translate_batch(batch, target)
                result.update(zip(batch, translated))
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(1.5 * (attempt + 1))
        print(f"{target}: batch {index}/{len(work)}")
        time.sleep(0.15)
    return result


def main() -> None:
    strings = collect_strings()
    print(f"Collected {len(strings)} public UI strings")
    output_dir = ROOT / "js"
    output_dir.mkdir(exist_ok=True)
    for target in TARGETS:
        dictionary = build(strings, target)
        output = output_dir / f"i18n-{target}.json"
        output.write_text(json.dumps(dictionary, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"Wrote {output.relative_to(ROOT)} ({len(dictionary)} entries)")


if __name__ == "__main__":
    main()
