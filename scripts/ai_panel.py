#!/usr/bin/env python3
"""Панель промптов: спрашиваем ИИ-ассистентов с веб-поиском и считаем, называют ли SpinHire.

    python3 scripts/ai_panel.py                 # все доступные движки
    python3 scripts/ai_panel.py gemini          # только один
    python3 scripts/ai_panel.py --dry           # показать промпты и движки без запросов

Движки включаются наличием ключей:
  gemini      — Vertex AI, сервисный аккаунт VERTEX_SA (по умолчанию ~/Desktop/planner/.data/vertex-sa.json),
                модель GEMINI_MODEL (gemini-2.5-flash) с инструментом Google Search
  openai      — OPENAI_API_KEY, модель OPENAI_MODEL (gpt-5) через Responses API + web_search
  perplexity  — PERPLEXITY_API_KEY, модель PERPLEXITY_MODEL (sonar)
  anthropic   — ANTHROPIC_API_KEY, модель ANTHROPIC_MODEL (claude-sonnet-5) + web_search

Результат дописывается в data/ai-panel.json (по одному прогону на движок и дату);
админка показывает его во вкладке «ИИ-видимость».
"""
import datetime
import json
import os
import re
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPTS_PATH = os.path.join(ROOT, "data", "ai-panel-prompts.json")
OUT_PATH = os.path.join(ROOT, "data", "ai-panel.json")
URL_RE = re.compile(r"https?://[^\s)\]>\"']+")


