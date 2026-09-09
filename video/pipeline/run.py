"""Один слот целиком: план → сборка (данные + озвучка) → рендер → загрузка по расписанию.

  python3 pipeline/run.py --slot morning            # сегодня, публикация в 09:00 местного
  python3 pipeline/run.py --slot day --dry          # без загрузки
  python3 pipeline/run.py --slot evening --script my-phrases.json   # фразы, написанные агентом (см. ROUTINE.md)

Если время слота уже прошло, публикация ставится на завтра.
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import OUT, RENDERS, ROOT, VIDEO_DIR  # noqa: E402
from planner import plan  # noqa: E402


def done_ids() -> set[str]:
    p = ROOT / "data" / "youtube-posts.json"
    return {r["id"] for r in json.load(open(p))} if p.exists() else set()


def already_done(date: str, slot: str) -> bool:
    return f"{date}-{slot}" in done_ids()


def next_free_slot(min_lead_minutes: int = 40):
    """Ближайший слот, до публикации которого ещё ≥ 40 минут и которого нет в логе."""
    from planner import SLOT_UTC
    now = dt.datetime.now(dt.timezone.utc)
    done = done_ids()
    for d in range(0, 3):
        day = (now + dt.timedelta(days=d)).date()
        for slot, t in SLOT_UTC.items():
            pub = dt.datetime.combine(day, dt.time.fromisoformat(t), tzinfo=dt.timezone.utc)
            if pub - now >= dt.timedelta(minutes=min_lead_minutes) and f"{day}-{slot}" not in done:
                return slot, day.isoformat()
    return None, None


def sh(cmd: list[str], **kw):
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, cwd=str(VIDEO_DIR), **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", default="auto", choices=["auto", "morning", "day", "evening"],
                    help="auto — ближайший свободный слот в ближайшие 48 часов (для облачной routine)")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--format", default="", help="переопределить формат из планировщика")
    ap.add_argument("--slug", default="")
    ap.add_argument("--script", default="", help="JSON с фразами/сценами от агента поверх автосборки")
    ap.add_argument("--dry", action="store_true", help="собрать и отрендерить, но не загружать")
    ap.add_argument("--plan-only", action="store_true", help="только выбрать слот и напечатать план")
    a = ap.parse_args()

    if a.slot == "auto":
        a.slot, a.date = next_free_slot()
        if not a.slot:
            print("все слоты на 48 часов уже заняты — нечего делать"); return
    if already_done(a.date, a.slot):
        print(f"слот {a.date}-{a.slot} уже в data/youtube-posts.json — пропускаю"); return
    p = plan(a.slot, dt.date.fromisoformat(a.date))
    if a.format:
        p["format"] = a.format
    if a.slug:
        p["slug"] = a.slug
    print("план:", json.dumps(p, ensure_ascii=False), flush=True)
    if a.plan_only:
        return

    cmd = [sys.executable, "pipeline/build.py", p["format"], p["id"], "--date", a.date]
    if p.get("slug"):
        cmd += ["--slug", p["slug"]]
    if p.get("dative"):
        cmd += ["--dative", p["dative"]]
    if a.script:
        cmd += ["--script", a.script]
    sh(cmd)

    props = RENDERS / p["id"] / "props.json"
    mp4 = OUT / f"{p['id']}.mp4"
    sh(["npx", "remotion", "render", "src/index.ts", "Short", str(mp4), f"--props={props}", "--log=error"])
    print("рендер:", mp4, mp4.stat().st_size // 1024, "КБ", flush=True)

    if a.dry:
        print("dry-run: без загрузки")
        return
    publish_at = p["publish_at"]
    if dt.datetime.fromisoformat(publish_at.replace("Z", "+00:00")) <= dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5):
        nxt = dt.date.fromisoformat(a.date) + dt.timedelta(days=1)
        publish_at = f"{nxt.isoformat()}T{publish_at[11:]}"
        print("слот прошёл — публикация переносится на", publish_at)
    r = sh([sys.executable, "pipeline/upload.py", str(mp4), "--publish-at", publish_at, "--slug", p.get("slug", "")],
           capture_output=True, text=True)
    print(r.stdout.strip().splitlines()[-1])


if __name__ == "__main__":
    main()
