# Архитектура rosctl

## Обзор
```
┌─────────────┐   REST API (8728/8729)   ┌─────────────────┐
│  Inventory │ ─────────────────────────► │  MikroTik fleet │
│ inventory.yml                         │  CCR / hAP / CRS │
└──────┬──────┘                         └─────────────────┘
       │ CLI (Typer + Rich)
       ▼
┌──────────────┐  Jinja2 RSC  ┌──────────┐  FastAPI  ┌──────────┐
│ Orchestrator ├─────────────►│ Templates│◄─────────►│ Web API  │
│ executor.py  │  playbooks   └──────────┘            └────┬─────┘
└──────┬───────┘                                           │
       │                                                   ▼
       │  backups/monitoring/audit               ┌─────────────────┐
       └────────────────────────────────────────►│ React Dashboard │
                                                │ (single HTML)   │
                                                └─────────────────┘
```

## Модули
- **config.py** — Pydantic-модели Inventory, AppConfig (env ROS_*)
- **inventory/manager.py** — загрузка YAML, фильтры (group/tag/glob/limit), Rich-таблицы
- **client/** — `RouterOSRestClient` (REST → CLI маппинг) + `RouterOSSSHClient` (paramiko), единый интерфейс `exec()`
- **orchestrator/** — `Playbook` (YAML → Pydantic), `Orchestrator` (async semaphore, стратегии parallel/sequential/rolling, dry-run/diff)
- **backup/** — экспорт → `backups/<host>/ts.rsc` + `.json` мета, ротация
- **monitoring/** — сбор `/system/resource`, синтетические метрики в demo, алерты
- **cli.py** — Typer-команды (inventory, exec, play, template, backup, monitor, wireguard, firewall, capsman, serve)
- **web/app.py** — FastAPI: /api/* + одностраничный дашборд (Tailwind CDN, live polling)

## Стратегии деплоя
- **CLI-only**: pip install, inventory.yml в репо, запуск из CI
- **CLI + Web**: `rosctl serve` поднимает API+дашборд
- **Docker**: один образ python:3.11-slim + tini, volume для inventory/backups

## Demo vs Live
`ROS_DEMO=1` (default) — все хосты 10.*/192.168.* возвращают synthetic-ответы без сети. `ROS_DEMO=0` — реальные HTTP-запросы к RouterOS REST. Переключение на лету.

## Расширения
- Добавить `ros_orchestrator/scheduler.py` (APScheduler cron → playbook)
- Подключить PostgreSQL вместо файлов для истории jobs
- Добавить Telegram/Slack webhook в monitoring
- Интеграция с NetBox как источник inventory
