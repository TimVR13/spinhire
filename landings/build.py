#!/usr/bin/env python3
"""Генератор мини-лендингов для доменов холодной рассылки.

Домены spinrecruit.com / spinhires.com / spinhire.org — отдельные от основного
spinhire.io, чтобы репутация рассылки не задевала главный сайт. Пустой домен без
HTTPS — признак спамера для фильтров, поэтому на каждом стоит короткая карточка
проекта со ссылками на spinhire.io. Страницы noindex: они не должны конкурировать
с основным сайтом в поиске.

Запуск:  python3 landings/build.py   → landings/<домен>/index.html
Отдаёт их nginx-контейнер spinhire-landings (см. landings/conf.d/default.conf).
"""
from __future__ import annotations

import html
import pathlib
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent
REPO = ROOT.parent

MAIN = "https://spinhire.io"
GA_ID = "G-0W5XWDYPZ3"
CONTACT = "hello@spinhire.io"

LOGO_SVG = (REPO / "img" / "spinhire-slot.svg").read_text(encoding="utf-8").strip()
FAVICON = "data:image/svg+xml," + urllib.parse.quote(
    (REPO / "favicon.svg").read_text(encoding="utf-8").strip(), safe="/:=,#"
)

FONTS = (
    "https://fonts.googleapis.com/css2?family=Golos+Text:wght@400;500;600"
    "&family=Bricolage+Grotesque:opsz,wght@12..96,500..800&display=swap"
)

