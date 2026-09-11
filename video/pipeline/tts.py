"""Озвучка Google Cloud TTS по фразам: русские куски русским Charon, латиница — английским Charon.

Возвращает дорожку и тайминги фраз — из них строятся субтитры и смена сцен.
"""
import os
import re
import subprocess
from pathlib import Path

from google.cloud import texttospeech as tts

from common import env_or_file

VOICE = os.environ.get("SPINHIRE_TTS_VOICE", "Chirp3-HD-Charon")
RATE = float(os.environ.get("SPINHIRE_TTS_RATE", "1.12"))
SR = 24000
LATIN = re.compile(r"([A-Za-z][A-Za-z0-9 .&/+\-]*[A-Za-z0-9]|[A-Za-z])")

_client = None


def client():
    global _client
    if _client is None:
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(env_or_file("GOOGLE_TTS_SA", "tts-sa.json")))
        _client = tts.TextToSpeechClient()
    return _client


# Термины, которые русскоязычный диктор произносит по-русски — английскому голосу их не отдаём.
TERMS = {
    "igaming": "айгейминг", "gambling": "гэмблинг", "betting": "беттинг", "crm": "ЦРМ", "hr": "эйчар", "it": "айти",
    "qa": "кью-эй", "seo": "сео", "ppc": "пи-пи-си", "kpi": "кипиай", "vip": "вип", "aml": "эй-эм-эл", "kyc": "кей-вай-си",
    "b2b": "би-ту-би", "b2c": "би-ту-си", "ceo": "сео-директор", "cto": "си-ти-о", "coo": "си-о-о", "cmo": "си-эм-о",
    "junior": "джуниор", "middle": "мидл", "senior": "сеньор", "lead": "лид", "head": "хед", "team lead": "тимлид",
    "remote": "ремоут", "office": "офис", "excel": "эксель", "google sheets": "гугл-таблицы", "google": "гугл",
    "telegram": "телеграм", "whatsapp": "вотсап", "linkedin": "линкедин", "youtube": "ютуб", "instagram": "инстаграм",
    "tiktok": "тикток", "facebook": "фейсбук", "slack": "слак", "jira": "джира", "sql": "эс-кью-эль", "api": "апи",
    "ggr": "джи-джи-ар", "ngr": "эн-джи-ар", "rtp": "ар-ти-пи", "ltv": "эл-ти-ви", "roi": "рои", "cpa": "си-пи-эй",
    "revshare": "ревшара", "affiliate": "аффилейт", "affiliates": "аффилейты", "retention": "ретеншн", "support": "саппорт",
    "spinhire.io": "спинхайр точка ай-оу", "spinhire": "спинхайр", "malta": "Мальта", "cyprus": "Кипр",
    "sre": "эс-ар-и", "b1": "би-один", "b2": "би-два", "c1": "си-один", "c2": "си-два", "a2": "а-два", "devops": "девопс", "product owner": "продакт-оунер", "product manager": "продакт-менеджер",
    "live casino": "лайв-казино", "casino": "казино", "slots": "слоты", "sportsbook": "спортсбук", "fintech": "финтех",
    "responsible gaming": "ответственная игра", "optimove": "оптимув", "zendesk": "зендеск", "intercom": "интерком",
}
_TERM_RE = re.compile(r"(?<![A-Za-z])(" + "|".join(sorted((re.escape(k) for k in TERMS), key=len, reverse=True)) + r")(?![A-Za-z])", re.I)


def russify_run(run: str) -> str | None:
    """Латинский кусок → русское произношение, если это термин целиком или каждое слово в словаре."""
    key = run.lower().strip(" .")
    if key in TERMS:
        return TERMS[key]
    words = key.split()
    if len(words) == 1 and key.rstrip(".") in TERMS:
        return TERMS[key.rstrip(".")]
    if all(w in TERMS for w in words):
        return " ".join(TERMS[w] for w in words)
    return None


