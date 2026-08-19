#!/usr/bin/env python3
"""Прямой доступ к Google Search Console по сервисному аккаунту.

Ключ не хранится в репозитории — путь берётся из GSC_SA_FILE
(по умолчанию ключ Vertex, которым уже пользуется planner).

  python3 scripts/gsc.py status
  python3 scripts/gsc.py sitemaps
  python3 scripts/gsc.py submit [https://spinhire.io/sitemap.xml]
  python3 scripts/gsc.py inspect https://spinhire.io/jobs
  python3 scripts/gsc.py performance [query|page|country|device] [дней] [строк]
"""
import json
import os
import sys
import urllib.parse

from google.oauth2 import service_account
import google.auth.transport.requests

SA_FILE = os.environ.get(
    "GSC_SA_FILE", os.path.expanduser("~/Desktop/planner/.data/vertex-sa.json"))
SITE = os.environ.get("GSC_SITE", "sc-domain:spinhire.io")
SCOPE = ["https://www.googleapis.com/auth/webmasters"]
API = "https://searchconsole.googleapis.com/webmasters/v3/sites/"


def session():
    creds = service_account.Credentials.from_service_account_file(SA_FILE, scopes=SCOPE)
    s = google.auth.transport.requests.AuthorizedSession(creds)
    return creds, s


def call(s, path, method="GET", body=None):
    url = API + urllib.parse.quote(SITE, safe="") + path
    r = s.request(method, url, json=body)
    if r.status_code >= 400:
        raise SystemExit(f"{r.status_code} {r.text[:400]}")
    return r.json() if r.text.strip() else {}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    creds, s = session()

    if cmd == "status":
        print(f"аккаунт: {creds.service_account_email}")
        print(f"ресурс:  {SITE}")
        r = s.get("https://searchconsole.googleapis.com/webmasters/v3/sites")
        if r.status_code >= 400:
            raise SystemExit(f"нет доступа: {r.status_code} {r.text[:300]}")
        sites = r.json().get("siteEntry", [])
        print("доступные ресурсы:")
        for it in sites:
            print(f"  {it['siteUrl']} — {it.get('permissionLevel')}")
        if not any(it["siteUrl"] == SITE for it in sites):
            print(f"\nВНИМАНИЕ: {SITE} в списке нет — добавьте "
                  f"{creds.service_account_email} в Search Console.")

    elif cmd == "sitemaps":
        for sm in call(s, "/sitemaps").get("sitemap", []):
            print(json.dumps({
                "path": sm.get("path"),
                "submitted": sm.get("lastSubmitted"),
                "downloaded": sm.get("lastDownloaded"),
                "errors": sm.get("errors"), "warnings": sm.get("warnings"),
                "urls": [(c.get("type"), c.get("submitted"), c.get("indexed"))
                         for c in sm.get("contents", [])],
            }, ensure_ascii=False))

    elif cmd == "submit":
        url = sys.argv[2] if len(sys.argv) > 2 else "https://spinhire.io/sitemap.xml"
        call(s, "/sitemaps/" + urllib.parse.quote(url, safe=""), "PUT")
        print(f"отправлено: {url}")

    elif cmd == "inspect":
        url = sys.argv[2]
        r = s.post("https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
                   json={"inspectionUrl": url, "siteUrl": SITE})
        if r.status_code >= 400:
            raise SystemExit(f"{r.status_code} {r.text[:400]}")
        res = r.json().get("inspectionResult", {}).get("indexStatusResult", {})
        print(json.dumps({
            "verdict": res.get("verdict"),
            "coverage": res.get("coverageState"),
            "robots": res.get("robotsTxtState"),
            "indexing": res.get("indexingState"),
            "canonical_google": res.get("googleCanonical"),
            "canonical_user": res.get("userCanonical"),
            "last_crawl": res.get("lastCrawlTime"),
        }, ensure_ascii=False, indent=2))

    elif cmd == "performance":
        dim = sys.argv[2] if len(sys.argv) > 2 else "query"
        days = int(sys.argv[3]) if len(sys.argv) > 3 else 28
        limit = int(sys.argv[4]) if len(sys.argv) > 4 else 25
        import datetime
        today = datetime.date.today()
        body = {"startDate": str(today - datetime.timedelta(days=days)),
                "endDate": str(today), "dimensions": [dim], "rowLimit": limit}
        rows = call(s, "/searchAnalytics/query", "POST", body).get("rows", [])
        if not rows:
            print("данных нет — обычно так до первых показов в выдаче")
        for row in rows:
            print(f"{row['keys'][0][:60]:60} показы={row['impressions']:>6} "
                  f"клики={row['clicks']:>4} позиция={row['position']:.1f}")

    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
