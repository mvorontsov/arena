# Best Practice для RouterOS 7.25 — шлюз (gateway)

> Источник: эталон `roles/mikrotik_audit/vars/best_practice.yml` — 24+ правила, покрывают п.3 ТЗ

## 1. Архитектура сети (ТЗ п.3)
- **WAN** — `ether1` с `111.111.111.111/24` (уточните маску и GW у провайдера), маршрут `0.0.0.0/0 → 111.111.111.1`
- **LAN** — `bridge1` с `192.168.0.50/16`, в бридже `ether2-10` (RSTP), интерфейс-листы `WAN=[ether1]`, `LAN=[bridge1]`
- **Проверки:** NET-001/002/003 — критичные, без них шлюз не маршрутизирует

## 2. System
- Identity ≠ MikroTik, timezone Europe/Moscow, NTP `pool.ntp.org + time.cloudflare.com` (SYS-001/002/003)
- ROS 7.25 stable, firmware `upgrade`, scheduled backup (MNT-001)

## 3. Пользователи
- Тех.учётка `ansible` group=full address=192.168.0.0/16 (USR-001) — создаёт 01-bootstrap.yml
- admin пароль не default, SSH strong-crypto (USR-002/003)

## 4. Сервисы
- Отключены: telnet, ftp, www, api (оставляем api-ssl 8729, ssh 22, winbox 8291) — SVC-001
- Все ограничены `address=192.168.0.0/16`, discovery/mac-server только LAN — SVC-002..005

## 5. Firewall (критично)
- Input: established→accept, invalid→drop, ICMP→accept, LAN→accept, **final drop** (FW-001..003)
- NAT: masquerade out-interface=ether1 (FW-004)
- Forward: established, LAN→WAN accept (FW-006)

## 6. DNS/DHCP
- DNS 1.1.1.1/8.8.8.8, не open resolver (DNS-001)
- DHCP pool 192.168.100.100-200, network 192.168.0.0/16 GW 192.168.0.50 (DHCP-001)

## 7. Мониторинг
- SNMP community не public, ограничен LAN (MON-001), syslog → 192.168.0.10 (MON-002)

## Несоответствия → рекомендации
Каждое правило в `best_practice.yml` имеет `remediation` — команду RouterOS. Аудит выводит её в `reports/json/*.audit.json` и в Prometheus метрику `mikrotik_audit_check`, Grafana показывает таблицу.
