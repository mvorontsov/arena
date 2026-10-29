# Журнал ошибок и решений (п.6 ТЗ)
# Формат: [timestamp] checksum=<sha256> size=<...> file=<путь> — описание + решение
# Контрольная сумма от файла с изменением — для целостности. Вести после каждой итерации. Старые файлы удалять (п.5 лимит 128МБ).

| Дата (ISO) | Файл | SHA256 | Размер | Ошибка / Решение |
|---|---|---|---|---|
| 2026-10-29T10:15:00+03:00 | `config/baseline/routeros-gateway.rsc` | `initial` | 4.1K | Проект создан — эталон шлюза ether1 WAN 111.111.111.111, bridge1 LAN 192.168.0.50/16 (ether2-10), firewall best practice ROS 7.25. Проверка: `./scripts/check-stand.sh` |
| 2026-10-29T10:15:00+03:00 | `inventory/hosts.yml` | `initial` | 1.2K | Инвентарь gw-core-01 (192.168.0.50) API 8728, группа mikrotik. Открытый вопрос: уточнить WAN маску/GW провайдера (group_vars/all.yml expected.wan) |
| 2026-10-29T08:01:54+00:00 | `config/baseline/routeros-gateway.rsc` | `d8444c74d9e3fde9bfecca9b5093bb8324eb25b6e6484e835aa06e3f804b8dcb` | 8.0K | Создан, syntax-check OK, стенд check-stand.sh |
| 2026-10-29T08:01:54+00:00 | `ansible.cfg` | `eac7bb3a302e94978600c2ca9238e6448cb81718c77438bc24a2ccf0a7533888` | 4.0K | Создан, syntax-check OK |
| 2026-10-29T08:01:54+00:00 | `playbooks/03-audit.yml` | `50e30c1ee430cd3b78356f720689002755159def55dcd53b347a5aac8ada45ba` | 4.0K | Создан, syntax-check OK |

# Шаблон:
# [2026-10-29T12:00:00+03:00] checksum=abc… size=4.1K file=config/baseline/routeros-gateway.rsc — Исправлен NAT masquerade: out-interface=ether1, проверено на стенде gw-lab-01, rollout.sh diff
