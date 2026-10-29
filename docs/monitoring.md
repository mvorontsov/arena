# Мониторинг → Grafana (п.9-10 ТЗ)

## Поток данных
```
MikroTik (192.168.0.50) —SNMP(161)/API(8729)→ snmp_exporter/pushgateway → Prometheus (9090) → Grafana (3000)
                             └─ syslog(514) → Loki → Grafana
Ansible audit → pushgateway (9091) → mikrotik_audit_* метрики → Grafana dashboard
```

## Что собирается в Prometheus
- `mikrotik_audit_compliance` — % compliance (0-100)
- `mikrotik_audit_check{id,severity} == 1` — конкретное несоответствие
- `mikrotik_audit_critical/high/medium/low` — счётчики
- `mikrotik_info{version,board}` — инвентарь
- `mikrotik_cpu_load`, `probe_success` (blackbox) — инфраструктура
- SNMP: интерфейсы, трафик, CPU, память (через mikrotik MIB)

## Развёртывание на Debian 13 (хост 192.168.0.10)
```bash
cd monitoring
docker compose -f docker-compose.monitoring.yml up -d
# Prometheus: http://192.168.0.10:9090
# Grafana:    http://192.168.0.10:3000 (admin/admin) — дашборд "MikroTik — Аудит и Compliance"
# Pushgateway:http://192.168.0.10:9091
```

## Grafana дашборд
- `monitoring/grafana/dashboards/mikrotik-audit.json` — автопровизнинг
- Панели: Compliance stat, Critical alert, Таблица findings, Compliance по хостам, Инвентарь
- Темплейт `hostname` — фильтр по роутеру
- Ссылки на Ansible отчёты `http://192.168.0.10/reports/`

## После каждого аудита
```bash
ansible-playbook playbooks/03-audit.yml  # пушит в pushgateway
# Проверьте в Grafana — compliance должен расти после baseline-apply
```

## Аллерты (prometheus/rules/mikrotik.yml)
- MikrotikDown (API не отвечает 2м)
- MikrotikAuditCritical (есть critical несоответствия)
- MikrotikLowCompliance (<80%)
- MikrotikVersionDrift (не 7.25)
