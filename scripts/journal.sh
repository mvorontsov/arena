#!/usr/bin/env bash
# scripts/journal.sh — добавить запись в ERROR_JOURNAL.md с меткой времени и checksum (п.6 ТЗ)
# Использование: ./scripts/journal.sh "файл" "описание ошибки/решения"
# Пример: ./scripts/journal.sh config/baseline/routeros-gateway.rsc "исправлен NAT masquerade"
set -euo pipefail
cd "$(dirname "$0")/.."

FILE="${1:-}"
MSG="${2:-}"
if [[ -z "$FILE" || -z "$MSG" ]]; then
  echo "Usage: $0 <file> \"описание\""
  exit 1
fi

TS="$(date -Is)"
if [[ -f "$FILE" ]]; then
  SUM="$(sha256sum "$FILE" | cut -d' ' -f1)"
  SIZE="$(du -h "$FILE" | cut -f1)"
else
  SUM="FILE_NOT_FOUND"
  SIZE="-"
fi

echo "[$TS] checksum=$SUM size=$SIZE file=$FILE — $MSG" >> ERROR_JOURNAL.md
echo "→ Записано в ERROR_JOURNAL.md: [$TS] $FILE ($SUM) — $MSG"
