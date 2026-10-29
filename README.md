# Управление роутерами MikroTik с помощью Ansible

> **ТЗ:** RouterOS **7.25 (API)**, шлюз `ether1: 111.111.111.111 ↔ bridge1(ether2-10): 192.168.0.50/16`, Ansible на **Debian 13** в `192.168.0.0/16`. Функции: подключение, тех.учётка, инвентаризация, аудит best practice, рекомендации, эталонный конфиг и раскатка, Grafana/Prometheus.

---

## 🚀 Быстрый старт (5 команд)

```bash
git clone <repo> && cd arena
cp inventory/hosts.example.yml inventory/hosts.yml   # заполните ansible_password (vault)
ansible-galaxy collection install -r collections/requirements.yml
ansible-playbook playbooks/01-bootstrap.yml          # создаёт ansible-учётку
ansible-playbook playbooks/02-inventory.yml          # факты → reports/facts/
ansible-playbook playbooks/03-audit.yml              # best practice → Grafana
# Мониторинг
docker compose -f monitoring/docker-compose.monitoring.yml up -d  # Prometheus 9090, Grafana 3000 admin/admin
```

**Стенд-проверка перед мажором:** `./scripts/check-stand.sh` (проверяет API, инвентарь, размер <128МБ, checksum)

---

## 📁 Структура

```
ansible.cfg                 # API, pipelining, cache
inventory/hosts.yml         # gw-core-01 192.168.0.50 (приват, не коммить)
group_vars/all.yml          # expected: WAN/LAN, tech_user, NTP/DNS, security, monitoring
group_vars/mikrotik.yml     # api 8728→8729
playbooks/
  01-bootstrap.yml          # тех.учётка ansible + api-ssl
  02-inventory.yml          # сбор фактов (15+ API-путей)
  03-audit.yml              # сверка с best_practice.yml → JSON + Prometheus
  04-baseline-apply.yml     # эталон → diff/apply serial=1
  05-monitoring.yml         # SNMP/syslog → Prometheus
roles/
  mikrotik_bootstrap/       # создание пользователя, api-ssl, strong-crypto
  mikrotik_inventory/       # 15 фактов + JSON для Grafana
  mikrotik_audit/           # 24 правила (SYS/NET/USR/SVC/FW/DNS/MON) → compliance%
  mikrotik_baseline/        # golden.j2 шаблон, бэкап, раскатка
  monitoring/               # SNMP, syslog
config/baseline/
  routeros-gateway.rsc      # эталон RSC — правится здесь, версионируется
  baseline.yml              # переменные эталона
  README.md
monitoring/
  prometheus/prometheus.yml # + pushgateway, snmp_exporter, blackbox
  grafana/dashboards/mikrotik-audit.json
  docker-compose.monitoring.yml
scripts/check-stand.sh      # п.7: стенд-тест + размер + checksum
scripts/rollout.sh          # safe раскатка: diff → apply → audit
scripts/journal.sh          # п.6: запись в журнал с timestamp+sha256
ERROR_JOURNAL.md            # журнал ошибок (обязателен)
STAND_CHECK.md              # протокол стенда
docs/best_practices.md      # описание 24 правил
docs/DEPLOYMENT.md          # подробная инструкция развёртывания (Debian 13 + CHR 7.25)
docs/CODE_REVIEW.md         # проверка кода на реальных CHR 7.25 / Debian 13

```

---

## 🔐 1. Bootstrap — тех.учётка

```bash
ansible-playbook playbooks/01-bootstrap.yml -k  # спросит пароль admin
# Создаёт ansible/full/192.168.0.0/16, включает api-ssl 8729, выключает telnet/ftp/www, ssh strong-crypto
# После — в inventory/hosts.yml поменяйте ansible_user: ansible, port: 8729, api_use_ssl: true
```

---

## 📦 2. Инвентаризация

Собирает: `system resource/identity/clock/routerboard, ip address/route, interface/bridge port, firewall filter/nat, ip service/dns/dhcp, user, ntp, discovery` → `reports/facts/<host>.json`

**Для Grafana:** `reports/facts/` — источник, плюс `mikrotik_facts` в памяти.

---

## ✅ 3. Аудит best practice (RouterOS 7.25 gateway)

