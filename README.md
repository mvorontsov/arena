# rosctl — Оркестратор для MikroTik RouterOS

<p align="center">
  <b>Ansible-подобный CLI + Web-дашборд для флота RouterOS</b><br>
  <i>инвентарь • плейбуки • Jinja2-шаблоны • массовый rollout • diff/rollback • бэкапы • мониторинг • CAPsMAN/WireGuard/VLAN</i>
</p>

<p align="center">
  <code>rosctl</code> — один бинарник для управления сотнями MikroTik: от hAP ax³ до CCR2116.<br>
  Работает через <b>REST API</b> и <b>SSH</b>, поддерживает <b>demo-режим</b> без живых роутеров.
</p>

---

## ⚡ Быстрый старт (30 секунд)

```bash
pip install -e .                    # или: pip install ros-orchestrator
rosctl init                         # создаёт inventory.yml + примеры
rosctl inventory list               # посмотреть флот
rosctl exec "/system/resource/print" -g edge   # выполнить на группе
rosctl play playbooks/example.yml --dry-run --diff  # плейбук с diff
rosctl serve                        # веб-дашборд + API на :8000
```

Откройте **http://localhost:8000** — инвентарь, мониторинг, exec, плейбуки, бэкапы, топология.

> **Demo-режим** включён по умолчанию: все хосты `10.*`/`192.168.*` возвращают синтетические ответы, чтобы вы могли оценить оркестрацию без реальных роутеров. Для живой работы: `ROS_DEMO=0 rosctl exec "/system/resource/print" -g edge`.

---

## 🧭 Возможности

| Модуль | Что умеет |
|---|---|
| **Inventory** | YAML-инвентарь с группами, тегами, vars, `defaults`, glob-фильтры `—limit "gw-*,branch-*"` |
| **Orchestrator** | Параллельный/последовательный/rolling rollout, `--parallel 20`, `--dry-run`, `--diff`, теги |
| **Плейбуки** | YAML как в Ansible: `plays → hosts → tasks (command/template)`, `vars`, `when`, `loop`, `tags` |
| **Шаблоны** | Jinja2 → RSC (`templates/*.rsc.j2`), контекст `inventory_hostname, host, group, vars, item` |
| **Бэкапы** | `export` → `backups/<host>/YYYYMMDD-HHMMSS.rsc` + `.json` мета, `list/diff/prune` |
| **Мониторинг** | `resource`, CPU/MEM/Uptime, `stats --watch`, `top`, алерты (CPU>70, offline, low-mem) |
| **Сетевые пресеты** | `wireguard status/genkey`, `firewall list`, `capsman status`, `audit` (дефолтные пароли, SSL, обновления) |
| **Web/API** | FastAPI + одностраничный дашборд: инвентарь, exec, плейбуки, мониторинг-live, бэкапы, топология, audit |

---

## 📦 Установка

### Локально
```bash
git clone https://github.com/mvorontsov/arena && cd arena
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
rosctl --help
```

### Docker
```bash
docker compose up -d
# API: http://localhost:8000  Docs: http://localhost:8000/docs
```
`docker-compose.yml` уже в репозитории — бэкенд + фронтенд (один образ).

### Переменные окружения
```bash
ROS_INVENTORY_PATH=./inventory.yml
ROS_BACKUPS_DIR=./backups
ROS_TEMPLATES_DIR=./templates
ROS_DEMO=1              # 1=демо (без роутеров), 0=реальные запросы
ROS_DEFAULT_PARALLEL=20
```

---

## 📋 Inventory

`inventory.yml` — единый источник правды:

```yaml
defaults:
  username: admin
  password: changeme
  api_ssl: false
  timeout: 10

groups:
  edge:
    vars: { dns_primary: 1.1.1.1, ntp: pool.ntp.org }
  branch:
    vars: { capsman: "10.0.0.1" }

hosts:
  - name: gw-msk-01
    host: 10.10.0.1
    group: edge
    tags: [msk, prod]
    comment: GW Москва — CCR2116
    vars: { wg_address: 10.255.0.1/24 }
```

Команды:
```bash
rosctl inventory list                          # таблица
rosctl inventory list -g edge                  # по группе
rosctl inventory list -t prod --json           # по тегу
rosctl inventory list --limit "gw-*,lab-*"     # glob
rosctl inventory show gw-msk-01
rosctl inventory test --parallel 30            # проверка доступности
rosctl inventory add new-host 10.0.0.99 -g lab --tags test
```

---

## 🚀 Exec — массовое выполнение

```bash
rosctl exec "/system/resource/print" --group edge
rosctl exec "/ip/address/print" --tag retail --parallel 30
rosctl exec "/interface/wireguard/print" --limit "gw-msk-*,lab-*" --output json
rosctl exec "/ip dns set servers=1.1.1.1,8.8.8.8" --dry-run   # без применения
```

Вывод — Rich-таблица с `host | status | latency | output`. Поддерживает `table | json | yaml`.

REST-маппинг: `/system/resource/print` → `GET /rest/system/resource`, мутации → `POST /rest/...`.

---

## 📖 Плейбуки

Синтаксис вдохновлён Ansible, адаптирован под RouterOS:

```yaml
name: Базовая настройка
plays:
  - name: Базовая сеть
    hosts: all                 # группа/тег/маска или "all"
    vars: { dns_primary: 1.1.1.1 }
    strategy: parallel         # parallel | sequential | rolling
    parallel: 20
    tasks:
      - name: Установить DNS
        command: /ip dns set servers={{ dns_primary }},8.8.8.8
        tags: [dns]

      - name: WireGuard из шаблона
        template: wireguard.rsc.j2
        vars:
          wg_address: 10.255.0.1/24
          peers:
            - { pubkey: "...", allowed: "10.255.0.0/24", endpoint: "1.2.3.4:13231" }
        tags: [vpn]

      - name: Условно
        command: /ip service disable telnet
        when: "group == 'edge'"    # Jinja2-условие
        tags: [harden]

      - name: Цикл
        command: /interface vlan add name=vlan{{ item }} vlan-id={{ item }}
        loop: [10, 20, 30]
```

