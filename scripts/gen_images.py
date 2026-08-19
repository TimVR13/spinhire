#!/usr/bin/env python3
"""Генерация 3D-картинок для SpinHire через Vertex AI (gemini-2.5-flash-image).
Использование: python3 scripts/gen_images.py jobs.json  — список {"out": "img/x.jpg", "prompt": "...", "aspect": "1:1"}
"""
import base64, json, os, sys, time, requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from PIL import Image
from io import BytesIO

SA = os.environ.get("VERTEX_SA", os.path.expanduser("~/Desktop/planner/.data/vertex-sa.json"))
PROJECT = "skillproof-502320"; LOCATION = "global"; MODEL = "gemini-2.5-flash-image"
STYLE = ("Premium 3D render, luxury game app-icon style, glossy materials, gold and emerald-green neon accents with a little "
         "hot-pink rim light, soft radial glow behind the object on a very dark near-black green background (not flat black), "
         "object fills ~80% of the frame, centered, sharp studio lighting, no text, no letters, no watermark.")

def token():
    creds = service_account.Credentials.from_service_account_file(SA, scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request()); return creds.token

def gen(prompt, aspect="1:1"):
    url = f"https://aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/{LOCATION}/publishers/google/models/{MODEL}:generateContent"
    body = {"contents": [{"role": "user", "parts": [{"text": prompt + " " + STYLE}]}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}}}
    for attempt in range(4):
        r = requests.post(url, headers={"Authorization": "Bearer " + token()}, json=body, timeout=120)
        if r.status_code == 429: time.sleep(15 * (attempt + 1)); continue
        r.raise_for_status()
        data = r.json()
        if "candidates" not in data:
            fb = data.get("promptFeedback", {})
            print("  blocked:", fb.get("blockReason"), "- retrying softened", file=sys.stderr)
            body["contents"][0]["parts"][0]["text"] = prompt + " Premium 3D render, glossy gold and emerald materials, dark elegant background, soft glow, object centered, no text."
            time.sleep(5); continue
        for part in data["candidates"][0]["content"]["parts"]:
            if "inlineData" in part: return base64.b64decode(part["inlineData"]["data"])
        raise RuntimeError("no image in response")
    raise RuntimeError("rate limited")

if __name__ == "__main__":
    jobs = json.load(open(sys.argv[1]))
    for j in jobs:
        if os.path.exists(j["out"]) and not j.get("force"): print("skip", j["out"]); continue
        data = gen(j["prompt"], j.get("aspect", "1:1"))
        im = Image.open(BytesIO(data)).convert("RGB")
        if j.get("size"): im.thumbnail((j["size"], j["size"]))
        im.save(j["out"], quality=88, optimize=True); print("ok", j["out"], im.size); time.sleep(8)