def load_prompts() -> dict:
    with open(PROMPTS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


# ---------- движки: каждый возвращает (текст ответа, список URL-источников) ----------

def ask_gemini(prompt: str) -> tuple[str, list[str]]:
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    sa = os.environ.get("VERTEX_SA", os.path.expanduser("~/Desktop/planner/.data/vertex-sa.json"))
    creds = service_account.Credentials.from_service_account_file(
        sa, scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    project = os.environ.get("VERTEX_PROJECT", "skillproof-502320")
    location = os.environ.get("VERTEX_LOCATION", "global")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    url = (f"https://aiplatform.googleapis.com/v1/projects/{project}/locations/{location}"
           f"/publishers/google/models/{model}:generateContent")
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "tools": [{"googleSearch": {}}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1500}}
    r = requests.post(url, headers={"Authorization": "Bearer " + creds.token}, json=body, timeout=120)
    r.raise_for_status()
    data = r.json()
    cand = (data.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
    urls = []
    for chunk in cand.get("groundingMetadata", {}).get("groundingChunks", []):
        web = chunk.get("web") or {}
        if web.get("uri"):
            urls.append(web["uri"])
        if web.get("domain"):
            urls.append("https://" + web["domain"])
    return text, urls


def ask_openai(prompt: str) -> tuple[str, list[str]]:
    key = os.environ["OPENAI_API_KEY"]
    model = os.environ.get("OPENAI_MODEL", "gpt-5")
    r = requests.post("https://api.openai.com/v1/responses",
                      headers={"Authorization": f"Bearer {key}"},
                      json={"model": model, "input": prompt, "tools": [{"type": "web_search"}]},
                      timeout=180)
    r.raise_for_status()
    data = r.json()
    text, urls = "", []
    for item in data.get("output", []):
        for part in item.get("content", []) or []:
            if part.get("type") == "output_text":
                text += part.get("text", "")
                for ann in part.get("annotations", []) or []:
                    if ann.get("url"):
                        urls.append(ann["url"])
    return text, urls


def ask_perplexity(prompt: str) -> tuple[str, list[str]]:
    key = os.environ["PERPLEXITY_API_KEY"]
    model = os.environ.get("PERPLEXITY_MODEL", "sonar")
    r = requests.post("https://api.perplexity.ai/chat/completions",
                      headers={"Authorization": f"Bearer {key}"},
                      json={"model": model, "messages": [{"role": "user", "content": prompt}]},
                      timeout=180)
    r.raise_for_status()
    data = r.json()
    text = data["choices"][0]["message"]["content"]
    urls = list(data.get("citations") or [])
    for res in data.get("search_results") or []:
        if res.get("url"):
            urls.append(res["url"])
    return text, urls


def ask_anthropic(prompt: str) -> tuple[str, list[str]]:
    key = os.environ["ANTHROPIC_API_KEY"]
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                      json={"model": model, "max_tokens": 1500,
                            "messages": [{"role": "user", "content": prompt}],
                            "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]},
                      timeout=240)
    r.raise_for_status()
    data = r.json()
    text, urls = "", []
    for block in data.get("content", []):
        if block.get("type") == "text":
            text += block.get("text", "")
            for cit in block.get("citations", []) or []:
                if cit.get("url"):
                    urls.append(cit["url"])
        if block.get("type") == "web_search_tool_result":
            for res in block.get("content", []) or []:
                if isinstance(res, dict) and res.get("url"):
                    urls.append(res["url"])
    return text, urls


ENGINES = {
    "gemini": (ask_gemini, lambda: os.path.exists(os.environ.get(
        "VERTEX_SA", os.path.expanduser("~/Desktop/planner/.data/vertex-sa.json")))),
    "openai": (ask_openai, lambda: bool(os.environ.get("OPENAI_API_KEY"))),
    "perplexity": (ask_perplexity, lambda: bool(os.environ.get("PERPLEXITY_API_KEY"))),
    "anthropic": (ask_anthropic, lambda: bool(os.environ.get("ANTHROPIC_API_KEY"))),
}


def analyse(text: str, urls: list[str], cfg: dict) -> dict:
    low = (text or "").lower()
    all_urls = urls + URL_RE.findall(text or "")
    joined = " ".join(all_urls).lower()
    mentioned = any(b in low for b in cfg["brand"])
    cited = "spinhire.io" in joined
    rivals = sorted({name for dom, name in cfg["competitors"].items()
                     if dom in joined or name.lower() in low})
    return {"mentioned": mentioned or cited, "cited": cited, "competitors": rivals,
            "sources": sorted({u for u in all_urls})[:15]}


def run(engine_names: list[str], dry: bool = False) -> None:
    cfg = load_prompts()
    try:
        with open(OUT_PATH, encoding="utf-8") as fh:
            store = json.load(fh)
    except (OSError, ValueError):
        store = {"runs": []}
    today = datetime.date.today().isoformat()
    for name in engine_names:
        ask, available = ENGINES[name]
        if not available():
            print(f"[{name}] нет ключа — пропускаю")
            continue
        if dry:
            print(f"[{name}] доступен, {len(cfg['prompts'])} промптов")
            continue
        results, errors = [], 0
        for prompt in cfg["prompts"]:
            try:
                text, urls = ask(prompt["text"])
                res = analyse(text, urls, cfg)
                res.update(id=prompt["id"], lang=prompt["lang"], snippet=(text or "")[:400])
                results.append(res)
                flag = "✓ SpinHire" if res["mentioned"] else "—"
                print(f"[{name}] {prompt['id']:18} {flag:12} {', '.join(res['competitors'][:4])}")
            except Exception as exc:  # noqa: BLE001 — один упавший промпт не валит прогон
                errors += 1
                print(f"[{name}] {prompt['id']:18} ошибка: {str(exc)[:120]}")
                results.append({"id": prompt["id"], "lang": prompt["lang"], "error": str(exc)[:200],
                                "mentioned": False, "cited": False, "competitors": [], "sources": []})
            time.sleep(1.5)
        ok = [r for r in results if "error" not in r]
        summary = {
            "prompts": len(results), "answered": len(ok), "errors": errors,
            "mentioned": sum(1 for r in ok if r["mentioned"]),
            "cited": sum(1 for r in ok if r["cited"]),
            "share": round(sum(1 for r in ok if r["mentioned"]) * 100 / len(ok)) if ok else 0,
        }
        rivals: dict[str, int] = {}
        for r in ok:
            for c in r["competitors"]:
                rivals[c] = rivals.get(c, 0) + 1
        summary["top_competitors"] = sorted(rivals.items(), key=lambda kv: -kv[1])[:8]
        store["runs"] = [r for r in store["runs"] if not (r["engine"] == name and r["date"] == today)]
        store["runs"].append({"date": today, "engine": name, "summary": summary, "results": results})
        store["runs"] = store["runs"][-60:]
        with open(OUT_PATH, "w", encoding="utf-8") as fh:
            json.dump(store, fh, ensure_ascii=False, indent=1)
        print(f"[{name}] итог: SpinHire назван в {summary['mentioned']}/{summary['answered']} "
              f"({summary['share']}%), цитирован {summary['cited']}; чаще всего называют "
              f"{', '.join(f'{k} ({v})' for k, v in summary['top_competitors'][:5])}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    run(args or list(ENGINES), dry="--dry" in sys.argv)
