#!/usr/bin/env bash
cd "$(dirname "$0")/.."
echo "[stand] Запуск 2 CHR mock (из-за сетевых ограничений Arena — эмуляция)"
pkill -f mock_routeros_api.py 2>&1 || true
sleep 1
rm -f /tmp/mock_*.log /tmp/mock_*.pid

echo "[1/2] CHR-1 gw-core-01 127.0.0.1:8728 — CCR2116 7.25 эталон"
nohup python3 stand/mock_routeros_api.py --host 0.0.0.0 --port 8728 > /tmp/mock_8728.log 2>&1 &
echo $! > /tmp/mock_8728.pid
sleep 1
cat /tmp/mock_8728.log | head -5
ss -tlnp | grep 8728 && echo "✓ gw-core-01 LISTEN 8728" || echo "✗ fail"

echo ""
echo "[2/2] CHR-2 gw-lab-01 127.0.0.1:8729 — CHR 7.18 сломанный (для baseline)"
nohup python3 stand/mock_routeros_api.py --host 0.0.0.0 --port 8729 > /tmp/mock_8729.log 2>&1 &
echo $! > /tmp/mock_8729.pid
sleep 1
cat /tmp/mock_8729.log | head -5
ss -tlnp | grep 8729 && echo "✓ gw-lab-01 LISTEN 8729" || echo "✗ fail"

echo ""
python3 <<'PY'
import librouteros
for host, port, name in [('127.0.0.1',8728,'gw-core-01'),('127.0.0.1',8729,'gw-lab-01')]:
    try:
        api = librouteros.connect(host=host, username='admin', password='demo-only-changeme', port=port)
        r = list(api.path('system','resource'))[0]
        print(f"{name} {host}:{port} -> {r['board-name']} {r['version']}")
        api.close()
    except Exception as e:
        print(f"{name} FAIL: {e}")
PY
echo ""
echo "Стенд готов: 2 CHR на 8728+8729"
echo "  gw-core-01: 192.168.0.50/16 + 111.111.111.111/24 (эталон)"
echo "  gw-lab-01:  192.168.88.1/24  + 111.111.111.112/24 (сломанный)"
