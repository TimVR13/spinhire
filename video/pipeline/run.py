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
from common import OUT, RENDERS, VIDEO_DIR  # noqa: E402
from planner import plan  # noqa: E402


def sh(cmd: list[str], **kw):
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, cwd=str(VIDEO_DIR), **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", required=True, choices=["morning", "day", "evening"])
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--format", default="", help="переопределить формат из планировщика")
    ap.add_argument("--slug", default="")
    ap.add_argument("--script", default="", help="JSON с фразами/сценами от агента поверх автосборки")
    ap.add_argument("--dry", action="store_true", help="собрать и отрендерить, но не загружать")
    a = ap.parse_args()

    p = plan(a.slot, dt.date.fromisoformat(a.date))
    if a.format:
        p["format"] = a.format
    if a.slug:
        p["slug"] = a.slug
    print("план:", json.dumps(p, ensure_ascii=False), flush=True)

    cmd = [sys.executable, "pipeline/build.py", p["format"], p["id"]]
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
