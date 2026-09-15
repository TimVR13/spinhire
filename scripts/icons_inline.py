#!/usr/bin/env python3
"""Синхронизирует единый SVG-набор img/icons.svg во все страницы, где он лежит инлайном
между маркерами <!-- sh-icons --> … <!-- /sh-icons --> (статические HTML и base.html).
Запуск после правки img/icons.svg:  python3 scripts/icons_inline.py
Иконка в разметке: <svg class="ico" aria-hidden="true"><use href="#i-имя"/></svg>."""
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FILES = ['index.html', 'games.html', 'jobs.html', 'employer.html', 'server/templates/base.html',
         *sorted(p.name for p in ROOT.glob('jobs-*.html'))]
MARK_RE = re.compile(r'<!-- sh-icons.*?<!-- /sh-icons -->\n?', re.S)


def block() -> str:
    svg = (ROOT / 'img/icons.svg').read_text().strip()
    return ('<!-- sh-icons: единый SVG-набор, источник img/icons.svg; обновлять scripts/icons_inline.py -->\n'
            + svg + '\n<!-- /sh-icons -->\n')


def main() -> int:
    blk = block(); changed = 0
    for rel in FILES:
        p = ROOT / rel
        if not p.exists():
            continue
        text = p.read_text()
        if MARK_RE.search(text):
            new = MARK_RE.sub(lambda m: blk, text)
        else:
            m = re.search(r'<body[^>]*>\n?', text)
            if not m:
                print('нет <body>:', rel); continue
            new = text[:m.end()] + blk + text[m.end():]
        if new != text:
            p.write_text(new); changed += 1; print('обновлён', rel)
    print(f'готово: {changed} файлов; символов в спрайте: {blk.count("<symbol")}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
