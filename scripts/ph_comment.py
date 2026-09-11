"""Product Hunt из вашего Chrome: лента, чтение запуска и комментарии.

Запускается на машине оператора, а не на сервере: PH закрыт Cloudflare, и из дата-центра
страница не открывается вовсе — ни curl, ни headless Chromium челлендж не проходят. Ваш
обычный Chrome с домашнего IP проходит его молча.

Один раз — вход:
    python3 scripts/ph_comment.py --login
  Откроется Google Chrome. Залогиньтесь в Product Hunt как обычно (X, Google или email) —
  скрипт сам заметит вход и сохранит сессию в ~/.spinhire/ph-state.json (cookies + localStorage).
  Enter в терминале не нужен.

Дальше:
    python3 scripts/ph_comment.py --check                 # жива ли сессия, под кем
    python3 scripts/ph_comment.py --feed                  # сегодняшние запуски: имя, тэглайн, ссылка
    python3 scripts/ph_comment.py --read --url <ссылка>   # описание продукта и верхние комментарии
    python3 scripts/ph_comment.py --comment --url <ссылка> --text-file c.txt --dry
    python3 scripts/ph_comment.py --comment --url <ссылка> --text-file c.txt

`--dry` доводит до кнопки отправки, не нажимает её и кладёт скриншот в /tmp/ph-dry.png —
так видно, что именно уйдёт в тред. Без `--dry` комментарий публикуется и пишется в
data/ph-comments.json.

Вёрстка PH меняется без предупреждения. Если селектор не нашёлся, скрипт не гадает: он делает
скриншот и печатает, какие поля ввода на странице вообще есть, — по ним селектор чинится за минуту.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

SITE = "https://www.producthunt.com"
STATE = Path(os.environ.get("SPINHIRE_PH_STATE", os.path.expanduser("~/.spinhire/ph-state.json")))
LOG = Path(__file__).resolve().parent.parent / "data" / "ph-comments.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/140.0.0.0 Safari/537.36")

# поля ввода комментария: PH переставляет их от релиза к релизу, поэтому пробуем по очереди
COMMENT_BOXES = [
    "textarea[placeholder*='think' i]",
    "textarea[placeholder*='comment' i]",
    "textarea[name='body']",
    "div[contenteditable='true'][role='textbox']",
    "div[contenteditable='true']",
]
SUBMIT_BUTTONS = [
    "button[type='submit']:has-text('Comment')",
    "button:has-text('Comment')",
    "button:has-text('Post')",
    "button[type='submit']",
]


def pw():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("pip3 install playwright && python3 -m playwright install chromium")
    return sync_playwright


def _launch(p, headless: bool):
    """Настоящий Google Chrome: у голого Chromium Cloudflare челлендж не отпускает вовсе."""
    try:
        return p.chromium.launch(channel="chrome", headless=headless)
    except Exception:
        return p.chromium.launch(headless=headless)


def _ready(page, timeout_s: int = 60) -> bool:
    """Дождаться, пока Cloudflare отпустит страницу (заголовок «Just a moment…» уйдёт)."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        title = (page.title() or "").lower()
        if "moment" not in title and "verif" not in title and title:
            return True
        time.sleep(2)
    return False


def _me(page) -> str | None:
    """Ник залогиненного пользователя по ссылке на свой профиль, иначе None."""
    for selector in ("a[href^='/@']", "a[href*='/my/']", "[data-test='header-user-menu']"):
        node = page.locator(selector).first
        if node.count():
            href = node.get_attribute("href") or ""
            match = re.search(r"/@([\w.-]+)", href)
            return match.group(1) if match else "ok"
    return None


def login(timeout_min: int = 15):
    with pw()() as p:
        browser = _launch(p, headless=False)
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1440, "height": 900}, locale="en-US")
        page = ctx.new_page()
        page.goto(SITE, wait_until="domcontentloaded")
        print(f"Залогиньтесь в окне браузера. Жду до {timeout_min} мин…", flush=True)
        name, deadline = None, time.time() + timeout_min * 60
        while time.time() < deadline:
            if page.is_closed():
                sys.exit("окно закрыли до входа — сессия не сохранена")
            try:
                name = _me(page)
            except Exception:
                name = None
            if name:
                break
            time.sleep(2)
        if not name:
            browser.close()
            sys.exit("вход не выполнен — повторите --login")
        time.sleep(2)  # дать PH дописать cookies после редиректа
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(ctx.storage_state()))
        os.chmod(STATE, 0o600)
        print(f"сессия сохранена: {STATE} (пользователь {name})")
        browser.close()


def _context(p, headless=True):
    if not STATE.exists():
        sys.exit(f"нет сессии {STATE} — сначала --login")
    browser = _launch(p, headless=headless)
    ctx = browser.new_context(storage_state=json.loads(STATE.read_text()), user_agent=UA,
                              viewport={"width": 1440, "height": 900}, locale="en-US")
    return browser, ctx


def _open(page, url: str) -> bool:
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    if not _ready(page):
        print("Cloudflare не отпустил страницу — запустите без --headless и пройдите проверку руками",
              file=sys.stderr)
        return False
    time.sleep(2)
    return True


def check(headless: bool = True) -> bool:
    with pw()() as p:
        browser, ctx = _context(p, headless)
        page = ctx.new_page()
        name = _me(page) if _open(page, SITE) else None
        browser.close()
    print("сессия:", f"ок, пользователь {name}" if name else "РАЗЛОГИНЕНА — повторите --login")
    return bool(name)


