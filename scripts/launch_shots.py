#!/usr/bin/env python3
"""Скриншоты для галереи Product Hunt и других каталогов.

    pip install playwright && playwright install chromium
    python3 scripts/launch_shots.py                      # 6 кадров в img/press/launch/
    python3 scripts/launch_shots.py --list               # что снимается
    python3 scripts/launch_shots.py --only hero,api      # только выбранные кадры
    python3 scripts/launch_shots.py --base http://127.0.0.1:8000 --no-caption

Снимает английскую версию сайта в размере галереи Product Hunt (1270×760, по
умолчанию в двойном разрешении) и впечатывает подпись прямо в кадр шрифтами
сайта. Снимать только после деплоя: на проде должны быть свежие тексты.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = "https://spinhire.io"
DEFAULT_OUT = ROOT / "img" / "press" / "launch"
WIDTH, HEIGHT = 1270, 760

# Порядок кадров = порядок галереи. Первый кадр видно в ленте — он решает больше всех.
SHOTS = [
    {
        "key": "hero",
        "path": "/en/",
        "scroll": 130,  # чтобы живые счётчики попали в кадр целиком
        "caption": "6,000+ live iGaming jobs, refreshed every 6 hours",
    },
    {
        "key": "jobs",
        "path": "/en/jobs",
        "caption": "Filters the industry actually needs: vertical, licence, languages, relocation, crypto pay",
    },
    {
        "key": "market",
        "path": "/en/market",
        "scroll": 150,
        "caption": "Public labour-market data with methodology and a monthly archive",
    },
    {
        "key": "professions",
        "path": "/en/professions",
        "scroll": 200,
        "caption": "35 profession cards with salary bands by seniority and region",
    },
    {
        "key": "api",
        "path": "/api/jobs?limit=3",
        "caption": "The whole index as an open API — no key, CC BY 4.0",
    },
    {
        "key": "employers",
        "path": "/en/post-job",
        "scroll": 320,
        "caption": "For employers: structured posting, salary range required, mini-ATS",
    },
]

# Подпись живёт в самой странице: так она наследует шрифты и цвета сайта,
# а не подставной системный шрифт из графического редактора.
CAPTION_JS = """
(caption) => {
  document.querySelectorAll('.sh-shot-caption').forEach((n) => n.remove());
  const bar = document.createElement('div');
  bar.className = 'sh-shot-caption';
  bar.textContent = caption;
  Object.assign(bar.style, {
    position: 'fixed', left: '0', right: '0', bottom: '0', zIndex: '2147483647',
    padding: '22px 40px', boxSizing: 'border-box',
    font: '600 25px/1.25 "Golos Text", system-ui, sans-serif', letterSpacing: '-0.01em',
    color: '#00120A', textAlign: 'center',
    background: 'linear-gradient(90deg, #00E297 0%, #00E297 55%, #FE38AD 100%)',
    boxShadow: '0 -18px 44px rgba(0,0,0,.55)',
  });
  (document.documentElement || document.body).appendChild(bar);
}
"""

# Мелочи, которые портят кадр: баннер согласия, фокус в поле поиска, прокрутка.
CLEANUP_JS = """
(scroll) => {
  document.querySelectorAll('.consent-banner, [data-cookie-banner], .cookie-banner, #cookie')
    .forEach((n) => n.remove());
  if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  window.scrollTo(0, scroll || 0);
}
"""

# Согласие на аналитику ставим заранее: иначе баннер закрывает низ первого кадра.
CONSENT_JS = """
try {
  localStorage.setItem('spinhireConsent', 'denied');
  document.cookie = 'spinhire_consent=denied; Max-Age=31536000; Path=/; SameSite=Lax';
} catch (e) {}
"""


def chromium_path(explicit: str = "") -> str:
    """Свой бинарь Chromium: в CI и в облачных песочницах он уже стоит рядом."""
    for candidate in (explicit, os.environ.get("PLAYWRIGHT_CHROMIUM_PATH", ""),
                      "/opt/pw-browsers/chromium"):
        if candidate and Path(candidate).exists():
            return candidate
    return ""


# В песочницах и CI трафик идёт через прокси, который рвёт соединение на TLS 1.3
# с ECH — браузеру эти возможности не нужны, а без них тоннель живёт.
PROXY_SAFE_ARGS = ["--disable-features=EncryptedClientHello,AsyncDns", "--ssl-version-max=tls1.2"]


def build(base: str, out_dir: Path, keys: list[str], caption: bool, scale: int, dark: bool,
          chromium: str = "", use_proxy: bool = True) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("нужен playwright: pip install playwright && playwright install chromium", file=sys.stderr)
        return 1

    shots = [s for s in SHOTS if not keys or s["key"] in keys]
    if not shots:
        print(f"нет таких кадров: {', '.join(keys)}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    base = base.rstrip("/")
    made = []
    with sync_playwright() as pw:
        exe = chromium_path(chromium)
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
        launch: dict = {"args": ["--no-sandbox"]}
        if exe:
            launch["executable_path"] = exe
        if use_proxy and proxy and not base.startswith(("http://127.0.0.1", "http://localhost")):
            launch["proxy"] = {"server": proxy}
            launch["args"] += PROXY_SAFE_ARGS
        browser = pw.chromium.launch(**launch)
        context = browser.new_context(
            viewport={"width": WIDTH, "height": HEIGHT},
            device_scale_factor=scale,
            locale="en-US",
            color_scheme="dark" if dark else "light",
        )
        # тема сайта хранится в localStorage: тёмная — дефолт, светлую ставим явно
        context.add_init_script(
            "try{localStorage.setItem('themeV2', %s)}catch(e){}" % ("'dark'" if dark else "'light'")
        )
        context.add_init_script(CONSENT_JS)
        page = context.new_page()
        for shot in shots:
            url = f"{base}{shot['path']}"
            try:
                page.goto(url, wait_until="networkidle", timeout=60_000)
            except Exception as e:
                print(f"  ✗ {shot['key']}: не открылось {url} ({type(e).__name__})", file=sys.stderr)
                continue
            page.wait_for_timeout(1200)  # ленивые картинки и счётчики
            page.evaluate(CLEANUP_JS, shot.get("scroll", 0))
            page.wait_for_timeout(500)  # прокрутка успевает перерисовать липкую шапку
            if caption:
                page.evaluate(CAPTION_JS, shot["caption"])
                page.wait_for_timeout(150)
            # номер = место кадра в галерее, а не в этом запуске: с --only имена не разъезжаются
            target = out_dir / f"{SHOTS.index(shot) + 1:02d}-{shot['key']}.png"
            page.screenshot(path=str(target))
            made.append(target)
            print(f"  ✓ {target.relative_to(ROOT)}  ←  {url}")
        browser.close()
    if not made:
        print("ни одного кадра не снято", file=sys.stderr)
        return 1
    print(f"\n{len(made)} кадр(ов) в {out_dir.relative_to(ROOT)}, "
          f"{WIDTH * scale}×{HEIGHT * scale} px (галерея Product Hunt ждёт минимум {WIDTH}×{HEIGHT})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=DEFAULT_BASE, help=f"адрес сайта (по умолчанию {DEFAULT_BASE})")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="куда складывать PNG")
    ap.add_argument("--only", default="", help="список кадров через запятую")
    ap.add_argument("--list", action="store_true", help="показать список кадров и выйти")
    ap.add_argument("--no-caption", action="store_true", help="снять без подписи в кадре")
    ap.add_argument("--scale", type=int, default=2, choices=(1, 2), help="множитель разрешения")
    ap.add_argument("--light", action="store_true", help="светлая тема сайта вместо тёмной")
    ap.add_argument("--chromium", default="", help="путь к бинарю Chromium, если playwright install не делали")
    ap.add_argument("--no-proxy", action="store_true", help="не отдавать браузеру HTTPS_PROXY из окружения")
    args = ap.parse_args()

    if args.list:
        for i, s in enumerate(SHOTS, 1):
            print(f"{i}. {s['key']:<12} {s['path']:<18} {s['caption']}")
        return 0

    keys = [k.strip() for k in args.only.split(",") if k.strip()]
    return build(args.base, Path(args.out), keys, not args.no_caption, args.scale, not args.light,
                 args.chromium, not args.no_proxy)


if __name__ == "__main__":
    raise SystemExit(main())
