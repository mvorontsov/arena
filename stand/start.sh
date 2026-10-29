#!/usr/bin/env bash
cd "$(dirname "$0")/.."
echo "[stand] Запуск mock RouterOS API на 127.0.0.1:8728..."
nohup python3 stand/mock_routeros_api.py --host 0.0.0.0 --port 8728 > /tmp/mock_routeros.log 2>&1 &
echo $! > /tmp/mock_routeros.pid
sleep 1
cat /tmp/mock_routeros.log | head -20
echo "PID: $(cat /tmp/mock_routeros.pid)"
# Проверяем
ss -tlnp | grep 8728 || netstat -tlnp | grep 8728 || echo "check port 8728"
curl -v telnet://127.0.0.1:8728 2>&1 | head -20 || nc -zv 127.0.0.1 8728 2>&1 | head -20
