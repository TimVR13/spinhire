"""Постинг в Reddit: через официальный API (основной путь) или через сессию браузера (запасной).

Путь 1 — API (рекомендуется; Reddit отбивает логин из автоматизированного браузера):
  1. Залогиньтесь в Reddit в обычном браузере, откройте https://www.reddit.com/prefs/apps
     → «create another app…» → тип **script**, name: spinhire-poster, redirect uri: http://localhost:8080.
  2. Создайте файл ~/.spinhire/reddit.env (chmod 600):
        REDDIT_CLIENT_ID=…        # строка под названием приложения
        REDDIT_CLIENT_SECRET=…    # поле secret
        REDDIT_USERNAME=…         # имя пользователя, не email
        REDDIT_PASSWORD=…
     У аккаунта должна быть выключена двухфакторка (password-grant её не поддерживает), либо
     добавьте REDDIT_2FA_CODE=123456 на время одного запуска.
  3. python3 scripts/reddit_post.py --check   → «сессия: ок, пользователь …»
  Если reddit.env есть, --check и --post идут через API; браузер не нужен.

Путь 2 — браузерная сессия. Один раз, на Маке оператора:
    python3 scripts/reddit_post.py --login
  Откроется Google Chrome, залогиньтесь в Reddit (email/пароль или ссылка на почту; вход через Google
  автоматизированный браузер блокирует) — скрипт сам заметит вход и сохранит сессию
  в ~/.spinhire/reddit-state.json (cookies + localStorage). Enter в терминале не нужен.

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
import base64
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = Path(os.environ.get("SPINHIRE_REDDIT_STATE", os.path.expanduser("~/.spinhire/reddit-state.json")))
ENV = Path(os.environ.get("SPINHIRE_REDDIT_ENV", os.path.expanduser("~/.spinhire/reddit.env")))
LOG = ROOT / "data" / "reddit-posts.json"
SITE = os.environ.get("SPINHIRE_SITE", "https://spinhire.io")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"


# ---------- путь 1: официальный API (OAuth2 password grant для script-приложения) ----------

def api_creds() -> dict | None:
    """Читает ~/.spinhire/reddit.env; None, если файла нет или не хватает полей."""
    if not ENV.exists():
        return None
    kv = {}
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip().strip('"').strip("'")
    need = ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME", "REDDIT_PASSWORD"]
    missing = [k for k in need if not kv.get(k)]
    if missing:
        sys.exit(f"в {ENV} не хватает: {', '.join(missing)}")
    return kv


def _api_ua(c: dict) -> str:
    return f"macos:spinhire-poster:1.0 (by /u/{c['REDDIT_USERNAME']})"


def api_token(c: dict) -> str:
    password = c["REDDIT_PASSWORD"]
    if c.get("REDDIT_2FA_CODE"):
        password = f"{password}:{c['REDDIT_2FA_CODE']}"
    body = urllib.parse.urlencode({"grant_type": "password", "username": c["REDDIT_USERNAME"], "password": password}).encode()
    auth = base64.b64encode(f"{c['REDDIT_CLIENT_ID']}:{c['REDDIT_CLIENT_SECRET']}".encode()).decode()
    req = urllib.request.Request("https://www.reddit.com/api/v1/access_token", data=body,
                                 headers={"Authorization": f"Basic {auth}", "User-Agent": _api_ua(c),
                                          "Content-Type": "application/x-www-form-urlencoded"})
    try:
        data = json.load(urllib.request.urlopen(req, timeout=20))
    except urllib.error.HTTPError as e:
        sys.exit(f"Reddit API: HTTP {e.code} при получении токена — проверьте client_id/secret в {ENV}")
    if "access_token" not in data:
        sys.exit(f"Reddit API отказал: {data.get('error', data)} — проверьте логин/пароль, выключена ли 2FA, тип приложения script")
    return data["access_token"]


def _api_call(c: dict, token: str, path: str, form: dict | None = None) -> dict:
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    req = urllib.request.Request("https://oauth.reddit.com" + path, data=data,
                                 headers={"Authorization": f"bearer {token}", "User-Agent": _api_ua(c)})
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {path}: {e.read()[:300].decode(errors='replace')}") from None


def api_check(c: dict) -> bool:
    name = _api_call(c, api_token(c), "/api/v1/me").get("name")
    print("сессия:", f"ок (API), пользователь {name}" if name else "API не вернул пользователя")
    return bool(name)


def api_post(c: dict, subreddit: str, title: str, text: str = "", url: str = "", flair: str = "", dry: bool = False) -> dict:
    token = api_token(c)
    form = {"sr": subreddit, "title": title, "api_type": "json", "resubmit": "true", "sendreplies": "true"}
    if url:
        form.update(kind="link", url=url)
    else:
        form.update(kind="self", text=text)
    if flair:
        try:
            flairs = _api_call(c, token, f"/r/{subreddit}/api/link_flair_v2")
            match = next((f for f in flairs if flair.lower() in (f.get("text") or "").lower()), None)
            if match:
                form["flair_id"] = match["id"]
            else:
                print(f"флэр «{flair}» не найден в r/{subreddit}, доступны: {[f.get('text') for f in flairs]}")
        except RuntimeError as e:
            print("флэры недоступны:", e)
    if dry:
        me = _api_call(c, token, "/api/v1/me").get("name")
        return {"ok": True, "dry": True, "as": me, "would_submit": {k: (v[:200] if isinstance(v, str) else v) for k, v in form.items()}}
    try:
        resp = _api_call(c, token, "/api/submit", form)
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}
    j = resp.get("json") or {}
    if j.get("errors"):
        return {"ok": False, "error": "; ".join(" ".join(map(str, e)) for e in j["errors"])}
    post_url = (j.get("data") or {}).get("url", "")
    return {"ok": bool(post_url), "url": post_url} if post_url else {"ok": False, "error": f"нет url в ответе: {resp}"}


# ---------- путь 2: сессия браузера (Playwright) ----------

def pw():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("pip3 install playwright && python3 -m playwright install chromium")
    return sync_playwright


def _me(ctx) -> str | None:
    """Имя залогиненного пользователя по cookies контекста, иначе None."""
    try:
        r = ctx.request.get("https://www.reddit.com/api/me.json", headers={"User-Agent": UA}, timeout=10_000)
        return (r.json().get("data") or {}).get("name") or None
    except Exception:
        return None


def login(timeout_min: int = 15, login_url: str = "https://old.reddit.com/login"):
    """Открывает Chrome, ждёт, пока в окне залогинятся (без Enter в терминале), и сохраняет сессию.

    Enter не нужен: скрипт сам раз в 2 секунды спрашивает Reddit, кто залогинен. Так работает и без stdin
    (например, при запуске из Claude Code). Вход через Google в автоматизированном Chrome обычно
    блокируется самим Google — входите по email/паролю или по одноразовой ссылке на почту.
    """
    with pw()() as p:
        b = _launch(p, headless=False)
        ctx = b.new_context(user_agent=UA, viewport={"width": 1280, "height": 900}, locale="en-US")
        page = ctx.new_page()
        page.goto(login_url, wait_until="domcontentloaded")
        try:  # баннер cookies мешает кликать
            page.get_by_role("button", name="Reject Optional Cookies").first.click(timeout=4000)
        except Exception:
            pass
        print(f"Залогиньтесь в окне браузера (email/пароль или ссылка на почту). Жду до {timeout_min} мин…", flush=True)
        name = None
        deadline = time.time() + timeout_min * 60
        while time.time() < deadline:
            if page.is_closed():
                sys.exit("окно закрыли до входа — сессия не сохранена")
            name = _me(ctx)
            if name:
                break
            time.sleep(2)
        if not name:
            b.close()
            sys.exit("за отведённое время вход не выполнен — сессия не сохранена, повторите --login")
        time.sleep(2)  # дать Reddit дописать cookies после редиректа
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(ctx.storage_state()))
        os.chmod(STATE, 0o600)
        print(f"сессия сохранена: {STATE} (пользователь {name})")
        b.close()


def _context(p, headless=True):
    if not STATE.exists():
        sys.exit(f"нет сессии {STATE} — сначала --login")
    b = _launch(p, headless=headless)
    ctx = b.new_context(storage_state=json.loads(STATE.read_text()), user_agent=UA, viewport={"width": 1280, "height": 900}, locale="en-US")
    return b, ctx


def _launch(p, headless: bool):
    """Настоящий Google Chrome (channel=chrome), профиль отдельный: капч меньше, чем у голого Chromium."""
    try:
        return p.chromium.launch(channel="chrome", headless=headless)
    except Exception:
        return p.chromium.launch(headless=headless)


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
    ap.add_argument("--login-timeout", type=int, default=15, help="минут ждать входа в окне (для --login)")
    ap.add_argument("--login-url", default="https://old.reddit.com/login", help="какую форму входа открыть (старая надёжнее новой)")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--subreddit", default="spinhire")
    ap.add_argument("--title")
    ap.add_argument("--text-file")
    ap.add_argument("--url", default="")
    ap.add_argument("--flair", default="")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    if a.login:
        login(a.login_timeout, a.login_url)
    elif a.check:
        creds = api_creds()
        sys.exit(0 if (api_check(creds) if creds else check()) else 1)
    elif a.post:
        if not a.subreddit or not a.title:
            sys.exit("--post требует --subreddit и --title")
        text = open(a.text_file, encoding="utf-8").read() if a.text_file else ""
        creds = api_creds()
        if creds:
            r = api_post(creds, a.subreddit, a.title, text, a.url, a.flair, a.dry)
        else:
            r = post(a.subreddit, a.title, text, a.url, a.flair, a.dry)
        entry = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                 "subreddit": a.subreddit, "title": a.title, **r}
        if not a.dry:
            log_and_sync(entry)
        print(json.dumps(entry, ensure_ascii=False))
        sys.exit(0 if r.get("ok") else 1)
    else:
        ap.print_help()