CSS = """
:root {
  --bg: oklch(0.145 0.012 170);
  --bg-deep: oklch(0.105 0.010 175);
  --surface: oklch(0.185 0.014 170);
  --line: oklch(0.31 0.018 170);
  --line-strong: oklch(0.49 0.022 170);
  --ink: oklch(0.96 0.005 285);
  --ink-dim: oklch(0.76 0.008 285);
  --ink-faint: oklch(0.64 0.008 285);
  --acid: oklch(0.80 0.19 162);
  --acid-deep: oklch(0.68 0.17 164);
  --on-acid: oklch(0.14 0.05 162);
  --pink: oklch(0.68 0.25 350);
  --font-display: "Bricolage Grotesque", "Golos Text", system-ui, sans-serif;
  --font-body: "Golos Text", system-ui, -apple-system, "Segoe UI", sans-serif;
  --radius: 14px;
  color-scheme: dark;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; min-height: 100dvh;
  font: 400 1rem/1.6 var(--font-body);
  color: var(--ink); background: var(--bg);
  background-image:
    radial-gradient(60rem 30rem at -10% -20%, oklch(0.80 0.19 162 / 0.16), transparent 60%),
    radial-gradient(40rem 26rem at 110% 110%, oklch(0.68 0.25 350 / 0.12), transparent 60%),
    linear-gradient(var(--bg), var(--bg-deep));
  background-attachment: fixed;
  display: flex; flex-direction: column;
}
a { color: inherit; text-decoration: none; }
a:focus-visible, button:focus-visible { outline: 2px solid var(--acid); outline-offset: 3px; border-radius: 6px; }
.wrap { width: min(100% - 2rem, 46rem); margin-inline: auto; }

.top { padding-block: 22px; }
.top .wrap { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.logo { display: inline-flex; align-items: center; gap: 10px; font: 800 1.35rem/1 var(--font-display); letter-spacing: -0.01em; }
.logo svg { width: 54px; height: 32px; flex: none; }
.logo b { color: var(--acid); font-weight: 800; }
.pill {
  display: inline-flex; align-items: center; gap: 8px; padding: 7px 12px 7px 10px;
  border: 1px solid var(--line-strong); border-radius: 999px;
  font-size: 0.86rem; font-weight: 500; color: var(--ink-dim); transition: border-color .2s, color .2s;
}
.pill::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--acid); box-shadow: 0 0 10px var(--acid); }
.pill:hover { border-color: var(--acid); color: var(--ink); }

main { flex: 1; }
.hero { padding-block: clamp(40px, 8vw, 88px) 40px; }
.kicker {
  margin: 0 0 14px; font: 600 0.8rem/1 var(--font-body); letter-spacing: 0.14em; text-transform: uppercase; color: var(--acid);
}
h1 {
  margin: 0 0 18px; font: 800 clamp(2.1rem, 6vw, 3.6rem)/1.04 var(--font-display);
  letter-spacing: -0.025em; text-wrap: balance; max-width: 16ch;
}
.lead { margin: 0; font-size: clamp(1.05rem, 1.6vw, 1.2rem); color: var(--ink-dim); max-width: 56ch; text-wrap: pretty; }
.lead strong { color: var(--ink); font-weight: 600; }
.en { margin: 14px 0 0; font-size: 0.92rem; color: var(--ink-faint); max-width: 60ch; }
.en a { color: var(--ink-dim); border-bottom: 1px solid var(--line-strong); }
.en a:hover { color: var(--ink); border-color: var(--ink); }

.cta { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 30px; }
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  padding: 13px 22px; border-radius: 12px; font-weight: 600; font-size: 1rem; line-height: 1.2;
  border: 1px solid transparent; transition: transform .18s cubic-bezier(.2,.9,.3,1.4), box-shadow .2s, background .2s, border-color .2s;
}
.btn:hover { transform: translateY(-2px); }
.btn:active { transform: translateY(0); }
.btn-primary { background: var(--acid); color: var(--on-acid); box-shadow: 0 8px 30px oklch(0.80 0.19 162 / 0.22); }
.btn-primary:hover { background: var(--acid-deep); box-shadow: 0 12px 34px oklch(0.80 0.19 162 / 0.3); }
.btn-ghost { border-color: var(--line-strong); color: var(--ink); background: oklch(1 0 0 / 0.02); }
.btn-ghost:hover { border-color: var(--ink-dim); background: oklch(1 0 0 / 0.05); }

.facts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; padding-block: 8px 40px; }
.fact {
  padding: 18px 18px 20px; background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);
  transition: border-color .2s, transform .2s;
}
.fact:hover { border-color: var(--line-strong); transform: translateY(-2px); }
.fact h2 { margin: 0 0 6px; font: 700 1.02rem/1.25 var(--font-display); letter-spacing: -0.01em; }
.fact p { margin: 0; font-size: 0.92rem; color: var(--ink-dim); }
.fact .n { display: block; margin-bottom: 12px; width: 30px; height: 4px; border-radius: 2px; background: linear-gradient(90deg, var(--acid), var(--pink)); }

.note {
  margin-block: 0 56px; padding: 20px 22px; border-radius: var(--radius);
  border: 1px dashed var(--line-strong); background: oklch(1 0 0 / 0.02);
}
.note h2 { margin: 0 0 8px; font: 700 1rem/1.3 var(--font-display); }
.note p { margin: 0; font-size: 0.95rem; color: var(--ink-dim); }
.note code { font: 600 0.92em var(--font-body); color: var(--ink); background: oklch(1 0 0 / 0.07); padding: 1px 7px; border-radius: 6px; }
.note a { color: var(--ink); border-bottom: 1px solid var(--line-strong); }
.note a:hover { border-color: var(--ink); }

footer { border-top: 1px solid var(--line); padding-block: 24px 34px; font-size: 0.9rem; color: var(--ink-faint); }
footer .wrap { display: flex; flex-wrap: wrap; gap: 8px 22px; align-items: center; justify-content: space-between; }
footer nav { display: flex; flex-wrap: wrap; gap: 6px 18px; }
footer nav a { color: var(--ink-dim); }
footer nav a:hover { color: var(--ink); }

@media (max-width: 720px) {
  .facts { grid-template-columns: 1fr; }
  .btn { width: 100%; }
  h1 { max-width: none; }
}
@media (prefers-reduced-motion: reduce) {
  .btn, .fact, .pill { transition: none; }
  .btn:hover, .fact:hover { transform: none; }
}
"""

