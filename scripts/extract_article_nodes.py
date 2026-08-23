"""Достаёт переводимые текстовые узлы статей блога.

Языковой слой сайта подменяет текст по точному совпадению узла, поэтому
для перевода статьи достаточно словаря «исходная строка → перевод».

    python3 scripts/extract_article_nodes.py           # все статьи
    python3 scripts/extract_article_nodes.py post-vip-manager.html
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = re.compile(r"<script.*?</script>|<style.*?</style>|<head>.*?</head>", re.S)


def nodes_of(path: str):
    html = open(path, encoding="utf-8").read()
    body = SKIP.sub("", html)
    out, seen = [], set()
    # <title> живёт в <head>, который вырезан из body: без него языковые версии
    # отдавали половину заголовка вкладки по-русски
    title = re.search(r"<title>([^<]+)</title>", html)
    if title:
        text = " ".join(title.group(1).split())
        if re.search(r"[А-Яа-я]", text):
            seen.add(text)
            out.append(text)
    for raw in re.findall(r">([^<>]{8,400})<", body):
        text = " ".join(raw.split())
        if not re.search(r"[А-Яа-я]", text) or text in seen:
            continue
        seen.add(text)
        out.append(text)
    # атрибуты, которые видит пользователь и поисковик
    for attr in re.findall(r'(?:content|alt|title|placeholder)="([^"]{15,300})"', html):
        text = " ".join(attr.split())
        if re.search(r"[А-Яа-я]", text) and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def main():
    files = sys.argv[1:]
    if not files:
        files = sorted(f for f in os.listdir(ROOT)
                       if f.startswith("post-") and f.endswith(".html") and f != "post-job.html")
    result = {}
    for name in files:
        for text in nodes_of(os.path.join(ROOT, name)):
            result.setdefault(text, "")
    json.dump(result, sys.stdout, ensure_ascii=False, indent=1)
    print(f"\n# строк: {len(result)}", file=sys.stderr)


if __name__ == "__main__":
    main()
