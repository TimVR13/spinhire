"""Дренаж очереди: залить готовые ролики на YouTube, расставив по будущим слотам.

  python3 pipeline/drain.py --count 3            # три ближайших свободных слота
  python3 pipeline/drain.py --count 5 --slots evening,day
  python3 pipeline/drain.py --count 3 --dry      # показать план, ничего не грузить

Рендер живёт на этой машине (video/out в .gitignore), поэтому публикует очередь тот, кто её собрал.
Заливаем заранее как private + publishAt: YouTube сам открывает ролик в срок, лента пополняется
по одному в день, а не пачкой. Квота YouTube Data API — 10 000 единиц в сутки, videos.insert стоит
1600, поэтому больше 6 загрузок за сутки не пройдёт (MAX_PER_RUN).
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vqueue as q  # noqa: E402
from common import ROOT, VIDEO_DIR  # noqa: E402
from planner import SLOT_UTC  # noqa: E402

MAX_PER_RUN = 6           # 10 000 единиц квоты / 1 600 за загрузку
LEAD_MINUTES = 60         # публикация не раньше чем через час, чтобы YouTube успел обработать


def taken_slots() -> set[str]:
    p = ROOT / "data" / "youtube-posts.json"
    return {r["id"] for r in json.load(open(p, encoding="utf-8"))} if p.exists() else set()


def free_slots(slots: list[str], n: int) -> list[tuple[str, str]]:
    """Ближайшие свободные (дата, слот) — по одному ролику в слот, начиная с сегодняшнего дня."""
    now = dt.datetime.now(dt.timezone.utc)
    taken, out = taken_slots(), []
    for d in range(0, 60):
        day = (now + dt.timedelta(days=d)).date()
        for slot in slots:
            pub = dt.datetime.combine(day, dt.time.fromisoformat(SLOT_UTC[slot]), tzinfo=dt.timezone.utc)
            if pub - now < dt.timedelta(minutes=LEAD_MINUTES) or f"{day}-{slot}" in taken:
                continue
            out.append((day.isoformat(), slot))
            if len(out) == n:
                return out
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=3, help=f"сколько роликов залить за прогон (максимум {MAX_PER_RUN} — квота API)")
    ap.add_argument("--slots", default="evening", help="слоты под серию через запятую: evening,day,morning")
    ap.add_argument("--dry", action="store_true", help="показать план без загрузки")
    a = ap.parse_args()

    count = min(a.count, MAX_PER_RUN)
    if a.count > MAX_PER_RUN:
        print(f"за сутки через API проходит не больше {MAX_PER_RUN} загрузок — беру {count}")
    slots = [s.strip() for s in a.slots.split(",") if s.strip()]
    bad = [s for s in slots if s not in SLOT_UTC]
    if bad:
        raise SystemExit(f"нет таких слотов: {', '.join(bad)}")

    items = [r for r in q.ready() if (VIDEO_DIR / (r["mp4"] or "")).exists()][:count]
    if not items:
        print("в очереди нет готовых роликов — сначала pipeline/batch.py"); return
    plan = list(zip(items, free_slots(slots, len(items))))
    for it, (date, slot) in plan:
        print(f"{date} {slot:8} ← {it['id']:34} {it['title'][:60]}")
    if a.dry:
        print("dry-run: ничего не загружено"); return

    for it, (date, slot) in plan:
        publish_at = f"{date}T{SLOT_UTC[slot]}Z"
        r = subprocess.run([sys.executable, "pipeline/upload.py", str(VIDEO_DIR / it["mp4"]),
                            "--publish-at", publish_at, "--slug", it.get("slug", ""), "--slot-id", f"{date}-{slot}"],
                           check=True, capture_output=True, text=True, cwd=str(VIDEO_DIR))
        entry = json.loads(r.stdout.strip().splitlines()[-1])
        q.mark_used(it["id"], f"{date}-{slot}", entry["video_id"])
        print(f"✓ {publish_at} {entry['url']} — {it['title'][:60]}", flush=True)
    print(f"\nзалито {len(plan)}; в очереди осталось {len(q.ready())}")


if __name__ == "__main__":
    main()
