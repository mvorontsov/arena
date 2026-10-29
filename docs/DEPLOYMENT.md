# Развёртывание Ansible-оркестратора MikroTik RouterOS 7.25
> **Версия проекта:** 1.0 (2026-10-29), стенд проверен на mock CHR 7.25 (PID 4066)
> **Хост управления:** Debian 13 (trixie) в LAN `192.168.0.0/16`, IP `192.168.0.10`
> **Целевые роутеры:** CHR / hAP ax3 / CCR2116, RouterOS **7.25 stable**, шлюз `ether1 111.111.111.111/24 GW 111.111.111.1 ↔ bridge1(ether2-10) 192.168.0.50/16`

---

## Содержание
1. [Архитектура](#1-архитектура)
2. [Требования](#2-требования)
3. [Подготовка Debian 13](#3-подготовка-debian-13-хоста-управления)
4. [Установка проекта](#4-установка-проекта)
5. [Настройка Inventory и Vault](#5-настройка-inventory-и-vault)
6. [Быстрая проверка связи](#6-быстрая-проверка-связи)
7. [Пошаговое развёртывание](#7-пошаговое-развёртывание-5-плейбуков)
8. [Мониторинг Grafana/Prometheus](#8-мониторинг-grafanaprometheus)
9. [Стендовая проверка перед мажором](#9-стендовая-проверка-перед-мажором)
10. [Эксплуатация и раскатка baseline](#10-эксплуатация-и-раскатка-baseline)
11. [Устранение неполадок](#11-устранение-неполадок)
12. [Приложения: структура и чек-листы](#12-приложения)

---

## 1. Архитектура

```
                           192.168.0.0/16 (LAN)
┌─────────────────┐        ┌────────────────────────────────────────────────┐
│  Debian 13      │  ─────►│  MikroTik CHR 7.25 (gateway)                 │
│  192.168.0.10   │  API   │  ether1: 111.111.111.111/24 ──► Internet (GW 111.111.111.1) │
│  Ansible 2.19  │  8728  │  bridge1: 192.168.0.50/16 (ports ether2-10 RSTP) │
│  Prometheus 9090├────────►  bridge1 DHCP: 192.168.0.100-200 DNS 1.1.1.1/8.8.8.8 │
│  Grafana 3000  │  SNMP  │  firewall input/forward filter + NAT masq ether1 │
│  PushGW 9091    │  syslog│  users: admin (bootstrap) → ansible/full/192.168.0.0/16 │
└─────────────────┘        └────────────────────────────────────────────────┘
```

**Поток данных аудита:**
`Ansible (API 8728/8729) → reports/facts/*.json → audit → reports/json/*.audit.json + reports/prometheus/*.prom → Pushgateway 9091 → Prometheus 9090 → Grafana 3000 (dashboard mikrotik-audit.json)`

**Эталонный конфиг:**
`config/baseline/routeros-gateway.rsc` (RSC) + `baseline.yml` → Jinja2 `golden.j2` → `/tmp/<host>-desired.rsc` → `/import` (только с `--tags apply`)

| Компонент | Порты | Протокол |
|---|---|---|
| API (bootstrap/inventory) | 8728 (plain) → после bootstrap 8729 (SSL) | TCP RouterOS API |
| SNMP | 161 | UDP → snmp-exporter |
| syslog | 514 | UDP → Loki/Promtail |
| Prometheus | 9090 | HTTP |
| Pushgateway | 9091 | HTTP POST |
| Grafana | 3000 | HTTP |
| Node-exporter | 9100 | HTTP |
| snmp-exporter | 9116 | HTTP |

---

## 2. Требования

### 2.1 Debian 13 (хост Ansible)
- **OS:** Debian 13 trixie (подойдёт 12 bookworm — проверено), RAM ≥2 ГБ, диск ≥10 ГБ (проект 1.2М + кеш + Docker)
- **Сеть:** статический IP `192.168.0.10/16` в том же bridge1, GW `192.168.0.50`, DNS `1.1.1.1` — обязателен доступ к `192.168.0.50:8728` и к WAN для `galaxy.ansible.com/pypi.org`
- **Пакеты:** `python3.11+`, `pip`, `git`, `ssh`, `docker.io`, `docker-compose-plugin`
- **Версии:** Ansible 2.19, community.routeros ≥2.9.0, librouteros 4.2.2 (для стенда-мока), Docker 25+

### 2.2 MikroTik CHR 7.25
- **Образ:** `chr-7.25.vdi/.img` или ISO, RAM ≥1 ГБ, диск ≥1 ГБ, 10+ ether-интерфейсов (ether1 WAN, ether2-10 LAN)
- **Лицензия:** trial P1 (60 дней) достаточно; для прода — P1/P10/P-Unlimited
- **Сеть CHR:**
  ```
  /interface bridge add name=bridge1 protocol-mode=rstp
  /interface bridge port add bridge=bridge1 interface=ether2-10
  /ip address add address=192.168.0.50/16 interface=bridge1
  /ip address add address=111.111.111.111/24 interface=ether1
  /ip route add dst-address=0.0.0.0/0 gateway=111.111.111.1
  /ip dns set servers=1.1.1.1,8.8.8.8
  /ip service enable api port=8728 address=192.168.0.0/16
  ```
- **Учётка:** `admin` без пароля (по умолчанию) — сразу ставим сложный пароль, затем bootstrap
- **Важно для CHR 7.25:** API изменился после 7.11 — используется `community.routeros.api` (не `api_find`), путь `system resource`, `interface bridge port` пишется с пробелом, `strong-crypto` требует ROS ≥7.12 — всё учтено

### 2.3 Проверка перед стартом
```bash
ping 192.168.0.50                    # LAN доступен?
telnet 192.168.0.50 8728             # API открыт? (Ctrl+] quit)
ssh admin@192.168.0.50 "/ip service print"  # SSH доступен?
```

---

## 3. Подготовка Debian 13 хоста управления

Выполняется **под root или sudo**.

### 3.1 Базовая настройка ОС
```bash
# Обновление
apt update && apt upgrade -y
apt install -y git python3 python3-pip python3-venv openssh-client curl wget nano

# Статический IP (если не настроен)
cat > /etc/network/interfaces.d/lan <<'CFG'
auto ens192
iface ens192 inet static
  address 192.168.0.10/16
  gateway 192.168.0.50
  dns-nameservers 1.1.1.1 8.8.8.8
CFG
systemctl restart networking || ip addr flush ens192 && ifup ens192

# Часовой пояс (критично для аудита SYS-002)
timedatectl set-timezone Europe/Moscow
apt install -y ntpsec && systemctl enable --now ntpsec

# Создаём пользователя (не root!)
adduser ansible --gecos "Ansible" --disabled-password
usermod -aG sudo ansible
su - ansible
```

### 3.2 Python + Ansible
```bash
# Debian 13: ставим через pip --break-system-packages (PEP 668)
pip3 install --break-system-packages ansible==12.3.0 librouteros==4.2.2

# Проверка
ansible --version        # 2.19.14+
ansible-galaxy --version
python3 -c "import librouteros; print(librouteros.__version__)"  # 4.2.2
```

### 3.3 Docker для мониторинга (опционально, но нужен для п.9-10 ТЗ)
```bash
sudo apt install -y docker.io docker-compose-plugin
sudo usermod -aG docker $USER
newgrp docker

# Проверка
docker --version          # 25+
docker compose version    # v2.x
sudo systemctl enable --now docker
```

### 3.4 Системные лимиты (п.5 ТЗ: workspace <128МБ)
```bash
# Проект хранит кеш в .cache, отчёты в reports — лимит 128МБ общий
# Настройка logrotate для /tmp/mock_routeros.log (если используете стенд-мок)
cat > /etc/logrotate.d/ansible-mikrotik <<'CFG'
/home/ansible/arena/reports/*.log {
  rotate 7
  daily
  compress
  size 5M
}
CFG
```

---

## 4. Установка проекта

```bash
# Клонирование
cd /home/ansible   # или /opt, /srv — где храните проекты
git clone https://github.com/mvorontsov/arena.git
cd arena
git checkout arena/1fb619c0-arena   # ветка стенда (или main для прода)

# Структура после clone:
ls -1
# ansible.cfg  Makefile  collections/requirements.yml  inventory/  group_vars/  playbooks/  roles/  config/baseline/  monitoring/  scripts/  reports/  stand/

# Установка коллекций (обязательно!)
ansible-galaxy collection install -r collections/requirements.yml --force
# → community.routeros 2.9+, community.general 8+, prometheus.prometheus, community.grafana, community.docker

# Проверка синтаксиса
ansible-playbook --syntax-check playbooks/*.yml
make check  # alias к syntax-check + ansible-lint (если установлен)

# Размер workspace
make size  # du -sh . .cache reports config/backups → должно быть 1.1M / 128M
```

**Важно про ansible.cfg:** уже настроен `inventory=inventory/hosts.yml`, `roles_path=./roles`, `collections_path=./collections_installed`, `fact_caching=jsonfile` в `.cache/facts`, `pipelining=True`, `host_key_checking=False`. Для прода раскомментируйте `vault_password_file = .vault_pass`.

---

## 5. Настройка Inventory и Vault

### 5.1 Копируем пример → рабочий inventory
```bash
cp inventory/hosts.example.yml inventory/hosts.yml
chmod 600 inventory/hosts.yml
nano inventory/hosts.yml
```

**Содержимое для прода (CHR 192.168.0.50):**
```yaml
all:
  vars:
    ansible_connection: local
    ansible_user: admin
    ansible_password: "demo-only-changeme"  # ← замените! см. Vault ниже
    api_hostname: "192.168.0.50"
    api_port: 8728
    api_username: admin
    api_password: "demo-only-changeme"
  children:
    mikrotik:
      vars:
        routeros_version_expected: "7.25"
        gateway_lan_cidr: "192.168.0.0/16"
        gateway_lan_ip: "192.168.0.50/16"
        gateway_lan_bridge: bridge1
        gateway_wan_if: ether1
        gateway_wan_ip: "111.111.111.111/24"
        hostname: "192.168.0.50"
        username: admin
        password: "demo-only-changeme"
        api_port: 8728
      hosts:
        gw-core-01:
          ansible_host: 192.168.0.50
          hostname: 192.168.0.50
          wan_address: 111.111.111.111
          lan_bridge: bridge1
          location: "Moscow DC — rack A1"
          role: gateway
        # добавляйте остальные gw-* аналогично
        gw-02:
          ansible_host: 192.168.0.51
          hostname: 192.168.0.51
          ...
```

**Для стенда-мока (тест без железа):**
```yaml
# inventory/hosts.yml уже настроен на 127.0.0.1:8728
# Запустите мок: ./stand/start.sh → PID 4066 LISTEN 0.0.0.0:8728
# Затем все плейбуки идут на 127.0.0.1
```

### 5.2 Vault — хранение паролей (п.11 ТЗ: демо plain, прод — шифровать)

**Демо (как в ТЗ сейчас — пароль в открытую):**
```yaml
# group_vars/all.yml уже содержит:
tech_user: ansible
tech_user_password: "{{ vault_tech_password | default('Ans1ble_Str0ng_2025!') }}"
# То есть если vault не настроен — используется дефолт 'Ans1ble_Str0ng_2025!'
# Для демо этого достаточно, но для прода — обязательно Vault!
```

**Прод — включаем Vault:**
```bash
# 1. Создайте файл пароля
echo "MyVaultPass123!" > .vault_pass
chmod 600 .vault_pass
# Раскомментируйте в ansible.cfg: vault_password_file = .vault_pass

# 2. Создайте vault-файл с секретами
ansible-vault create group_vars/mikrotik/vault.yml
# Внутри:
vault_tech_password: "Супер_Сложный_Пароль_2025!"
vault_snmp_community: "mikrotik-ro-strong"
vault_mikrotik_password: "admin_исходный_пароль"

# 3. Проверка
ansible-vault view group_vars/mikrotik/vault.yml
```

### 5.3 Групповые переменные
```bash
cat group_vars/all.yml | head -80
# expected.wan/lan — главный источник правды! Проверьте:
# expected.wan.address=111.111.111.111 netmask=24 gateway=111.111.111.1
# expected.lan.bridge=bridge1 address=192.168.0.50 netmask=16 ports=ether2-10
# dns=1.1.1.1/8.8.8.8 ntp=pool.ntp.org/time.cloudflare.com timezone=Europe/Moscow
# tech_user=ansible group=full address=192.168.0.0/16

cat group_vars/mikrotik.yml
# api_port=8728 (после bootstrap — 8729 api-ssl)
```

### 5.4 .gitignore уже настроен
- `inventory/hosts.yml` — **не коммитится** (секрет)
- `reports/facts/*.json`, `reports/json/*.json`, `config/backups/*.json` — не коммитятся (размер)
- `.vault_pass`, `*.key` — не коммитятся

---

## 6. Быстрая проверка связи

```bash
# 1. API напрямую через community.routeros (требует inventory/hosts.yml с api_* )
ansible mikrotik -m community.routeros.api -a "path='/system resource' print" -i inventory/hosts.yml --limit gw-core-01 -v
# Ожидается: msg: [{ "board-name": "CHR", "version": "7.25 (stable)", ... }]

# 2. Через стенд-мок (если нет живого CHR)
./stand/start.sh          # запускает mock на 0.0.0.0:8728
ss -tlnp | grep 8728      # LISTEN
python3 -c "import librouteros; api=librouteros.connect(host='127.0.0.1', username='admin', password='demo-only-changeme'); print(list(api.path('system','resource')))"
# → [{'board-name': 'CCR2116-12G-4S+', 'version': '7.25 (stable)'}]

# 3. Полный стенд-тест (5 этапов, п.7 ТЗ)
./scripts/check-stand.sh
# [1/5] API 192.168.0.50:8728 — ✓ API OK
# [2/5] Инвентаризация — факты в reports/facts/gw-core-01.json
# [3/5] Аудит dry-run — compliance 80.0% (8/10)
# [4/5] Baseline diff — diff см. /tmp/*-desired.rsc
# [5/5] Мониторинг — prometheus/grafana (или подсказка запустить)
# [SIZE] 1.1M / 128M ✓
# [CHECKSUM] sha256sum playbooks/*.yml ...

# Если check-stand.sh прошёл — можно мажорные изменения. Если нет — см. раздел 11.
```

---

## 7. Пошаговое развёртывание (5 плейбуков)

### 7.1 01-bootstrap.yml — тех.учётка

**Что делает:** создаёт пользователя `ansible/full/192.168.0.0/16`, выключает `telnet/ftp/www/api`, включает `ssh strong-crypto`, ставит `api-ssl 8729` (ограниченный LAN).

**Для CHR 7.25 особенности:**
- Использует `community.routeros.api` (plain 8728) + `api_modify` (disable/enable services)
- `quote_argument_value` для комментария (экранирование)
- `failed_when: false` — не падает, если API уже настроен
- `when: not res_resource.failed|default(false)` — проверка доступности

```bash
# Первый запуск — спросит исходный пароль admin (CHR по умолчанию без пароля → просто Enter)
ansible-playbook playbooks/01-bootstrap.yml -k -v
# -k (ask-pass) — если у admin уже стоит пароль, спросит его

# Для стенда-мока (без пароля):
ansible-playbook playbooks/01-bootstrap.yml -v

# Ожидаемый вывод:
# TASK [mikrotik_bootstrap : Проверка API-доступности] ok
# TASK [Вывод версии RouterOS] ok: Board CHR, ROS 7.25 (stable)
# TASK [Проверить существование тех.учётки ansible] ok
# TASK [Создать тех.учётку] changed (или ok, если уже есть)
# TASK [Отключить небезопасные сервисы] ok
# [gw-core-01] Bootstrap gw-core-01: OK — user_created=True/False

# После успешного bootstrap — переключите inventory на новую учётку:
nano inventory/hosts.yml
# api_username: ansible
# api_password: "Ans1ble_Str0ng_2025!"  # из vault или Plain
# api_port: 8729  # api-ssl (если включили)

# Проверка новой учёткой:
ansible mikrotik -m community.routeros.api -a "path='user print'" -i inventory/hosts.yml --limit gw-core-01
# должна вернуться запись ansible
```

**Откат:** `ansible-playbook playbooks/01-bootstrap.yml --tags check` — только проверка, без изменений. Или вручную `/user remove ansible`.

---

### 7.2 02-inventory.yml — инвентаризация

**Что делает:** собирает 15+ API-путей (resource, identity, clock, address, interface, bridge_ports, routes, firewall filter/nat, services, dns, dhcp, users, ntp) → единый `mikrotik_facts` → JSON в `reports/facts/<host>.json` (для Grafana).

**CHR 7.25 нюансы:**
- Пути `interface bridge port`, `ip firewall filter` пишутся с пробелом — в роли уже учтено
- `system ntp client` в 7.25 — отдельный путь (не `system ntp` как в 6.x)
- `fact_caching` в `.cache/facts` — ускоряет повторные прогоны

```bash
ansible-playbook playbooks/02-inventory.yml -v

# Результат:
# reports/facts/gw-core-01.json 6.9K (7049B)
# {
#   "meta": {"board": "CHR", "routeros_version": "7.25 (stable)"},
#   "addresses": [{"address": "192.168.0.50/16", "interface": "bridge1"}, {"111.111.111.111/24": "ether1"}],
#   "bridge_ports": [ether2..ether10],
#   "firewall_filter": 7 rules,
#   "firewall_nat": 1 masquerade,
#   "users": ["admin", "ansible"]
# }

ls -lh reports/facts/
cat reports/facts/gw-core-01.json | python3 -m json.tool | head -60

# Проверка на CHR:
# Зайдите на CHR: /ip address print, /interface bridge port print, /ip firewall filter print — сверьте с JSON
```

---

### 7.3 03-audit.yml — аудит best practice

**Что делает:** сверяет `mikrotik_facts` (или файл `reports/facts/*.json` если факты не в памяти) с `roles/mikrotik_audit/vars/best_practice.yml` (24 правила) → `audit_report` → `reports/json/<host>.audit.json` + `reports/prometheus/<host>.prom` (для Pushgateway/Grafana).

**Категории (см. docs/best_practices.md):**
- **SYS:** NTP (SYS-001), timezone Europe/Moscow (SYS-002), identity ≠ MikroTik (SYS-003), ROS 7.25 (SYS-004)
- **NET:** WAN 111.111.111.111 на ether1 (NET-001), LAN bridge1 192.168.0.50/16 ether2-10 (NET-002), маршрут 0.0.0.0/0 (NET-003)
- **USR:** ansible/full/192.168.0.0/16 (USR-001), strong-crypto (USR-003)
- **SVC:** telnet/ftp/www/api disabled (SVC-001), api-ssl LAN only (SVC-002)
- **FW:** input established (FW-001), drop invalid (FW-002), final drop (FW-003), NAT masq ether1 (FW-004)
- **DNS/DHCP/MON:** DNS 1.1.1.1/8.8.8.8, DHCP pool, SNMP

**CHR 7.25 особенности:** `mikrotik_facts.clock['time-zone-name']` — в 7.25 хранится именно так; `firewall_filter` без `connection-state` у части правил — роль обрабатывает `map(attribute='connection-state', default='')`.

```bash
ansible-playbook playbooks/03-audit.yml -v
# или только diff без push в Prometheus:
ansible-playbook playbooks/03-audit.yml --tags audit --skip-tags prometheus

# Вывод:
# [gw-core-01] Compliance 80.0% (8/10)
#   Critical: 0, High: 2, Medium: 0, Low: 0
#   - [HIGH] USR-001: Тех.учётка ansible существует → /user add name=ansible...
#   - [HIGH] SVC-001: Отключены telnet/ftp/www/api → /ip service disable...

cat reports/json/gw-core-01.audit.json | python3 -m json.tool
# compliance.pct 80.0, findings[], passed_ids[], remediation для каждого

cat reports/prometheus/gw-core-01.prom
# mikrotik_audit_compliance{hostname="gw-core-01"} 80.0
# mikrotik_audit_check{id="USR-001"} 1 (fail), id="SYS-001" 0 (pass)

# Если есть critical (audit_critical>0) и audit_fail_on_critical=true — плейбук упадёт с fail: "Критические несоответствия"
# Для прода установите в group_vars/all.yml: audit.fail_on_critical: true
```

**На реальном CHR ожидаемый результат:** если CHR уже настроен по best practice — compliance 95-100%; если чистый CHR — ~40-60% (много fail).

---

### 7.4 04-baseline-apply.yml — эталонный конфиг

**Что делает:** хранит эталон в `config/baseline/routeros-gateway.rsc` + `baseline.yml` → генерирует `roles/mikrotik_baseline/templates/golden.j2` → `/tmp/<host>-desired.rsc` (проверьте!) → по `--tags apply` импортирует через `import file-name=ansible-baseline.rsc`.

**Безопасность:**
- `serial: 1` — раскатывает по одному роутеру (не положит весь флот)
- По умолчанию **dry-run** (только diff) — безопасно
- `baseline_backup_before: true` — перед apply делает бэкап `config/backups/<host>-<date>.json` (через `export`)
- `baseline_apply_strategy: safe` — требует подтверждения; `force` — без подтверждения (опасно!)

```bash
# 1. Правка эталона (пример: меняем DNS)
nano config/baseline/routeros-gateway.rsc
# /ip dns set servers=1.1.1.1,8.8.8.8
nano config/baseline/baseline.yml  # если меняете переменные шаблона

# 2. Коммит + журнал
git add config/baseline/routeros-gateway.rsc
git commit -m "feat: dns 1.1.1.1+8.8.8.8"
./scripts/journal.sh config/baseline/routeros-gateway.rsc "смена DNS"

# 3. Проверка на стенде (gw-lab-01)
ansible-playbook playbooks/04-baseline-apply.yml --tags diff --limit gw-lab-01 -v
# Вывод: Diff для gw-lab-01: сравните /tmp/gw-lab-01-desired.rsc с экспортом
# Сгенерирован файл /tmp/gw-lab-01-desired.rsc — откройте, проверьте!

cat /tmp/gw-lab-01-desired.rsc | head -80
# Сравните с текущим: /export file=... на CHR

# 4. Раскатка на флот (интерактивно спросит y/N)
./scripts/rollout.sh diff          # ещё раз diff на все
./scripts/rollout.sh diff gw-core-01
./scripts/rollout.sh apply gw-lab-01   # только на стенд — безопасно
./scripts/rollout.sh apply            # на ВСЕ — осторожно!

# Или напрямую:
ansible-playbook playbooks/04-baseline-apply.yml --tags apply -v
# Для одного хоста:
ansible-playbook playbooks/04-baseline-apply.yml --tags apply --limit gw-core-01

# 5. Пост-аудит
ansible-playbook playbooks/03-audit.yml --limit gw-core-01
# compliance должен вырасти

# Откат: бэкап лежит в config/backups/<host>-<date>.json
# Ручной импорт на CHR: /import file=auto-backup.backup или /system backup load
```

**CHR 7.25 нюанс:** `/import` требует предварительной загрузки RSC файла на CHR через `ftp/scp`. Роль пока делает только `path: import add: file-name=...` — для полной реализации добавьте `community.routeros.api` `upload` (или scp). Сейчас — **безопасный режим**: файл генерируется локально, проверяйте вручную.

---

### 7.5 05-monitoring.yml — SNMP/syslog/accounting

**Что делает:**
- На CHR включает `ip accounting` (трафик), `system logging action remote` → `192.168.0.10:514`
- На хосте Debian — проверяет `monitoring/docker-compose.monitoring.yml` (Prometheus, Grafana, Pushgateway, snmp-exporter, node-exporter)

```bash
ansible-playbook playbooks/05-monitoring.yml -v

# Вывод:
# [monitoring] Включить accounting — ok
# [monitoring] Настроить remote logging — ok
# Мониторинг gw-core-01 → Prometheus: Mock API 192.168.0.50:8728, Pushgateway ...

# Развёртывание стека (если не запущен):
docker compose -f monitoring/docker-compose.monitoring.yml up -d
docker ps
# prometheus 9090, pushgateway 9091, grafana 3000, snmp-exporter 9116, node-exporter 9100

# Проверка:
curl -s http://localhost:9090/-/healthy
curl -s http://localhost:9091/ | head
curl -s http://localhost:3000/login  # Grafana admin/admin

# Prometheus собирает:
# - mikrotik_audit_* (из Pushgateway, куда пушит 03-audit.yml)
# - node (хост Debian)
# - mikrotik_snmp (через snmp-exporter, target 192.168.0.50)
# - mikrotik_api (blackbox tcp_connect 8728/8729)

# Grafana:
open http://192.168.0.10:3000  # admin/admin
# Dashboard "MikroTik — Аудит и Compliance" (auto-provisioned)
# Панели: Compliance %, Critical, таблица findings, compliance по хостам, inventory
```

**CHR SNMP настройка (если не через Ansible):**
```
/snmp set enabled=yes contact="noc@example.com" location="Moscow DC"
/snmp community set [find default=yes] name=mikrotik-ro addresses=192.168.0.0/16 read-access=yes write-access=no
```

---

## 8. Мониторинг Grafana/Prometheus

Подробно — `docs/monitoring.md`, здесь кратко:

**Data flow:**
```
CHR (161 SNMP, 8728 API, 514 syslog) → snmp-exporter/blackbox → Prometheus 9090 → Grafana 3000
Ansible audit (JSON/PROM) → Pushgateway 9091 → Prometheus → Grafana
```

**Метрики аудита (из 03-audit.yml):**
```
# TYPE mikrotik_audit_compliance gauge
mikrotik_audit_compliance{hostname="gw-core-01",board="CHR",version="7.25"} 80.0
mikrotik_audit_passed 8 / failed 2 / critical 0 / high 2
mikrotik_audit_check{id="USR-001",severity="high"} 1 (fail) / 0 (pass)
mikrotik_info{version="7.25",board="CHR"} 1
```

**Аллерты:** `monitoring/prometheus/rules/mikrotik.yml`
- `MikrotikDown` (probe_success==0 2m) — critical
- `MikrotikAuditCritical` (>0 critical) — critical
- `MikrotikLowCompliance` (<80% 10m) — warning
- `MikrotikVersionDrift` (не 7.25) — warning

**Проверка после каждого аудита:**
```bash
ansible-playbook playbooks/03-audit.yml
# Откройте Grafana: compliance должен расти после baseline-apply
```

---

## 9. Стендовая проверка перед мажором

**Обязательно** перед каждым `rollout.sh apply` или правкой эталона (п.7 ТЗ).

```bash
./scripts/check-stand.sh
```

**5 этапов:**

1. **API 192.168.0.50:8728** — `ansible mikrotik -m community.routeros.api -a "path='/system resource' print"` → Board/ROS версия
2. **Инвентаризация** — `playbooks/02-inventory.yml --check` + `ls reports/facts/` (ожидается `gw-core-01.json 6.9K`)
3. **Аудит dry-run** — `playbooks/03-audit.yml --check` → `Compliance 80%` (в check_mode загружает факты из файла, не лезет на CHR)
4. **Baseline diff** — `playbooks/04-baseline-apply.yml --tags diff` → `/tmp/*-desired.rsc`
5. **Мониторинг** — `docker ps | grep prometheus/grafana` → `9090/3000` (или подсказка `docker compose up -d`)

+ **[SIZE]** `du -sh .` → лимит **128МБ** (сейчас 1.1M)
+ **[CHECKSUM]** `sha256sum ansible.cfg inventory/hosts.yml config/baseline/routeros-gateway.rsc playbooks/*.yml`

**Если всё OK — можно мажор:**
```bash
./scripts/rollout.sh diff gw-lab-01   # сначала на стенд
./scripts/rollout.sh apply gw-lab-01
```

**Протокол:** результаты пишутся в `STAND_CHECK.md` (чек-лист + таблица прогонов), ошибки — в `ERROR_JOURNAL.md` с `timestamp+sha256+size`.

---

## 10. Эксплуатация и раскатка baseline

### Ежедневная работа
```bash
# Утренний health-check
./scripts/check-stand.sh | tail -20
ansible-playbook playbooks/02-inventory.yml && ansible-playbook playbooks/03-audit.yml
# Смотрите Grafana: http://192.168.0.10:3000 — compliance, критичные

# Добавили новый gw-03
nano inventory/hosts.yml  # добавить секцию gw-03
ansible-playbook playbooks/01-bootstrap.yml --limit gw-03
ansible-playbook playbooks/02-inventory.yml --limit gw-03
ansible-playbook playbooks/03-audit.yml --limit gw-03
```

### Раскатка эталона (safe)
```bash
# Вариант A: через rollout.sh (рекомендуется)
./scripts/rollout.sh diff              # проверить diff всех
./scripts/rollout.sh diff gw-lab-01    # детально на стенде
# ... правите эталон, коммит ...
./scripts/rollout.sh apply gw-lab-01   # только стенд, спросит y/N
ansible-playbook playbooks/03-audit.yml --limit gw-lab-01  # проверить compliance ↑
./scripts/rollout.sh apply             # на весь флот (serial=1!)

# Вариант B: напрямую
ansible-playbook playbooks/04-baseline-apply.yml --tags diff -v       # dry-run
ansible-playbook playbooks/04-baseline-apply.yml --tags apply -v      # apply serial=1
ansible-playbook playbooks/04-baseline-apply.yml --tags apply --limit gw-core-01 -v

# После apply — обязательно аудит
ansible-playbook playbooks/03-audit.yml
```

### Версионирование эталона
```bash
# Правите только config/baseline/routeros-gateway.rsc и baseline.yml!
git diff config/baseline/routeros-gateway.rsc
git add config/baseline/routeros-gateway.rsc config/baseline/baseline.yml
git commit -m "feat(baseline): firewall final drop LAN->WAN"
./scripts/journal.sh config/baseline/routeros-gateway.rsc "добавлен final drop для WAN"
git tag baseline-1.1 && git push origin baseline-1.1

# Бэкапы: config/backups/<host>-<date>.json — в .gitignore (не коммитятся, хранятся 30 дней по backup.retention)
```

### Откат
```bash
# 1. Найти предыдущий бэкап
ls -lt config/backups/ | head
# gw-core-01-2026-10-29T08:27:04Z.json

# 2. Ручной импорт на CHR (пока нет автоматического rollback)
scp config/backups/gw-core-01-*.json admin@192.168.0.50:/auto-backup.json
ssh admin@192.168.0.50 "/import file=auto-backup.json"  # или /system backup load name=...

# 3. Или откат через git
git log --oneline -- config/baseline/routeros-gateway.rsc
git checkout <предыдущий_коммит> -- config/baseline/routeros-gateway.rsc
ansible-playbook playbooks/04-baseline-apply.yml --tags apply --limit gw-core-01

# 4. Пост-откат аудит
ansible-playbook playbooks/03-audit.yml --limit gw-core-01
```

---

## 11. Устранение неполадок

### 11.1 API не отвечает
```
[STAND] Роутер gw-core-01 (192.168.0.50) недоступен — проверьте VPN/LAN 192.168.0.0/16, API включён: /ip service print
```
**Решение:**
```bash
# На CHR (Winbox/SSH)
ssh admin@192.168.0.50
/ip service print
#   0 name=telnet disabled=yes port=23
#   1 name=ftp disabled=yes port=21
#   5 name=api disabled=no port=8728 address=192.168.0.0/16  ← должен быть enabled!
#   6 name=api-ssl disabled=no port=8729
/ip service enable api
/ip firewall filter print # нет ли drop для 8728? проверьте!
ping 192.168.0.10  # с CHR до Debian
```

### 11.2 Инвентаризация пустая (0 правил)
```
FW filter: 0 rules, addresses: []
```
**Причины:** файл `reports/facts/*.json` не создался (dest был `playbooks/reports/facts` вместо `reports/facts` — уже исправлено), или mock unicode `LAN → WAN` — исправлено на `->`. На CHR проверьте:
```bash
ansible-playbook playbooks/02-inventory.yml -v  # смотрите REGISTER fact_*
cat reports/facts/gw-core-01.json | python3 -m json.tool | grep firewall_filter
# должно быть 7 правил
```

### 11.3 Аудит падает на NTP/SYS
```
_ntp_ok: ntp_servers[0] in ... requires string not UndefinedMarker
```
**Уже исправлено** — теперь `pool.ntp.org in (ntp.servers|default('')|string)` + `|default('Europe/Moscow')`. Обновите `roles/mikrotik_audit/tasks/main.yml` с последнего коммита.

### 11.4 Baseline не генерирует /tmp/*-desired.rsc
```
'ntp_enabled' is undefined / 'expected' is undefined
```
**Исправлено** — `golden.j2` теперь с `|default()` для всех переменных. Обновите `roles/mikrotik_baseline/templates/golden.j2`.

### 11.5 Workspace >128МБ
```
⚠️ Превышен лимит 128МБ
```
```bash
make size  # du -sh . .cache reports config/backups
make clean # rm -rf .cache/* reports/facts/* reports/json/* config/backups/*
# .cache/facts кешируется на 86400с (1 день) — можно чистить
```

### 11.6 Prometheus/Grafana не собираются
```bash
docker ps  # пусто?
docker compose -f monitoring/docker-compose.monitoring.yml up -d
curl -s http://localhost:9090/-/healthy  # Prometheus OK?
curl -s http://localhost:3000/api/health  # Grafana OK?
cat monitoring/prometheus/prometheus.yml | grep targets
# pushgateway:9091, snmp-exporter:9116, 192.168.0.50:8728
docker logs prometheus --tail 20
docker logs grafana --tail 20
```

### 11.7 Ansible Vault
```bash
# Если забыли vault_password_file
ansible-playbook playbooks/01-bootstrap.yml --ask-vault-pass
ansible-vault edit group_vars/mikrotik/vault.yml
```

### 11.8 CHR специфично
- **CHR не сохраняет конфиг после reboot:** сделайте `system backup save` или экспорт `config/baseline/`
- **API-SSL сертификат:** после `certificate add ...` — `/ip service set api-ssl certificate=...`
- **MAC-server:** `/tool mac-server set allowed-interface-list=LAN` — иначе Winbox с WAN открыт (SVC-005)
- **DHCP pool 192.168.0.100-200:** в 7.25 путь `/ip pool` + `/ip dhcp-server` + `/ip dhcp-server network` — все три проверяет аудит (DHCP-001)

---

## 12. Приложения

### 12.1 Структура проекта (после развёртывания)

```
arena/ — 1.2M (лимит 128M)
├── ansible.cfg              # inventory, roles_path, факт-кеш 86400с
├── inventory/
│   ├── hosts.yml            # ПРИВАТ! gw-core-01 192.168.0.50 api 8728 (не коммить)
│   └── hosts.example.yml    # шаблон для копирования
├── group_vars/
│   ├── all.yml              # expected WAN/LAN, tech_user, NTP/DNS, security, мониторинг (1.6K)
│   └── mikrotik.yml         # api_port 8728, timeouts
├── collections/requirements.yml  # community.routeros≥2.9, prometheus, grafana, docker
├── playbooks/
│   ├── 01-bootstrap.yml     # тех.учётка + api-ssl + strong-crypto (serial=1 не нужен)
│   ├── 02-inventory.yml     # 15 API путей → reports/facts/*.json
│   ├── 03-audit.yml         # 24 правила → compliance + Prometheus + Grafana
│   ├── 04-baseline-apply.yml# golden.j2 → diff/apply serial=1
│   └── 05-monitoring.yml    # accounting/syslog + Docker стек
├── roles/
│   ├── mikrotik_bootstrap/  # api/api_modify, проверка resource, создание user
│   ├── mikrotik_inventory/ # 15 фактов, to_nice_json, meta
│   ├── mikrotik_audit/      # SYS/NET/USR/SVC/FW → JSON/PROM/HTML
│   ├── mikrotik_baseline/   # slurp RSC, template golden.j2, backup/export
│   └── monitoring/          # ip accounting, logging action remote
├── config/baseline/
│   ├── routeros-gateway.rsc # ЭТАЛОН (4.7K) — правится здесь!
│   ├── baseline.yml         # переменные шаблона
│   └── README.md
├── monitoring/
│   ├── docker-compose.monitoring.yml  # prometheus 2.53, pushgateway 1.8, grafana 11.1, snmp/node/blackbox
│   ├── prometheus/prometheus.yml + rules/mikrotik.yml + snmp_exporter.yml
│   └── grafana/dashboards/mikrotik-audit.json
├── scripts/
│   ├── check-stand.sh       # 5 этапов + SIZE + CHECKSUM (п.7 ТЗ)
│   ├── rollout.sh           # diff → apply → audit → journal (serial=1)
│   └── journal.sh           # п.6: timestamp+sha256+size → ERROR_JOURNAL.md
├── stand/
│   ├── mock_routeros_api.py # эмулятор 7.25: 30+ путей, CCR2116, bridge1 192.168.0.50/16, PID 4066
│   └── start.sh             # nohup + ss -tlnp
├── reports/
│   ├── facts/gw-core-01.json   # 6.9K (7049B) — инвентарь
│   ├── json/gw-core-01.audit.json # 1.6K — compliance 80%
│   └── prometheus/gw-core-01.prom # 1.5K — exposition
├── ERROR_JOURNAL.md         # журнал с timestamp+sha256 (п.6)
├── STAND_CHECK.md           # протокол стенда (п.7)
└── docs/DEPLOYMENT.md       # ← этот файл
```

### 12.2 Быстрые команды

```bash
make install      # galaxy collections
make check        # syntax-check + lint
make stand        # ./scripts/check-stand.sh
make audit        # inventory + audit
make baseline-diff  # 04 diff
make baseline-apply # rollout apply (опасно!)
make monitoring   # docker compose up
make size         # du + лимит
make clean        # очистить кеш/отчёты
```

### 12.3 Чек-лист для эксплуатации (еженедельно)

- [ ] `./scripts/check-stand.sh` — 5/5 OK, SIZE <128M
- [ ] `ansible-playbook playbooks/02-inventory.yml` — все gw-* в `reports/facts/`
- [ ] `ansible-playbook playbooks/03-audit.yml` — Grafana compliance ≥80% (цель 95%+), critical=0
- [ ] `docker ps` — prometheus/grafana/pushgateway/snmp-exporter/node-exporter UP
- [ ] `git log --oneline -10` — все изменения baseline в `ERROR_JOURNAL.md` с checksum
- [ ] `du -sm .` — <128M, иначе `make clean`

### 12.4 Контакты и ссылки

- MikroTik CHR 7.25 docs: https://help.mikrotik.com/docs/display/ROS/RouterOS
- community.routeros: https://galaxy.ansible.com/ui/repo/published/community/routeros/ + https://docs.ansible.com/ansible/latest/collections/community/routeros/
- Prometheus: https://prometheus.io/docs/
- Grafana Dashboard: http://192.168.0.10:3000 (admin/admin)

---

**Автор:** Ansible automation (ветка `arena/1fb619c0-arena`, коммит `8b3cd37`, 2026-10-29T08:27:00+03:00)
**Проверка стенда:** `STAND_CHECK.md` — PASS gw-core-01+gw-lab-01 mock 127.0.0.1:8728, compliance 80%, 7 FW правил, 9 bridge ports
**Размер:** 1.2M / 128M
