"""Загрузка Shorts на YouTube: private + publishAt (сам станет public в срок) + в плейлист по формату.

  python3 pipeline/upload.py out/2026-09-09-morning.mp4 --publish-at 2026-09-09T07:00:00Z
  python3 pipeline/upload.py out/x.mp4 --privacy private          # без расписания, для проверки
Метаданные берутся из out/<id>.meta.json (сборщик build.py). Лог — data/youtube-posts.json.
"""
import argparse
import datetime as dt
import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from common import DATA, OUT, env_or_file

LOG = DATA / "youtube-posts.json"
PLAYLISTS = json.load(open(DATA / "youtube-playlists.json", encoding="utf-8"))["playlists"]


def service():
    token = env_or_file("YT_TOKEN", "token.json")
    creds = Credentials.from_authorized_user_file(str(token))
    if not creds.valid:
        creds.refresh(Request())
        token.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def upload(video: Path, meta: dict, publish_at: str | None, privacy: str) -> str:
    yt = service()
    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}
    if publish_at:
        status = {"privacyStatus": "private", "publishAt": publish_at, "selfDeclaredMadeForKids": False}
    body = {"snippet": {"title": meta["title"], "description": meta["description"], "tags": meta["tags"],
                        "categoryId": "22", "defaultLanguage": "ru", "defaultAudioLanguage": "ru"},
            "status": status}
    media = MediaFileUpload(str(video), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    pl = PLAYLISTS.get(meta.get("playlist"))
    if pl:
        yt.playlistItems().insert(part="snippet", body={"snippet": {"playlistId": pl, "resourceId": {"kind": "youtube#video", "videoId": vid}}}).execute()
        if privacy == "public" or publish_at:  # плейлист открываем, как только в нём есть видео к публикации
            yt.playlists().update(part="id,status,snippet", body={"id": pl, "status": {"privacyStatus": "public"},
                                  "snippet": yt.playlists().list(part="snippet", id=pl).execute()["items"][0]["snippet"]}).execute()
    return vid


def log(entry: dict):
    rows = json.load(open(LOG)) if LOG.exists() else []
    rows.append(entry)
    LOG.write_text(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--publish-at", default="", help="RFC3339 UTC, напр. 2026-09-09T07:00:00Z")
    ap.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    ap.add_argument("--slug", default="", help="профессия/компания для истории планировщика")
    a = ap.parse_args()
    video = Path(a.video)
    meta = json.load(open(OUT / f"{video.stem}.meta.json", encoding="utf-8"))
    vid = upload(video, meta, a.publish_at or None, a.privacy)
    entry = {"id": video.stem, "video_id": vid, "url": f"https://youtube.com/shorts/{vid}", "format": meta["format"],
             "playlist": meta.get("playlist"), "title": meta["title"], "publish_at": a.publish_at or None, "slug": a.slug or None, "featured": meta.get("featured", []),
             "uploaded_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")}
    log(entry)
    print(json.dumps(entry, ensure_ascii=False))
