#!/usr/bin/env bash
# Включает access-log по хосту spinhire.io в общем Caddy (контейнер coex-caddy-1)
# и повтор запроса до 15 с при рестарте uvicorn (чтобы боты не получали 502).
# Запуск на проде: bash /opt/spinhire/deploy/caddy-spinhire-log.sh
set -euo pipefail
F=/opt/coex/caddy/Caddyfile
cp -n "$F" "$F.bak-$(date +%F)" || true
if grep -q "spinhire-access.log" "$F"; then echo "уже настроено"; exit 0; fi
python3 - <<'PY'
p = "/opt/coex/caddy/Caddyfile"; s = open(p).read()
old = """spinhire.io, www.spinhire.io {
	tls {
		issuer acme {
			disable_http_challenge
		}
	}
	reverse_proxy 172.20.0.1:8100
}"""
new = """spinhire.io, www.spinhire.io {
	tls {
		issuer acme {
			disable_http_challenge
		}
	}
	log {
		output file /data/spinhire-access.log {
			roll_size 50mb
			roll_keep 6
		}
		format json
	}
	reverse_proxy 172.20.0.1:8100 {
		lb_try_duration 15s
		lb_try_interval 250ms
	}
}"""
assert old in s, "блок spinhire.io в Caddyfile не найден в ожидаемом виде — правь руками"
open(p, "w").write(s.replace(old, new)); print("Caddyfile обновлён")
PY
docker exec coex-caddy-1 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker exec coex-caddy-1 caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
echo "лог: /var/lib/docker/volumes/coex_caddy_data/_data/spinhire-access.log"
