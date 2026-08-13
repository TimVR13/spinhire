# -*- coding: utf-8 -*-
"""Генерация списка вакансий на jobs.html из data/jobs.csv.

Обновление вакансий:
  1) правишь data/jobs.csv (разделитель ;)
  2) python3 scripts/build_jobs.py
"""
import csv, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "data", "jobs.csv")
PAGE = os.path.join(ROOT, "jobs.html")

PALETTE = [
    ("var(--acid)", "var(--on-acid)"),
    ("var(--pink)", "var(--on-pink)"),
    ("var(--yellow)", "var(--on-yellow)"),
    ("var(--violet)", "white"),
    ("var(--surface-2)", "var(--acid)"),
    ("var(--surface-2)", "var(--pink)"),
    ("var(--surface-2)", "var(--yellow)"),
    ("var(--surface-2)", "white"),
]

ALERT_BOX = '''
      <div class="alert-box">
        <div>
          <b>⚡ Не обновляй страницу. Мы сами напишем.</b>
          <p>Новые вакансии по этим фильтрам — на почту или в Telegram.</p>
        </div>
        <form data-demo="Подписка оформлена — ждите в Telegram (демо)">
          <input class="input" type="email" placeholder="you@example.com" required aria-label="Email для подписки">
          <button class="btn btn-acid" type="submit">Подписаться</button>
        </form>
      </div>
'''

def initials(company):
    words = re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", company)
    if not words:
        return "??"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()

def tag_class(tag):
    t = tag.lower()
    if "релокац" in t: return "tag-yellow"
    if "крипт" in t or "usdt" in t: return "tag-pink"
    if any(k in t for k in ("удалён", "c1", "c2", "язык", "немецк", "шведск", "испанск", "нидерланд", "узбек")):
        return "tag-acid"
    return ""

def card(row, i):
    bg, fg = PALETTE[i % len(PALETTE)]
    tags = [t.strip() for t in row["tags"].split(",")][:3]
    tags_html = "".join(f'<span class="tag {tag_class(t)}">{t}</span>' for t in tags)
    sal = row["salary"].strip()
    has_money = any(c.isdigit() for c in sal)
    sal_html = (f'<span class="salary">{sal}</span>' if has_money
                else f'<span class="salary" style="color: var(--ink-faint); font-size: 0.9rem;">{sal}</span>')
    return f'''        <a class="job-card" href="{row["source_url"]}" target="_blank" rel="noopener nofollow">
          <div class="job-card__logo" style="background: {bg}; color: {fg};" aria-hidden="true">{initials(row["company"])}</div>
          <div>
            <h3 class="job-card__title">{row["title"]}</h3>
            <p class="job-card__meta"><b>{row["company"]}</b> · {row["location"]} · {row["format"]}</p>
            <div class="job-card__tags">{tags_html}</div>
          </div>
          <div class="job-card__side">
            {sal_html}
            <button class="save-btn" aria-label="Сохранить вакансию">♡</button>
            <span class="job-card__age">источник ↗</span>
          </div>
        </a>'''

with open(CSV, encoding="utf-8") as f:
    rows = list(csv.DictReader(f, delimiter=";"))

cards = [card(r, i) for i, r in enumerate(rows)]
block = ('<!-- JOBS:START (генерируется из data/jobs.csv скриптом scripts/build_jobs.py — руками не править) -->\n'
         '      <div class="jobs-list">\n' + "\n".join(cards[:4]) + '\n      </div>\n'
         + ALERT_BOX +
         '      <div class="jobs-list">\n' + "\n".join(cards[4:]) + '\n      </div>\n'
         '      <!-- JOBS:END -->')

s = open(PAGE, encoding="utf-8").read()

if "JOBS:START" in s:
    s = re.sub(r"<!-- JOBS:START.*?JOBS:END -->", block, s, flags=re.S)
else:
    start = s.index('<section aria-label="Результаты поиска">') + len('<section aria-label="Результаты поиска">')
    end = s.index('<nav class="pagination"')
    s = s[:start] + "\n      " + block + "\n\n      " + s[end:]

s = re.sub(r"По вашим фильтрам: <b>\d+</b>", f"По вашим фильтрам: <b>{len(rows)}</b>", s)
open(PAGE, "w", encoding="utf-8").write(s)
print(f"jobs.html обновлён: {len(rows)} вакансий из data/jobs.csv")
