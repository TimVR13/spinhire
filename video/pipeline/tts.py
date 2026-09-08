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


def split_langs(text: str) -> list[tuple[str, str]]:
    segs = []
    for part in LATIN.split(text):
        part = part.strip()
        if not part:
            continue
        lang = "en-US" if LATIN.fullmatch(part) else "ru-RU"
        if segs and segs[-1][0] == lang:
            segs[-1] = (lang, segs[-1][1] + " " + part)
        else:
            segs.append((lang, part))
    return segs


def synth_wav(text: str, lang: str) -> bytes:
    r = client().synthesize_speech(
        input=tts.SynthesisInput(text=text),
        voice=tts.VoiceSelectionParams(language_code=lang, name=f"{lang}-{VOICE}"),
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


def voice_track(phrases: list[dict], workdir: Path, gap: float = 0.18, lead: float = 0.3) -> tuple[Path, list[dict]]:
    """phrases: [{id, text}] → voice.mp3 + [{id, text, start, end}] в секундах."""
    workdir.mkdir(parents=True, exist_ok=True)
    pieces, timings, t = [], [], lead
    pieces.append(("silence", lead))
    for i, ph in enumerate(phrases):
        wav = workdir / f"ph{i:02d}.wav"
        parts = []
        for j, (lang, seg) in enumerate(split_langs(ph["text"])):
            raw = workdir / f"ph{i:02d}_{j}_raw.wav"
            raw.write_bytes(synth_wav(seg, lang))
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
