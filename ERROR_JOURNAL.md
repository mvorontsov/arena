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
| 2026-10-29T08:27:00+03:00 | `roles/mikrotik_audit/tasks/main.yml` | `84763b0491f35d1839d10df485dd24b98da991910a36b05563e521c062770a6c` | 16.3K | Исправлен NTP `ntp_servers[0] in` → `pool.ntp.org in`, timezone/gateway defaults, FW `connection-state` → `map(default='')`, compliance `max` → `[...,1]\|max`, добавлена загрузка фактов из файла; проверка `ansible-playbook 03-audit.yml` 80.0% 8/10, reports/json/*.audit.json + prom OK |
| 2026-10-29T08:27:00+03:00 | `roles/mikrotik_baseline/templates/golden.j2` | `0039de909b473fa6a743c825d5605133fcfad030a07181e92615d52202100a06` | 4.4K | Исправлены `ntp_enabled`, `expected.*`, `dns_servers`, `tech_user`, `monitoring.*` с `|default()` — `ansible-playbook 04-baseline-apply.yml` diff OK, /tmp/*-desired.rsc генерируется, бэкапы в config/backups |
| 2026-10-29T08:27:00+03:00 | `roles/mikrotik_bootstrap/tasks/main.yml` | `a22d93f28dfd5fdd9635d5382fad1069c6fed46c6ddff0931c867b4f1698e6c5` | 5.7K | Исправлен `when: res_resource.failed is not defined` → `not failed|default(false)` + `msg|length>0`, `bootstrap_ok` true, bootstrap 01-bootstrap.yml ok=8 changed=1 |
| 2026-10-29T08:27:00+03:00 | `playbooks/03-audit.yml` | `6d100ad90884cbfcb8105860907bfbbba27203176a8a615c125cfa9b039ea901` | 1.9K | Исправлены пути `audit_output_dir: playbook_dir/../reports`, `audit_fail_on_critical|default(false)`, post_tasks проходят, audit 80% |
| 2026-10-29T08:27:00+03:00 | `stand/mock_routeros_api.py` | `14432d6f37a51d0741d65a691325de0c1427ce58f79e258b7ede3451e15dcce3` | 18.8K | Исправлен unicode `LAN → WAN` → `LAN -> WAN`, ascii codec error на filter/print устранён, mock PID 4066 0.0.0.0:8728, librouteros filter 7 правил OK |
| 2026-10-29T08:27:00+03:00 | `roles/mikrotik_inventory/tasks/main.yml` | `c4f2aa624897a9fa04a24fa0898035394298e6a52ca2b0c1e960c1bec2813577` | 8.4K | Исправлен dest `playbook_dir/../reports/facts`, инвентаризация пишет в /reports/facts/gw-core-01.json 6.9K, 7 FW правил, 9 bridge ports |
| 2026-10-29T08:27:00+03:00 | `scripts/check-stand.sh` | `8f317ed9f5641999753f37cd55c8205939debfbff88b50a649062c1165bf3245` | 2.8K | Исправлен `api_find` → `api path='/system resource' print`, стенд check-stand.sh 5/5 OK, размер workspace 1.1M/128M |
| 2026-10-29T08:27:00+03:00 | `roles/monitoring/tasks/main.yml` | `bd27566fee44392c8dba78e866f759019b3c607f407c21f0d7117edcd52c4e71` | 1.1K | Добавлены `|default()` для syslog, 05-monitoring.yml ok=4, Prometheus+Grafana конфиги валидны |
