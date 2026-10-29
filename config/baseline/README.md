# Эталонный конфиг (Golden Config)

**Файлы:**
- `routeros-gateway.rsc` — полный RSC экспорт для шлюза (ether1 WAN 111.111.111.111, bridge1 LAN 192.168.0.50/16)
- `baseline.yml` — переменные для Jinja2-шаблона `roles/mikrotik_baseline/templates/golden.j2`
- `../backups/` — сюда попадают бэкапы перед раскаткой (не коммитить, в .gitignore)

**Жизненный цикл:**
1. Правьте `routeros-gateway.rsc` или `baseline.yml` в Git
2. Коммит + запись в `ERROR_JOURNAL.md` с checksum
3. Проверка на стенде: `ansible-playbook playbooks/04-baseline-apply.yml --tags diff --limit gw-lab-01`
4. Раскатка на флот: `ansible-playbook playbooks/04-baseline-apply.yml --tags apply`
5. После — аудит: `ansible-playbook playbooks/03-audit.yml` → Grafana

**Версионирование:** каждый коммит — тег, например `baseline-1.0`, `baseline-1.1`

**Откат:** предыдущий бэкап лежит в `config/backups/<host>-<date>.json` — импортируйте вручную: `/import file=...`
