#!/usr/bin/env bash
# Переводит spinhire.service на systemd socket activation: порт 8100 открыт постоянно,
# рестарты сервиса не дают 502. Идемпотентно. Запуск на проде под root.
set -euo pipefail
cp /opt/spinhire/deploy/spinhire.socket /etc/systemd/system/spinhire.socket
mkdir -p /etc/systemd/system/spinhire.service.d
cat > /etc/systemd/system/spinhire.service.d/socket.conf <<'CONF'
[Unit]
Requires=spinhire.socket
After=spinhire.socket

[Service]
# uvicorn принимает готовый сокет от systemd (fd 3) вместо --host/--port
ExecStart=
ExecStart=/opt/spinhire/venv/bin/uvicorn server.app:app --fd 3 --proxy-headers --forwarded-allow-ips=*
NonBlocking=true
CONF
systemctl daemon-reload
systemctl stop spinhire.service
systemctl enable --now spinhire.socket
systemctl start spinhire.service
sleep 12
systemctl is-active spinhire.socket spinhire.service
curl -s -o /dev/null -w "local probe %{http_code}\n" http://127.0.0.1:8100/llms.txt
