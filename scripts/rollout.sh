#!/usr/bin/env bash
# scripts/rollout.sh — безопасная раскатка эталона на флот
# Использование: ./scripts/rollout.sh [diff|apply] [limit]
# Пример: ./scripts/rollout.sh diff gw-core-01
#         ./scripts/rollout.sh apply   # на все!

set -euo pipefail
cd "$(dirname "$0")/.."
MODE="${1:-diff}"
LIMIT="${2:-}"

echo "=== Роллаут baseline — mode=$MODE limit=${LIMIT:-all} — $(date -Is) ==="

# 1. Проверка стенда
./scripts/check-stand.sh || { echo "Стенд не прошёл — отмена"; exit 1; }

# 2. Линтинг эталона
echo -e "\n[lint] Проверка эталона..."
ansible-lint playbooks/04-baseline-apply.yml 2>&1 | head || true
ansible-playbook playbooks/04-baseline-apply.yml --syntax-check

# 3. Diff
if [[ "$MODE" == "diff" ]]; then
  echo -e "\n[diff] Запуск diff..."
  if [[ -n "$LIMIT" ]]; then
    ansible-playbook playbooks/04-baseline-apply.yml --tags diff --limit "$LIMIT" -v
  else
    ansible-playbook playbooks/04-baseline-apply.yml --tags diff -v
  fi
  echo "Проверьте /tmp/<host>-desired.rsc — если ок, запустите: $0 apply $LIMIT"

# 4. Apply
elif [[ "$MODE" == "apply" ]]; then
  read -p "⚠️ Применить эталон на ${LIMIT:-ВСЕ}? Это изменит роутеры! (y/N): " ans
  if [[ "$ans" != "y" ]]; then echo "Отменено"; exit 0; fi

  # Бэкап уже делает роль, но делаем ещё один явный
  echo "[backup] Бэкап перед apply..."
  ansible-playbook playbooks/02-inventory.yml ${LIMIT:+--limit "$LIMIT"} -v

  # Serial=1 уже в плейбуке — по одному
  if [[ -n "$LIMIT" ]]; then
    ansible-playbook playbooks/04-baseline-apply.yml --tags apply --limit "$LIMIT" -v
  else
    ansible-playbook playbooks/04-baseline-apply.yml --tags apply -v
  fi

  # Пост-аудит
  echo -e "\n[audit] Пост-раскаточный аудит..."
  ansible-playbook playbooks/03-audit.yml ${LIMIT:+--limit "$LIMIT"} -v

  # Запись в журнал
  SUM=$(sha256sum config/baseline/routeros-gateway.rsc | cut -d' ' -f1)
  echo "$(date -Is) ROLLOUT apply limit=${LIMIT:-all} checksum=$SUM mode=$MODE" >> ERROR_JOURNAL.md
  echo "✓ Записано в ERROR_JOURNAL.md"

else
  echo "Usage: $0 [diff|apply] [limit]"
  exit 1
fi
