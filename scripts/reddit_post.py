"""Reddit без API: постинг через сохранённую сессию браузера (Playwright, приём из PostForge).

Один раз, на Маке оператора:
    python3 scripts/reddit_post.py --login
  Откроется Chromium, залогиньтесь в Reddit, вернитесь в терминал и нажмите Enter —
  сессия сохранится в ~/.spinhire/reddit-state.json (cookies + localStorage).

Постинг:
    python3 scripts/reddit_post.py --post --subreddit igaming --title "…" --text-file post.md
    python3 scripts/reddit_post.py --post --subreddit igaming --title "…" --url https://spinhire.io/… [--flair "Jobs"]
    добавьте --dry, чтобы дойти до кнопки Post и не нажимать (сохранится скриншот в /tmp/reddit-dry.png)

Проверка сессии:
    python3 scripts/reddit_post.py --check

Лог: data/reddit-posts.json; если задан SPINHIRE_PUBLISH_KEY — строка уходит в реестр публикаций сайта.
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = Path(os.environ.get("SPINHIRE_REDDIT_STATE", os.path.expanduser("~/.spinhire/reddit-state.json")))
LOG = ROOT / "data" / "reddit-posts.json"
SITE = os.environ.get("SPINHIRE_SITE", "https://spinhire.io")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"


def pw():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("pip3 install playwright && python3 -m playwright install chromium")
    return sync_playwright


def login():
    with pw()() as p:
        b = p.chromium.launch(headless=False)
        ctx = b.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.goto("https://www.reddit.com/login/", wait_until="domcontentloaded")
        print("Залогиньтесь в окне браузера, затем нажмите Enter здесь.")
        input()
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(ctx.storage_state()))
        os.chmod(STATE, 0o600)
        print("сессия сохранена:", STATE)
        b.close()


def _context(p, headless=True):
    if not STATE.exists():
        sys.exit(f"нет сессии {STATE} — сначала --login")
    b = p.chromium.launch(headless=headless)
    ctx = b.new_context(storage_state=json.loads(STATE.read_text()), user_agent=UA, viewport={"width": 1280, "height": 900})
    return b, ctx


def whoami(page) -> str | None:
    page.goto("https://www.reddit.com/", wait_until="domcontentloaded", timeout=30_000)
    time.sleep(2)
    if page.locator("a[href='/login/']").first.is_visible(timeout=1500) if page.locator("a[href='/login/']").count() else False:
        return None
    try:
        r = page.request.get("https://www.reddit.com/api/me.json", headers={"User-Agent": UA})
        data = r.json()
        return (data.get("data") or {}).get("name")
    except Exception:
        return "unknown"


def check():
    with pw()() as p:
        b, ctx = _context(p)
        name = whoami(ctx.new_page())
        b.close()
    print("сессия:", "ок, пользователь " + name if name else "РАЗЛОГИНЕНА — повторите --login")
    return bool(name)


def post(subreddit: str, title: str, text: str = "", url: str = "", flair: str = "", dry: bool = False) -> dict:
    kind = "LINK" if url else "TEXT"
    with pw()() as p:
        b, ctx = _context(p)
        page = ctx.new_page()
        if not whoami(page):
            b.close()
            return {"ok": False, "error": "session expired — run --login"}
        page.goto(f"https://www.reddit.com/r/{subreddit}/submit?type={kind}", wait_until="domcontentloaded", timeout=45_000)
        time.sleep(3)
        # новый Reddit (shreddit): заголовок — textarea[name=title]; текст — редактор contenteditable; ссылка — input[name=link]
        page.locator("textarea[name='title'], input[name='title']").first.fill(title)
        if url:
            page.locator("input[name='link'], textarea[name='link']").first.fill(url)
        if text:
            editor = page.locator("[contenteditable='true'][role='textbox'], div[contenteditable='true']").first
            editor.click()
            editor.type(text, delay=5)
        if flair:
            try:
                page.get_by_role("button", name="Add flair and tags").first.click(timeout=3000)
                page.get_by_text(flair, exact=False).first.click(timeout=3000)
                page.get_by_role("button", name="Apply").first.click(timeout=3000)
            except Exception:
                pass
        if dry:
            page.screenshot(path="/tmp/reddit-dry.png", full_page=True)
            b.close()
            return {"ok": True, "dry": True, "screenshot": "/tmp/reddit-dry.png"}
        page.get_by_role("button", name="Post", exact=True).first.click(timeout=10_000)
        # ждём переход на страницу поста
        for _ in range(40):
            time.sleep(0.5)
            if "/comments/" in page.url:
                break
        result = {"ok": "/comments/" in page.url, "url": page.url}
        if not result["ok"]:
            page.screenshot(path="/tmp/reddit-fail.png", full_page=True)
            result["error"] = "no redirect to post; see /tmp/reddit-fail.png"
        b.close()
        return result


def log_and_sync(entry: dict):
    rows = json.load(open(LOG)) if LOG.exists() else []
    rows.append(entry)
    LOG.parent.mkdir(exist_ok=True)
    LOG.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    key = os.environ.get("SPINHIRE_PUBLISH_KEY")
    if not key:
        return
    body = {"external_id": f"reddit:{entry.get('url') or entry['ts']}", "platform": "reddit", "lang": "en", "kind": "post",
            "title": entry["title"], "url": entry.get("url", ""), "status": "published" if entry["ok"] else "error",
            "published_at": entry["ts"] if entry["ok"] else None, "error": entry.get("error", ""),
            "meta": {"subreddit": entry["subreddit"]}, "origin": "pipeline"}
    req = urllib.request.Request(f"{SITE}/api/publications/upsert", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "X-Publish-Key": key})
    try:
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:  # реестр — не критичный путь
        print("реестр недоступен:", e)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--subreddit")
    ap.add_argument("--title")
    ap.add_argument("--text-file")
    ap.add_argument("--url", default="")
    ap.add_argument("--flair", default="")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    if a.login:
        login()
    elif a.check:
        sys.exit(0 if check() else 1)
    elif a.post:
        text = open(a.text_file, encoding="utf-8").read() if a.text_file else ""
        r = post(a.subreddit, a.title, text, a.url, a.flair, a.dry)
        entry = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                 "subreddit": a.subreddit, "title": a.title, **r}
        if not a.dry:
            log_and_sync(entry)
        print(json.dumps(entry, ensure_ascii=False))
        sys.exit(0 if r.get("ok") else 1)
    else:
        ap.print_help()
