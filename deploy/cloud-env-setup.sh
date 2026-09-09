#!/usr/bin/env bash
# Setup-скрипт облачного окружения SpinHire (claude.ai/code/environments → Spinhire Cloud → Setup script).
# Ставит всё для конвейера Shorts: ffmpeg, Remotion + headless Chrome, python-клиенты Google.
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive
SUDO=""; command -v sudo >/dev/null 2>&1 && [ "$(id -u)" != "0" ] && SUDO="sudo"
$SUDO apt-get update -qq >/dev/null 2>&1 || true
$SUDO apt-get install -y -qq ffmpeg libnss3 libatk-bridge2.0-0 libgbm1 fonts-noto-core >/dev/null 2>&1 || true
$SUDO apt-get install -y -qq libasound2t64 >/dev/null 2>&1 || $SUDO apt-get install -y -qq libasound2 >/dev/null 2>&1 || true
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT/video" || { echo "нет каталога video/"; exit 1; }
npm ci --silent || npm install --silent
npx --yes remotion browser ensure >/dev/null 2>&1 || true
pip3 install -q google-cloud-texttospeech google-api-python-client google-auth-oauthlib google-auth-httplib2 pillow 2>/dev/null \
  || pip3 install -q --break-system-packages google-cloud-texttospeech google-api-python-client google-auth-oauthlib google-auth-httplib2 pillow
echo "setup ok: node $(node -v 2>/dev/null), ffmpeg $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f3)"
