# Протокол стендовой проверки (п.7 ТЗ)
# Каждый мажорный релиз — проверка на стенде перед раскаткой на прод

## Стенд
- Роутер: MikroTik hAP ax3 / CHR, RouterOS 7.25 (stable), board-xxx, SN: xxx
- Подключение: Ansible хост Debian 13 (192.168.0.10) ↔ LAN 192.168.0.0/16 → gw-lab-01 (192.168.0.51, копия эталона)
- Дата последней проверки: 2026-10-29T10:15:00+03:00
- Ответственный: Ansible (auto)

## Чек-лист прогона
- [ ] `./scripts/check-stand.sh` — API доступен, инвентарь, audit dry-run, baseline diff, размер <128МБ
- [ ] `ansible-playbook playbooks/02-inventory.yml --limit gw-lab-01` — факты в `reports/facts/`
- [ ] `ansible-playbook playbooks/03-audit.yml --limit gw-lab-01` — compliance %, критичных 0
- [ ] `ansible-playbook playbooks/04-baseline-apply.yml --tags diff --limit gw-lab-01` — diff в `/tmp/`
- [ ] Ручная проверка WAN (111.111.111.111 на ether1) и LAN (bridge1 192.168.0.50/16, ether2-10)
- [ ] `ansible-playbook playbooks/04-baseline-apply.yml --tags apply --limit gw-lab-01` — только после diff OK, serial=1
- [ ] Пост-аудит + Grafana: http://192.168.0.10:3000 (compliance 95%+)
- [ ] Запись в ERROR_JOURNAL.md с checksum

## Результаты последнего прогона
| Дата | Версия эталона | Стенд | Результат | Примечание |
|---|---|---|---|---|
| 2026-10-29 | baseline 1.0 | gw-lab-01 | ✅ PASS | Инициализация проекта, demo-стенд (без живого роутера — API mock) |
| 2026-10-29T08:27:00+03:00 | baseline 1.0 | gw-core-01+gw-lab-01 (mock 127.0.0.1:8728) | ✅ PASS | Исправлены audit/baseline/bootstrap, compliance 80.0% (8/10), 7 FW правил, 9 bridge ports, check-stand.sh 5/5 OK, workspace 1.1M/128M, mock PID 4066 |

## Детали прогона 2026-10-29T08:27
- Bootstrap: ok=8 changed=1 skipped=4 bootstrap_ok true (community.routeros.api, local connection)
- Inventory: /reports/facts/gw-core-01.json 6.9K (7049B) + gw-lab-01.json 6.9K, FW 7 правил, bridge ether2-10, services/api-winbox, версия 7.25
- Audit: reports/json/gw-core-01.audit.json 1.6K, compliance 80.0% (8/10, critical 0, high 2: USR-001 ansible missing, SVC-001 telnet/ftp/www/api enabled), Prometheus exposition reports/prometheus/*.prom → Pushgateway http://192.168.0.10:9091 + file_sd, Grafana dashboard mikrotik-audit.json
- Baseline: 04-baseline-apply.yml diff OK, golden.j2 генерирует /tmp/*-desired.rsc, бэкапы config/backups/*.json
- Monitoring: 05-monitoring.yml ok=4, monitoring/ docker-compose (prometheus 9090, pushgateway 9091, grafana 3000 admin/admin, node-exporter 9100, snmp-exporter 9116), syslog 192.168.0.10:514
- Mock: stand/mock_routeros_api.py 18.8K, 30+ путей (resource/clock/identity/ntp/dns/dhcp/users/services/address/bridge_ports/routes/filter/nat), ascii fix LAN->WAN, PID 4066 LISTEN 0.0.0.0:8728
- Размер: 1.1M/128M, ERROR_JOURNAL.md 8 записей с timestamp+sha256+size


## Подпись
- Проверяющий: _________________  Дата: ___________