def feed(limit: int, headless: bool = True) -> list[dict]:
    """Сегодняшняя лента: имя, тэглайн и ссылка на страницу запуска."""
    with pw()() as p:
        browser, ctx = _context(p, headless)
        page = ctx.new_page()
        if not _open(page, SITE):
            browser.close()
            return []
        rows, seen = [], set()
        for link in page.locator("a[href^='/products/'], a[href^='/posts/']").all():
            href = (link.get_attribute("href") or "").split("?")[0]
            title = " ".join((link.inner_text() or "").split())
            if not href or href in seen or not title:
                continue
            seen.add(href)
            rows.append({"name": title[:80], "url": SITE + href})
            if len(rows) >= limit:
                break
        browser.close()
    for row in rows:
        print(f"{row['name']}\n  {row['url']}")
    return rows


def read(url: str, headless: bool = True) -> str:
    """Текст страницы запуска: описание, комментарий мейкера и обсуждение — чтобы было о чём писать."""
    with pw()() as p:
        browser, ctx = _context(p, headless)
        page = ctx.new_page()
        if not _open(page, url):
            browser.close()
            return ""
        for _ in range(3):  # комментарии догружаются по мере прокрутки
            page.mouse.wheel(0, 4000)
            time.sleep(1)
        text = " ".join((page.inner_text("body") or "").split("\n"))
        browser.close()
    print(text[:8000])
    return text


def comment(url: str, text: str, dry: bool, headless: bool = True) -> dict:
    with pw()() as p:
        browser, ctx = _context(p, headless)
        page = ctx.new_page()
        if not _open(page, url):
            browser.close()
            return {"ok": False, "error": "cloudflare"}
        if not _me(page):
            browser.close()
            return {"ok": False, "error": "session expired — run --login"}
        page.mouse.wheel(0, 2500)
        time.sleep(2)
        box = next((page.locator(sel).first for sel in COMMENT_BOXES if page.locator(sel).count()), None)
        if box is None:
            page.screenshot(path="/tmp/ph-nobox.png", full_page=True)
            fields = {sel: page.locator(sel).count() for sel in ("textarea", "div[contenteditable='true']", "input")}
            browser.close()
            return {"ok": False, "error": f"поле комментария не найдено; поля на странице: {fields}; "
                                          "скриншот /tmp/ph-nobox.png"}
        box.click()
        box.type(text, delay=8)
        time.sleep(1)
        if dry:
            page.screenshot(path="/tmp/ph-dry.png", full_page=True)
            browser.close()
            return {"ok": True, "dry": True, "screenshot": "/tmp/ph-dry.png"}
        button = next((page.locator(sel).first for sel in SUBMIT_BUTTONS if page.locator(sel).count()), None)
        if button is None:
            page.screenshot(path="/tmp/ph-nobutton.png", full_page=True)
            browser.close()
            return {"ok": False, "error": "кнопка отправки не найдена; скриншот /tmp/ph-nobutton.png"}
        button.click()
        time.sleep(4)
        posted = text.split("\n")[0][:40] in (page.inner_text("body") or "")
        if not posted:
            page.screenshot(path="/tmp/ph-fail.png", full_page=True)
        browser.close()
        return {"ok": posted, "url": url,
                **({} if posted else {"error": "комментарий не появился в треде; скриншот /tmp/ph-fail.png"})}


def log(entry: dict):
    rows = json.load(open(LOG, encoding="utf-8")) if LOG.exists() else []
    rows.append(entry)
    LOG.parent.mkdir(exist_ok=True)
    LOG.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def posted_before(text: str) -> bool:
    """Один и тот же текст под разными запусками — то, за что PH и наказывает."""
    if not LOG.exists():
        return False
    head = text.split("\n")[0][:60]
    return any(head and head in (row.get("text") or "") for row in json.load(open(LOG, encoding="utf-8")))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--login-timeout", type=int, default=15, help="минут ждать входа в окне")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--feed", action="store_true", help="сегодняшние запуски")
    ap.add_argument("--read", action="store_true", help="текст страницы запуска")
    ap.add_argument("--comment", action="store_true")
    ap.add_argument("--url", default="")
    ap.add_argument("--text-file")
    ap.add_argument("--text", default="")
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--dry", action="store_true", help="довести до кнопки и не нажимать")
    ap.add_argument("--show", action="store_true", help="показывать окно браузера (для отладки и капч)")
    a = ap.parse_args()
    headless = not a.show

    if a.login:
        login(a.login_timeout)
    elif a.check:
        sys.exit(0 if check(headless) else 1)
    elif a.feed:
        feed(a.limit, headless)
    elif a.read:
        if not a.url:
            sys.exit("--read требует --url")
        read(a.url, headless)
    elif a.comment:
        if not a.url or not (a.text or a.text_file):
            sys.exit("--comment требует --url и --text-file (или --text)")
        body = a.text or open(a.text_file, encoding="utf-8").read().strip()
        if len(body) < 40:
            sys.exit("комментарий короче 40 символов — такие PH не учитывает, а мейкеры не читают")
        if posted_before(body):
            sys.exit("этот текст уже отправляли под другим запуском — копипаста работает в минус")
        result = comment(a.url, body, a.dry, headless)
        entry = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                 "url": a.url, "text": body, **result}
        if not a.dry:
            log(entry)
        print(json.dumps(entry, ensure_ascii=False)[:600])
        sys.exit(0 if result.get("ok") else 1)
    else:
        ap.print_help()