Правила в `roles/mikrotik_audit/vars/best_practice.yml`:

| Категория | Примеры (ID) |
|---|---|
| **System** | NTP включён (SYS-001), timezone Europe/Moscow, ROS 7.25 |
| **Network** | WAN 111.111.111.111 на ether1 (NET-001), bridge1 192.168.0.50/16 с ether2-10, маршрут 0.0.0.0/0 |
| **Users** | ansible/full/192.168.0.0/16, admin не default, ssh strong-crypto |
| **Services** | telnet/ftp/www/api disabled, api-ssl только из LAN |
| **Firewall** | input established, drop invalid, final drop, NAT masquerade на ether1 |
| **DNS/DHCP/SNMP** | DNS 1.1.1.1/8.8.8.8, DHCP pool, SNMP не public |

**Запуск:** `ansible-playbook playbooks/03-audit.yml` → `reports/json/<host>.audit.json` + `reports/prometheus/<host>.prom` → Pushgateway `192.168.0.10:9091`

**Вывод:** compliance % (например 73.5%), failed/critical счётчики, и для каждого — `current vs expected + remediation` (готовая команда RouterOS).

---

## 🏆 4. Эталонный конфиг → раскатка

**Хранится:** `config/baseline/routeros-gateway.rsc` (полный RSC) + `baseline.yml`. Правите там → коммит → запись в `ERROR_JOURNAL.md` с checksum (`./scripts/journal.sh config/baseline/routeros-gateway.rsc "что изменено"`).

**Безопасно (serial=1):**
```bash
./scripts/rollout.sh diff              # только diff, без изменений
./scripts/rollout.sh diff gw-core-01  # на один
./scripts/rollout.sh apply             # применение (спросит y/N, сделает бэкап, затем push)
# или вручную:
ansible-playbook playbooks/04-baseline-apply.yml --tags diff
ansible-playbook playbooks/04-baseline-apply.yml --tags apply --limit gw-core-01
ansible-playbook playbooks/03-audit.yml  # пост-аудит → Grafana вырастет
```

Бэкапы: `config/backups/<host>-<date>.json` (не коммитить). Откат: `/import file=...`

---

## 📊 5. Grafana + Prometheus (п.9-10)

```bash
docker compose -f monitoring/docker-compose.monitoring.yml up -d
# Prometheus http://192.168.0.10:9090, Grafana http://192.168.0.10:3000 admin/admin
```

**Метрики:** `mikrotik_audit_compliance`, `mikrotik_audit_check{id,severity}`, `mikrotik_audit_critical`, `mikrotik_info`, `probe_success`

**Дашборд:** `monitoring/grafana/dashboards/mikrotik-audit.json` — Compliance stat, таблица несоответствий, график по хостам, инвентарь. Автообновление 30с.

**Аллерты:** `monitoring/prometheus/rules/mikrotik.yml` — MikrotikDown, AuditCritical, LowCompliance, VersionDrift.

---

## 📏 Ограничения (п.5-7)

- **Размер workspace <128МБ:** `scripts/check-stand.sh` проверяет `du -sh`, очищайте `.cache`, `reports`, `config/backups` (см. `make clean` если добавите)
- **Журнал:** `ERROR_JOURNAL.md` — каждая ошибка/фикс с `[timestamp] checksum=<sha256> size= file=<путь> — описание`. Добавляйте через `./scripts/journal.sh <file> "описание"`
- **Стенд:** `STAND_CHECK.md` + `scripts/check-stand.sh` — мажоры только после прогона на `gw-lab-01`
- **Вопросы:** задавайте — например, WAN маска/GW провайдера, нужен ли DHCP, SNMP community, vault пароли

---

## 🔧 Требования

- Ansible 2.16+ (`pipx install ansible`), коллекции: `ansible-galaxy collection install -r collections/requirements.yml`
- Python 3.11+, `community.routeros` 2.9+, доступ из `192.168.0.0/16` в `192.168.0.50:8728/8729`
- Для мониторинга: Docker + Compose на Debian 13

---

## 📚 Доки

- `docs/best_practices.md` — 24 правила подробно
- `docs/monitoring.md` — Prometheus/Grafana поток
- `config/baseline/README.md` — жизненный цикл эталона

**Лицензия:** MIT