def split_langs(text: str) -> list[tuple[str, str]]:
    """Русский диктор читает всё, кроме латинских названий (компании, должности). Известные термины
    (iGaming, CRM, senior…) произносит по-русски. Знаки препинания клеятся к предыдущему куску,
    иначе голос читает «вопросительный знак»."""
    segs = []
    for part in LATIN.split(text):
        part = part.strip()
        if not part:
            continue
        lang = "en-US" if LATIN.fullmatch(part) else "ru-RU"
        if lang == "en-US":
            ru = russify_run(part)
            if ru is not None:
                lang, part = "ru-RU", ru
        joiner = " " if re.match(r"[A-Za-zА-Яа-яЁё0-9]", part) else ""
        if segs and (segs[-1][0] == lang or not re.search(r"[A-Za-zА-Яа-яЁё0-9]", part)):
            segs[-1] = (segs[-1][0], segs[-1][1] + joiner + part)
        else:
            segs.append((lang, part))
    return segs


def synth_wav(text: str, lang: str, voice: str = "") -> bytes:
    r = client().synthesize_speech(
        input=tts.SynthesisInput(text=text),
        voice=tts.VoiceSelectionParams(language_code=lang, name=f"{lang}-{voice or VOICE}"),
        audio_config=tts.AudioConfig(audio_encoding=tts.AudioEncoding.LINEAR16, sample_rate_hertz=SR, speaking_rate=RATE),
    )
    return r.audio_content


def trim_silence(src: Path, dst: Path, thr: str = "-42dB") -> None:
    """Chirp отдаёт до секунды тишины по краям — режем, иначе фразы тянутся."""
    flt = (f"silenceremove=start_periods=1:start_silence=0.04:start_threshold={thr},areverse,"
           f"silenceremove=start_periods=1:start_silence=0.06:start_threshold={thr},areverse")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-af", flt, str(dst)], check=True)


def wav_seconds(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def voice_track(phrases: list[dict], workdir: Path, gap: float = 0.18, lead: float = 0.3, voice: str = "") -> tuple[Path, list[dict]]:
    """phrases: [{id, text}] → voice.mp3 + [{id, text, start, end}] в секундах.

    voice — имя Chirp3-HD без кода языка (например «Chirp3-HD-Kore»); пустое = голос по умолчанию.
    Голос один на весь ролик: и русские куски, и латиница читаются им же."""
    workdir.mkdir(parents=True, exist_ok=True)
    pieces, timings, t = [], [], lead
    pieces.append(("silence", lead))
    for i, ph in enumerate(phrases):
        wav = workdir / f"ph{i:02d}.wav"
        parts = []
        for j, (lang, seg) in enumerate(split_langs(ph["text"])):
            raw = workdir / f"ph{i:02d}_{j}_raw.wav"
            raw.write_bytes(synth_wav(seg, lang, voice))
            p = workdir / f"ph{i:02d}_{j}.wav"
            trim_silence(raw, p)
            raw.unlink()
            parts.append(p)
        if len(parts) == 1:
            parts[0].rename(wav)
        else:
            lst = workdir / f"ph{i:02d}.txt"
            lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(wav)], check=True)
        dur = wav_seconds(wav)
        timings.append({**ph, "start": round(t, 3), "end": round(t + dur, 3)})
        pieces.append(("file", wav))
        pieces.append(("silence", gap))
        t += dur + gap
    # склейка с паузами: silence через anullsrc
    lst = workdir / "voice.txt"
    lines = []
    for kind, val in pieces:
        if kind == "file":
            lines.append(f"file '{Path(val).name}'\n")
        else:
            sil = workdir / f"sil_{int(val * 1000)}.wav"
            if not sil.exists():
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=mono", "-t", str(val), "-c:a", "pcm_s16le", str(sil)], check=True)
            lines.append(f"file '{sil.name}'\n")
    lst.write_text("".join(lines))
    mp3 = workdir / "voice.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c:a", "libmp3lame", "-q:a", "2", str(mp3)], check=True)
    for p in workdir.glob("ph*.wav"):
        p.unlink()
    for p in workdir.glob("ph*.txt"):
        p.unlink()
    return mp3, timings
