#!/usr/bin/env bash
# scripts/check-stand.sh — проверка стенда перед мажорными изменениями (п.7 ТЗ)
# Запуск: ./scripts/check-stand.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== [$(date -Is)] STAND CHECK — RouterOS 7.25 gateway 192.168.0.50 ==="
echo "Хост Ansible: $(hostname) — $(ip -4 addr show | grep 192.168 || true)"
echo "Inventory: $(cat inventory/hosts.yml | grep ansible_host || true)"

# 1. Проверка API
echo -e "\n[1/5] Проверка API 192.168.0.50:8728..."
if ansible mikrotik -m community.routeros.api_find -a "path=system resource" -i inventory/hosts.yml --limit gw-core-01 2>&1 | head -n 20; then
  echo "✓ API OK"
else
  echo "✗ API FAIL — проверьте /ip service print, firewall, LAN 192.168.0.0/16, стенд"
fi

# 2. Проверка инвентаризации (02)
echo -e "\n[2/5] Инвентаризация..."
ansible-playbook playbooks/02-inventory.yml --check -v 2>&1 | head -n 40 || true
echo "Факты ожидаются в reports/facts/gw-core-01.json"
ls -lh reports/facts/ 2>/dev/null | head || echo "(нет фактов — запустите 02 полностью)"

# 3. Аудит dry-run
echo -e "\n[3/5] Аудит (check mode)..."
ansible-playbook playbooks/03-audit.yml --check 2>&1 | tail -n 30 || true

# 4. Baseline diff (без применения)
echo -e "\n[4/5] Baseline diff..."
ansible-playbook playbooks/04-baseline-apply.yml --tags diff 2>&1 | tail -n 30 || true

# 5. Prometheus / Grafana
echo -e "\n[5/5] Мониторинг стек..."
if docker ps 2>/dev/null | grep -q prometheus; then
  echo "✓ prometheus running — $(curl -s http://localhost:9090/-/healthy || echo 'no health')"
else
  echo "→ запустите: docker compose -f monitoring/docker-compose.monitoring.yml up -d"
fi
if docker ps 2>/dev/null | grep -q grafana; then
  echo "✓ grafana running — http://$(hostname -I | awk '{print $1}'):3000 (admin/admin)"
else
  echo "→ grafana не запущена"
fi

# Размер workspace (п.5 ТЗ — не более 128МБ)
echo -e "\n[SIZE] Workspace: $(du -sh . | cut -f1) / 128M лимит"
du -sh . .cache reports 2>/dev/null || true
if [ "$(du -sm . | cut -f1)" -gt 128 ]; then
  echo "⚠️ Превышен лимит 128МБ — очистите .cache, reports, backups (см. п.5 ТЗ)"
fi

# Checksum ключевых файлов (для журнала п.6)
echo -e "\n[CHECKSUM] Контрольные суммы:"
sha256sum ansible.cfg inventory/hosts.yml config/baseline/routeros-gateway.rsc playbooks/*.yml 2>/dev/null | head -n 20

echo -e "\n=== Готово — $(date -Is) ==="
echo "Если всё OK — можно мажорные изменения. Логируйте в ERROR_JOURNAL.md с timestamp+checksum"
