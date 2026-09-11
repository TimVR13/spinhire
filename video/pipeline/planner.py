"""Планировщик: что снимать в этот слот. Ротация форматов по дню недели и слоту, без повторов по истории.

  python3 pipeline/planner.py --slot morning [--date 2026-09-09]   → JSON {format, slug, dative, id, publish_at}

Слоты (местное время Europe/Madrid → UTC): morning 09:00 (07:00Z), day 14:00 (12:00Z), evening 19:00 (17:00Z).
История — data/youtube-posts.json: профессия/компания не повторяется 14 дней, формат в слоте — не чаще 2 раз в неделю.
"""
import argparse
import datetime as dt
import json

from common import DATA, professions

SLOT_UTC = {"morning": "07:00:00", "day": "12:00:00", "evening": "17:00:00"}

# ротация по дню недели (0 = понедельник); в каждом слоте своя роль
ROTATION = {
    "morning": ["hot_jobs", "hot_jobs", "hot_jobs", "hot_jobs", "hot_jobs", "hot_jobs", "hot_jobs"],
    "day":     ["salary", "market_stat", "salary", "market_stat", "salary", "market_stat", "salary"],
    "evening": ["profession", "profession", "profession", "profession", "profession", "profession", "profession"],
}

# профессии в дательном падеже для «сколько платят …» (остальные — через title.lower(), планировщик подставит «специалисту»)
DATIVE = {
    "affiliate-manager": "аффилейт-менеджеру", "bonus-manager": "бонус-менеджеру", "vip-manager": "VIP-менеджеру",
    "retention-manager": "retention-менеджеру", "casino-operations-manager": "менеджеру операций казино",
    "game-content-manager": "менеджеру игрового контента", "sportsbook-trader": "трейдеру беттинга",
    "head-of-affiliates": "хеду аффилейтов", "media-buyer": "медиабайеру", "crm-manager": "CRM-менеджеру",
    "support-agent": "агенту поддержки", "kyc-specialist": "KYC-специалисту", "aml-analyst": "AML-аналитику",
    "fraud-analyst": "антифрод-аналитику", "game-mathematician": "математику игр", "slot-game-designer": "гейм-дизайнеру слотов",
    "product-manager": "продакт-менеджеру", "qa-engineer": "QA-инженеру", "seo-specialist": "SEO-специалисту",
    "country-manager": "кантри-менеджеру", "payments-manager": "менеджеру платежей", "compliance-officer": "комплаенс-офицеру",
}


def history() -> list[dict]:
    p = DATA / "youtube-posts.json"
    return json.load(open(p, encoding="utf-8")) if p.exists() else []


def recent_slugs(days: int = 14, include_queue: bool = True) -> set[str]:
    """Роли, которые нельзя брать сейчас: недавно опубликованные и (для новой сборки) уже ждущие в очереди.
    При выборе ролика ИЗ очереди очередь, понятно, исключать нельзя — include_queue=False."""
    import vqueue
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
    used = {r.get("slug") for r in history() if r.get("slug") and r.get("uploaded_at", "") >= since}
    if not include_queue:
        return used
    return used | {r.get("slug") for r in vqueue.load() if r.get("status") == "ready" and r.get("slug")}


def pick_role(fmt: str, seed: int) -> dict:
    """Профессия по кругу: сначала те, у кого больше вакансий (demand), исключая недавние."""
    roles = professions()["roles"]
    used = recent_slugs()
    pool = [r for r in roles if r["slug"] not in used] or roles
    pool.sort(key=lambda r: (-(r.get("demand") or 0) if isinstance(r.get("demand"), (int, float)) else 0, r["slug"]))
    return pool[seed % len(pool)]


def plan(slot: str, date: dt.date) -> dict:
    fmt = ROTATION[slot][date.weekday()]
    vid = f"{date.isoformat()}-{slot}"
    out = {"id": vid, "slot": slot, "format": fmt, "publish_at": f"{date.isoformat()}T{SLOT_UTC[slot]}Z"}
    if fmt in ("salary", "profession"):
        r = pick_role(fmt, date.toordinal() + (1 if slot == "evening" else 0))
        out["slug"] = r["slug"]
        out["dative"] = DATIVE.get(r["slug"], f"на позиции {r['title']}")  # «сколько платят на позиции BI-аналитик»
        out["role_title"] = r["title"]
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", required=True, choices=SLOT_UTC)
    ap.add_argument("--date", default=dt.date.today().isoformat())
    a = ap.parse_args()
    print(json.dumps(plan(a.slot, dt.date.fromisoformat(a.date)), ensure_ascii=False))
