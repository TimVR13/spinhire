#!/usr/bin/env bash
# Setup-скрипт облачного окружения SpinHire. Запускается ДО входа в репо (cwd может быть $HOME),
# поэтому репозиторий ищем сами; если не нашли — ставим только системные пакеты, остальное доставит routine.
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive
SUDO=""; command -v sudo >/dev/null 2>&1 && [ "$(id -u)" != "0" ] && SUDO="sudo"
$SUDO apt-get update -qq >/dev/null 2>&1 || true
$SUDO apt-get install -y -qq ffmpeg libnss3 libatk-bridge2.0-0 libgbm1 fonts-noto-core >/dev/null 2>&1 || true
$SUDO apt-get install -y -qq libasound2t64 >/dev/null 2>&1 || $SUDO apt-get install -y -qq libasound2 >/dev/null 2>&1 || true
# системный cryptography 41 в образе ломает импорт google.cloud (pyo3 panic) — переустанавливаем поверх
pip3 install -q -U --ignore-installed --break-system-packages cryptography >/dev/null 2>&1 || true
pip3 install -q google-cloud-texttospeech google-api-python-client google-auth-oauthlib google-auth-httplib2 pillow 2>/dev/null \
  || pip3 install -q --break-system-packages google-cloud-texttospeech google-api-python-client google-auth-oauthlib google-auth-httplib2 pillow || true
# Chromium в рендере ходит через egress-прокси с подменой TLS: добавляем CA прокси в NSS-базу, иначе шрифты с gstatic не грузятся
$SUDO apt-get install -y -qq libnss3-tools >/dev/null 2>&1 || true
if command -v certutil >/dev/null 2>&1; then
  mkdir -p "$HOME/.pki/nssdb" && certutil -d "sql:$HOME/.pki/nssdb" -N --empty-password >/dev/null 2>&1 || true
  for f in /usr/local/share/ca-certificates/*.crt "${NODE_EXTRA_CA_CERTS:-}"; do
    [ -f "$f" ] && certutil -d "sql:$HOME/.pki/nssdb" -A -t "C,," -n "$(basename "$f")" -i "$f" >/dev/null 2>&1 || true
  done
fi
VIDEO="$(find "$HOME" /workspace /repo /src -maxdepth 4 -type f -name package.json -path '*/video/package.json' 2>/dev/null | head -1)"
if [ -n "$VIDEO" ]; then
  cd "$(dirname "$VIDEO")" && (npm ci --silent || npm install --silent) && (npx --yes remotion browser ensure >/dev/null 2>&1 || true)
  echo "setup ok: $(dirname "$VIDEO"), node $(node -v 2>/dev/null), ffmpeg $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f3)"
else
  echo "setup ok (системные пакеты); video/ не найден из $(pwd) — npm ci сделает routine"
fi
exit 0
