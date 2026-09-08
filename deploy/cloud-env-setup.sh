#!/usr/bin/env bash
# Setup-скрипт облачного окружения SpinHire (claude.ai/code/environments → SpinHire → Setup script).
# Ставит всё для конвейера Shorts: ffmpeg, Remotion + headless Chrome, python-клиенты Google.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -qq && sudo apt-get install -y -qq ffmpeg fonts-noto-core fonts-noto-cjk libnss3 libatk-bridge2.0-0 libgbm1 libasound2 >/dev/null
cd "$(git rev-parse --show-toplevel)/video"
npm ci --silent
npx --yes remotion browser ensure >/dev/null
pip3 install -q google-cloud-texttospeech google-api-python-client google-auth-oauthlib google-auth-httplib2 pillow
echo "setup ok: node $(node -v), ffmpeg $(ffmpeg -version | head -1 | cut -d' ' -f3)"
