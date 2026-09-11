"""Батч: собрать и отрендерить пачку роликов заранее, сложить в очередь (без загрузки).

  python3 pipeline/batch.py profession --slugs vip-manager,bonus-manager,media-buyer
  python3 pipeline/batch.py profession --all --limit 10
  python3 pipeline/batch.py profession --all --no-render     # только озвучка и props, рендер потом
  python3 pipeline/batch.py --status                         # что лежит в очереди

Один прогон = одна серия. Публикацией занимается run.py: в свой слот он берёт готовое из
data/video-queue.json. Уже опубликованные и уже собранные роли пропускаются (--force отменяет).
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vqueue as q  # noqa: E402
from common import DATA, OUT, RENDERS, VIDEO_DIR, professions  # noqa: E402


def published_slugs() -> set[str]:
    p = DATA / "youtube-posts.json"
    rows = json.load(open(p, encoding="utf-8")) if p.exists() else []
    return {r.get("slug") for r in rows if r.get("slug")}


def queued_slugs() -> set[str]:
    return {r.get("slug") for r in q.load() if r.get("slug")}


def roles_for(fmt: str, slugs: list[str], take_all: bool, limit: int, force: bool) -> list[dict]:
    roles = professions()["roles"]
    if slugs:
        by_slug = {r["slug"]: r for r in roles}
        missing = [s for s in slugs if s not in by_slug]
        if missing:
            raise SystemExit(f"нет таких профессий: {', '.join(missing)}")
        pool = [by_slug[s] for s in slugs]
    elif take_all:
        pool = sorted(roles, key=lambda r: (-(r.get("demand") or 0), r["slug"]))  # сначала востребованные
    else:
        raise SystemExit("нужен --slugs или --all")
    if not force:
        skip = published_slugs() | queued_slugs()
        pool = [r for r in pool if r["slug"] not in skip]
    return pool[:limit] if limit else pool


def build_one(fmt: str, role: dict, args) -> dict:
    vid = f"{fmt[:4]}-{role['slug']}"
    cmd = [sys.executable, "pipeline/build.py", fmt, vid, "--slug", role["slug"]]
    subprocess.run(cmd, check=True, cwd=str(VIDEO_DIR))
    meta = json.load(open(OUT / f"{vid}.meta.json", encoding="utf-8"))
    mp4 = OUT / f"{vid}.mp4"
    if not args.no_render:
        subprocess.run(["npx", "remotion", "render", "src/index.ts", "Short", str(mp4),
                        f"--props={RENDERS / vid / 'props.json'}", "--log=error"], check=True, cwd=str(VIDEO_DIR))
    return {"id": vid, "format": fmt, "slug": role["slug"], "title": meta["title"], "duration": meta["duration"],
            "voice": meta.get("voice", ""), "theme": meta.get("theme", ""),
            "mp4": str(mp4.relative_to(VIDEO_DIR)) if mp4.exists() else None,
            "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "status": "ready" if mp4.exists() else "built"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("format", nargs="?", choices=["profession", "salary"])
    ap.add_argument("--status", action="store_true", help="показать очередь и выйти")
    ap.add_argument("--slugs", default="", help="через запятую; иначе --all")
    ap.add_argument("--all", action="store_true", help="все профессии, начиная с самых востребованных")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-render", action="store_true", help="только озвучка и props — рендер отдельным прогоном")
    ap.add_argument("--force", action="store_true", help="пересобрать, даже если роль уже в очереди или опубликована")
    a = ap.parse_args()

    if a.status:
        rows = q.load()
        rd = [r for r in rows if r["status"] == "ready"]
        print(f"в очереди готовых: {len(rd)}, уже опубликовано из очереди: {sum(1 for r in rows if r['status'] == 'used')}")
        for r in rd:
            print(f"  {r['id']:34} {r['duration']:>5}с  {r['voice'].split('-')[-1]:7} {r['theme']:8} {r['title'][:54]}")
        return
    if not a.format:
        raise SystemExit("нужен формат (profession|salary) или --status")

    pool = roles_for(a.format, [s.strip() for s in a.slugs.split(",") if s.strip()], a.all, a.limit, a.force)
    if not pool:
        print("нечего собирать: все роли уже в очереди или опубликованы"); return
    print(f"в работе {len(pool)}: " + ", ".join(r["slug"] for r in pool), flush=True)

    done, failed = [], []
    for i, role in enumerate(pool, 1):
        t0 = time.time()
        print(f"\n[{i}/{len(pool)}] {role['slug']} — {role['title']}", flush=True)
        try:
            entry = build_one(a.format, role, a)
        except subprocess.CalledProcessError as e:
            print(f"  ✗ {role['slug']}: {e}", flush=True)
            failed.append(role["slug"])
            continue
        q.add(entry)
        done.append(entry)
        print(f"  ✓ {entry['id']} · {entry['duration']}с · голос {entry['voice'].split('-')[-1]} · тема {entry['theme']}"
              f" · {round(time.time() - t0)}с", flush=True)

    print(f"\nготово: {len(done)}, ошибок: {len(failed)}" + (f" ({', '.join(failed)})" if failed else ""))
    print("очередь:", q.QUEUE)


if __name__ == "__main__":
    main()
