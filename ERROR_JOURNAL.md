# Журнал ошибок и решений (п.6 ТЗ)
# Формат: [timestamp] checksum=<sha256> size=<...> file=<путь> — описание + решение

| Дата (ISO) | Файл | SHA256 | Размер | Ошибка / Решение |
|---|---|---|---|---|
| 2026-10-29T10:15:00+03:00 | `config/baseline/routeros-gateway.rsc` | `initial` | 4.1K | Проект создан — эталон шлюза ether1 WAN 111.111.111.111, bridge1 LAN 192.168.0.50/16 (ether2-10), firewall best practice ROS 7.25. Проверка: `./scripts/check-stand.sh` |
| 2026-10-29T10:15:00+03:00 | `inventory/hosts.yml` | `initial` | 1.2K | Инвентарь gw-core-01 (192.168.0.50) API 8728, группа mikrotik. Открытый вопрос: WAN маска/GW (group_vars/all.yml expected.wan) |
| 2026-10-29T08:01:54+00:00 | `config/baseline/routeros-gateway.rsc` | `d8444c74d9e3fde9bfecca9b5093bb8324eb25b6e6484e835aa06e3f804b8dcb` | 8.0K | Создан, syntax-check OK, стенд check-stand.sh |
| 2026-10-29T08:01:54+00:00 | `ansible.cfg` | `eac7bb3a302e94978600c2ca9238e6448cb81718c77438bc24a2ccf0a7533888` | 4.0K | Создан, syntax-check OK |
| 2026-10-29T08:04:09+00:00 | `group_vars/all.yml` | `d719f0ae17c4ef6fb31d22b192d9b0d6321175bd60b8c0876788a4d1219efe11` | 1.6K | Скорректирован dhcp_pool на 192.168.0.100-192.168.0.200 по выбору заказчика (yes_dhcp), проверка стенда, размер 891K<128M |

# Шаблон:
# [2026-10-29T12:00:00+03:00] checksum=abc… size=4.1K file=config/baseline/routeros-gateway.rsc — Исправлен NAT masquerade: out-interface=ether1, проверено на стенде gw-lab-01, rollout.sh diff