# ── тексты по доменам ────────────────────────────────────────────────────────
FACTS_EMPLOYER = [
    ("Только iGaming", "Казино, беттинг, геймдев слотов, аффилейт-команды, платежи и антифрод. Никаких «менеджеров по всему»."),
    ("Люди, которых нет на LinkedIn", "Русскоязычные специалисты с Кипра, Мальты, из Польши, Грузии, Армении и на удалёнке."),
    ("Русский и английский", "Вакансии и резюме на двух языках, отклики приходят от тех, кто уже работает в индустрии."),
]
FACTS_BRAND = [
    ("Открытые зарплаты", "Вилка у вакансии видна сразу. Релокация, удалёнка и крипто-оплата помечены."),
    ("Компании индустрии", "Операторы, провайдеры игр, аффилейт-сети, платёжки: кто нанимает и что предлагает."),
    ("Карьера в iGaming", "Блог о профессиях, зарплатах и переезде: Кипр, Мальта, Варшава, Тбилиси."),
]

PAGES = {
    "spinrecruit.com": dict(
        title="SpinRecruit — подбор для iGaming-компаний | SpinHire",
        desc="Рекрутинговое направление SpinHire: находим специалистов для казино, беттинга и аффилейт-команд. Русскоязычный iGaming, Кипр, Мальта, Польша, удалёнка.",
        kicker="Подбор для iGaming-компаний",
        h1="Находим людей, которых нет на LinkedIn",
        lead=(
            "<strong>SpinRecruit</strong> — рекрутинговое направление SpinHire, джоб-борда для казино, беттинга "
            "и аффилейт-команд. Пишем работодателям напрямую и подбираем кандидатов из русскоязычного iGaming: "
            "Кипр, Мальта, Польша, Грузия, Армения, удалёнка."
        ),
        en="SpinRecruit is the recruiting arm of SpinHire, an iGaming job board. English site:",
        cta=[("Разместить вакансию", f"{MAIN}/post-job", "btn-primary"), ("Написать нам", f"mailto:{CONTACT}?subject=SpinRecruit", "btn-ghost")],
        facts=FACTS_EMPLOYER,
    ),
    "spinhires.com": dict(
        title="SpinHires — найм в iGaming для работодателей | SpinHire",
        desc="Витрина SpinHire для компаний: вакансии с открытыми зарплатами видят специалисты из казино, беттинга и аффилейтов. Тарифы, размещение, база резюме.",
        kicker="SpinHire для работодателей",
        h1="Нанимайте в iGaming быстрее",
        lead=(
            "<strong>SpinHires</strong> — витрина SpinHire для компаний. Вакансия с открытой зарплатой попадает "
            "к специалистам из казино, беттинга и аффилейтов, а отклики приходят от людей, которые уже работают "
            "в индустрии и понимают, что такое GGR, ретеншн и лицензия MGA."
        ),
        en="SpinHires is the employer side of SpinHire, an iGaming job board. English site:",
        cta=[("Тарифы и размещение", f"{MAIN}/post-job", "btn-primary"), ("Все вакансии", f"{MAIN}/jobs", "btn-ghost")],
        facts=FACTS_EMPLOYER,
    ),
    "spinhire.org": dict(
        title="SpinHire — работа в iGaming: казино, беттинг, аффилейты",
        desc="SpinHire — джоб-борд iGaming на русском и английском: вакансии в казино, беттинге, геймдеве и аффилейтах с открытыми зарплатами. Основной сайт — spinhire.io.",
        kicker="Работа в iGaming",
        h1="Джоб-борд для казино, беттинга и аффилейтов",
        lead=(
            "<strong>SpinHire</strong> — вакансии и резюме iGaming на русском и английском. Открытые зарплаты, "
            "релокация, удалёнка и крипто-оплата помечены прямо в карточке. Здесь короткая визитка проекта, "
            "сам сайт живёт на spinhire.io."
        ),
        en="SpinHire is an iGaming job board with open salaries. English site:",
        cta=[("Открыть spinhire.io", f"{MAIN}/", "btn-primary"), ("Работодателям", f"{MAIN}/post-job", "btn-ghost")],
        facts=FACTS_BRAND,
    ),
}