Запуск:
```bash
rosctl play playbooks/example.yml --dry-run --diff
rosctl play playbooks/wireguard.yml --limit edge --tags vpn
rosctl play playbooks/vlan.yml -e vlan_id=20,dns_primary=9.9.9.9
rosctl lint playbooks/harden.yml     # валидация
```

Опции: `--limit`, `--tags`/`--skip-tags`, `--extra-vars key=val`, `--parallel`, `--check` (dry-run), `--diff`.

---

## 🧩 Шаблоны Jinja2

`templates/*.rsc.j2` рендерятся с контекстом хоста:

```jinja
# {{ inventory_hostname }} — {{ host }} — {{ group }}
/interface wireguard add name={{ wg_name }} listen-port={{ wg_port }} private-key="{{ wg_private_key }}"
/ip address add address={{ wg_address }} interface={{ wg_name }}
{% for peer in peers %}
/interface wireguard peers add interface={{ wg_name }} public-key="{{ peer.pubkey }}" allowed-address={{ peer.allowed }}
{% endfor %}
```

```bash
rosctl template list
rosctl template render wireguard.rsc.j2 --host gw-msk-01 --var wg_address=10.0.0.1/24 --var wg_port=13231
```

---

## 💾 Бэкапы

```bash
rosctl backup create -g edge                    # export всех edge
rosctl backup list                              # последние
rosctl backup list gw-msk-01
rosctl backup diff gw-msk-01                    # diff с последним
rosctl backup diff gw-msk-01 backups/gw-msk-01/20251029-120000.rsc
rosctl backup prune --keep 30                   # ротация
```

Хранение: `backups/<hostname>/YYYYMMDD-HHMMSS.rsc` + `.json` (размер, версия, время).

---

## 📊 Мониторинг

```bash
rosctl monitor stats                    # таблица CPU/MEM/Uptime/Board
rosctl monitor stats -g edge --watch    # автообновление 2с
rosctl monitor stats --json             # для интеграции
rosctl monitor top                      # htop-style TUI (live)
```

Web: `/api/monitoring` → алерты (`CPU>85 crit`, `offline`, `low-mem`), графики, история.

---

## 🔐 WireGuard, Firewall, CAPsMAN, Audit

```bash
rosctl wireguard status -g edge
rosctl wireguard genkey                  # генерация keypair

rosctl firewall list --host gw-msk-01
rosctl capsman status

rosctl audit                            # дефолтные пароли, firewall, SSL, обновления
rosctl diff gw-msk-01 --template base.rsc.j2
```

---

## 🌐 Web-дашборд и API

```bash
rosctl serve --port 8000 --host 0.0.0.0
# → http://localhost:8000        дашборд
# → http://localhost:8000/docs   Swagger
# → http://localhost:8000/health
```

API:
```
GET  /api/inventory
GET  /api/monitoring?group=edge
POST /api/exec          {command, group, limit, parallel}
POST /api/backups/create
GET  /api/backups?host=gw-msk-01
POST /api/playbook/run  {playbook, limit, dry_run, diff, extra_vars}
GET  /api/audit
GET  /api/hosts/{name}/export
GET  /api/hosts/{name}/diff
```

Дашборд — один HTML (без сборки): Tailwind CDN, live-обновление 3с, exec-консоль, модалка плейбуков, топология.

---

## 🐳 Docker Compose

```yaml
services:
  rosctl:
    build: .
    ports: ["8000:8000"]
    volumes: ["./inventory.yml:/app/inventory.yml", "./backups:/app/backups", "./templates:/app/templates", "./playbooks:/app/playbooks"]
    environment: [ROS_DEMO=1]
    command: rosctl serve --host 0.0.0.0 --port 8000
```

```bash
docker compose up --build
```

---

## 🧪 Разработка

```bash
pip install -e ".[dev]"
pytest -q
ruff check .
rosctl lint playbooks/example.yml
ROS_DEMO=1 rosctl exec "/system/resource/print" -g lab
```

Структура:
```
arena/
├── ros_orchestrator/
│   ├── cli.py               # Typer CLI (основной интерфейс)
│   ├── config.py            # Pydantic Settings + модели Inventory
│   ├── inventory/manager.py
│   ├── client/ {rest,ssh,base}.py
│   ├── orchestrator/ {executor,tasks}.py
│   ├── backup/manager.py
│   ├── monitoring/collector.py
│   └── web/app.py           # FastAPI + дашборд
├── inventory.yml / inventory.example.yml
├── playbooks/ {example,wireguard,vlan,harden}.yml
├── templates/ {base,wireguard,capsman,dhcp}.rsc.j2
├── backups/
├── tests/
└── docker-compose.yml / Dockerfile
```

---

## 🔌 Подключение к реальным RouterOS

1. Включите REST API: `/ip service enable api` (или `api-ssl`), `/user set admin password=...`
2. Откройте порт: `/ip service set api port=8728` (или 8729 для SSL)
3. Запустите:
   ```bash
   ROS_DEMO=0 rosctl inventory test
   ROS_DEMO=0 rosctl exec "/system/resource/print" -g edge
   ```
4. Для SSH: укажите `key_file` или `password` в inventory, клиент `paramiko` подхватит.

---

## 📝 Лицензия

MIT — используйте свободно. PR и issues приветствуются.

<p align="center"><i>Сделано для сетевых инженеров, которые устали от WinBox на 200 роутеров.</i></p>