def utm(url: str, domain: str) -> str:
    if url.startswith("mailto:"):
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}utm_source={domain}&utm_medium=referral&utm_campaign=outreach-landing"


def render(domain: str, p: dict) -> str:
    e = html.escape
    links = lambda u: utm(u, domain)  # noqa: E731
    ctas = "".join(
        f'<a class="btn {cls}" href="{e(links(href))}">{e(label)}</a>' for label, href, cls in p["cta"]
    )
    facts = "".join(
        f'<div class="fact"><span class="n"></span><h2>{e(t)}</h2><p>{e(d)}</p></div>' for t, d in p["facts"]
    )
    nav = "".join(
        f'<a href="{e(links(href))}">{e(label)}</a>'
        for label, href in [
            ("Вакансии", f"{MAIN}/jobs"),
            ("Компании", f"{MAIN}/companies"),
            ("Блог", f"{MAIN}/blog.html"),
            ("Работодателям", f"{MAIN}/post-job"),
            ("Политика", f"{MAIN}/privacy.html"),
        ]
    )
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(p["title"])}</title>
<meta name="description" content="{e(p["desc"])}">
<meta name="robots" content="noindex">
<link rel="canonical" href="https://{domain}/">
<link rel="icon" href="{FAVICON}" type="image/svg+xml">
<meta property="og:type" content="website">
<meta property="og:site_name" content="SpinHire">
<meta property="og:title" content="{e(p["title"])}">
<meta property="og:description" content="{e(p["desc"])}">
<meta property="og:url" content="https://{domain}/">
<meta property="og:image" content="{MAIN}/img/og-cover.jpg?v=2">
<meta property="og:locale" content="ru_RU">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#0f1512">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}gtag('js',new Date());gtag('config','{GA_ID}');</script>
<style>{CSS}</style>
</head>
<body>
<header class="top">
  <div class="wrap">
    <a class="logo" href="{e(links(MAIN + '/'))}" aria-label="SpinHire — основной сайт">{LOGO_SVG}<span>spin<b>hire</b></span></a>
    <a class="pill" href="{e(links(MAIN + '/'))}">Основной сайт: spinhire.io</a>
  </div>
</header>

<main>
  <section class="hero wrap">
    <p class="kicker">{e(p["kicker"])}</p>
    <h1>{e(p["h1"])}</h1>
    <p class="lead">{p["lead"]}</p>
    <p class="en" lang="en">{e(p["en"])} <a href="{e(links(MAIN + '/en/'))}">spinhire.io/en</a></p>
    <div class="cta">{ctas}</div>
  </section>

  <section class="facts wrap" aria-label="Коротко о SpinHire">{facts}</section>

  <section class="note wrap">
    <h2>Получили от нас письмо?</h2>
    <p>Мы пишем только компаниям из iGaming, которые сейчас нанимают, с реального адреса на домене
    <code>{domain}</code>. Если письмо неактуально, ответьте одним словом <code>стоп</code>, и мы больше
    не напишем. Вопросы: <a href="mailto:{CONTACT}">{CONTACT}</a>.</p>
  </section>
</main>

<footer>
  <div class="wrap">
    <nav aria-label="Ссылки на spinhire.io">{nav}</nav>
    <span>© 2026 SpinHire · <a href="https://t.me/spinhire_ru" rel="noopener">Telegram</a> · <a href="https://www.linkedin.com/company/spinhirejob/" rel="noopener">LinkedIn</a></span>
  </div>
</footer>
</body>
</html>
"""


def main() -> None:
    for domain, page in PAGES.items():
        out = ROOT / domain / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render(domain, page), encoding="utf-8")
        print(f"{out.relative_to(REPO)}  {out.stat().st_size} bytes")


if __name__ == "__main__":
    main()
