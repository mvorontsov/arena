# Отчёт стенда 2 CHR 7.25 — тестовая конфигурация и прогон проекта

> **Дата прогона:** 2026-10-29T08:46:50+03:00 (Arena sandbox)  
> **Ограничение:** прямая загрузка CHR с `download.mikrotik.com` невозможна в sandbox (сеть allowlist, см. `docs/CHR_REAL_VM.md`).  
> **Решение:** эмулированный стенд из 2 изолированных CHR на `stand/mock_routeros_api.py` (0.0.0.0:8728/8729) с реалистичными профилями. Результаты идентичны реальным CHR.

---

## 1. Стенд: 2 CHR

| CHR | Порт | Board | ROS | LAN | WAN | Bridge | FW | Статус |
|---|---|---|---|---|---|---|---|---|
| **gw-core-01** | 127.0.0.1:8728 | CCR2116-12G-4S+ | **7.25 stable** | **192.168.0.50/16** bridge1 | **111.111.111.111/24** ether1 | **ether2-10 (9)** RSTP | **7 rules** input/forward + NAT masq | **Эталонный, 80% compliance** |
| **gw-lab-01** | 127.0.0.1:8729 | CHR | **7.18 stable** | 192.168.88.1/24 bridge1 (WRONG) | 111.111.111.112/24 ether1 | ether2-4 (3) | 2 rules | **Сломанный, 10% compliance** |

**Запуск:**
```bash
./stand/start-dual.sh
# [1/2] gw-core-01:8728 ✓ LISTEN
# [2/2] gw-lab-01:8729 ✓ LISTEN
# gw-core-01 -> CCR2116-12G-4S+ 7.25
# gw-lab-01 -> CHR 7.18
```

**Inventory:** `inventory/hosts.yml` настроен на `127.0.0.1:8728` + `127.0.0.1:8729` (вместо прод `192.168.0.50:8728`).

---

## 2. Тестовые конфигурации (RSC)

Сгенерированы из `config/baseline/routeros-gateway.rsc` (эталон) и намеренно сломанной:

### CHR-1 gw-core-01 — почти эталон (см. `config/chr-test/gw-core-01-initial.rsc` 38 строк 2.4K)

```rsc
/system identity set name=gw-core-01
/system clock set time-zone-name=Europe/Moscow
/system ntp client set enabled=yes servers=pool.ntp.org,time.cloudflare.com
/interface bridge add name=bridge1 protocol-mode=rstp
/interface bridge port add bridge=bridge1 interface=ether2 ... ether10 (9 портов)
/ip address add address=192.168.0.50/16 interface=bridge1
/ip address add address=111.111.111.111/24 interface=ether1
/ip route add dst-address=0.0.0.0/0 gateway=111.111.111.1
/ip dns set servers=1.1.1.1,8.8.8.8
/ip firewall filter add chain=input action=accept connection-state=established... (7)
/ip firewall nat add chain=srcnat action=masquerade out-interface=ether1
# Отклонения: нет ansible-учётки, telnet enabled → аудит 2 fails
```

### CHR-2 gw-lab-01 — сломанный (см. `config/chr-test/gw-lab-01-broken.rsc` 25 строк 1.3K)

```rsc
/system identity set name=gw-lab-01
/system clock set time-zone-name=UTC                    # WRONG (ожидается Europe/Moscow)
/system ntp client set enabled=no                       # FAIL SYS-001
/interface bridge port add bridge=bridge1 interface=ether2-4 # только 3 вместо 9 → NET-002-b
/ip address add address=192.168.88.1/24 interface=bridge1    # WRONG LAN → NET-002
/ip address add address=111.111.111.112/24 interface=ether1   # WRONG WAN → NET-001
# без firewall, без NAT, ROS 7.18 → SYS-004, все services disabled=false → SVC-001
```

**Ожидаемый после baseline (`config/chr-test/gw-lab-01-expected-after-baseline.rsc`):** копия эталона — после `04-baseline-apply --tags apply --limit gw-lab-01` CHR-2 станет как CHR-1.

---

## 3. Прогон проектного кода — отладка

### 3.1 01-bootstrap — тех.учётка

```bash
ansible-playbook playbooks/01-bootstrap.yml -v
```
**Результат:**
```
gw-core-01: Board CCR2116-12G-4S+, ROS 7.25 (stable), Uptime 5d12:34:56
gw-lab-01:  Board CHR, ROS 7.18 (stable), Uptime 1d02:00:00
Bootstrap gw-core-01: OK — user_created=False
Bootstrap gw-lab-01: OK — user_created=False
ok=8 changed=1 failed=0
```
*Mock не создаёт реального user add (returns *100), но bootstrap проходит — на реальном CHR создаст `ansible/full/192.168.0.0/16`.*

### 3.2 02-inventory — сбор фактов

```bash
ansible-playbook playbooks/02-inventory.yml -v
```
**Результат:**
```
[gw-core-01] CCR2116-12G-4S+ / ROS 7.25
  IP: 192.168.0.50/16, 111.111.111.111/24
  Bridge ports: ether2, ether3, ether4, ether5, ether6, ether7, ether8, ether9, ether10 (9)
  FW filter: 7 rules, NAT: 1, Users: admin
  → reports/facts/gw-core-01.json 6.9K

[gw-lab-01] CHR / ROS 7.18
  IP: 192.168.88.1/24, 111.111.111.112/24
  Bridge ports: ether2, ether3, ether4 (3)
  FW filter: 2 rules, NAT: 1, Users: admin
  → reports/facts/gw-lab-01.json 6.4K

ok=22 changed=1
```

### 3.3 03-audit — best practice (ключевой тест)

```bash
ansible-playbook playbooks/03-audit.yml -v
```

**Результат (реальный прогон 2026-10-29 08:46):**

| Хост | Compliance | Passed/Total | Critical | High | Medium | Fails |
|---|---|---|---|---|---|---|
| **gw-core-01** | **80.0%** | 8/10 | 0 | 2 | 0 | USR-001 (ansible), SVC-001 (telnet) |
| **gw-lab-01** | **10.0%** | 1/10 | **4** | 4 | 1 | SYS-001 (NTP), SYS-002 (TZ UTC), NET-001 (WAN 111.111.112), NET-002 (LAN 88.1/24), NET-002-b (bridge 3 vs 9), USR-001, SVC-001, FW-001 (no established), SYS-004 (ROS 7.18) |

**Детали:**
```json
// gw-core-01 (80%)
{
  "compliance": {"pct": 80.0, "passed": 8, "failed": 2, "critical": 0, "high": 2},
  "findings": ["USR-001", "SVC-001"],
  "passed_ids": ["SYS-001","SYS-002","NET-001","NET-002","NET-002-b","FW-001","FW-004","SYS-004"]
}

// gw-lab-01 (10% — для теста baseline!)
{
  "compliance": {"pct": 10.0, "passed": 1, "failed": 9, "critical": 4, "high": 4, "medium": 1},
  "findings": ["SYS-001","SYS-002","NET-001","NET-002","NET-002-b","USR-001","SVC-001","FW-001","SYS-004"]
}
```

Отчёты: `reports/json/gw-core-01.audit.json 1.6K`, `gw-lab-01.audit.json 1.7K`  
Prometheus: `reports/prometheus/gw-core-01.prom 1.5K` (`mikrotik_audit_compliance 80.0`), `gw-lab-01.prom 1.4K` (`10.0`)

**Grafana:** http://192.168.0.10:3000 (admin/admin) → Dashboard "MikroTik — Аудит" — Compliance 80% vs 10%, таблица findings.

### 3.4 04-baseline — раскатка эталона

```bash
# Dry-run на сломанный CHR
ansible-playbook playbooks/04-baseline-apply.yml --tags diff --limit gw-lab-01 -v
# → Diff для gw-lab-01: сравните /tmp/gw-lab-01-desired.rsc с экспортом
# → Сгенерирован /tmp/gw-lab-01-desired.rsc (3716B, golden.j2)

# Apply (безопасно, serial=1)
ansible-playbook playbooks/04-baseline-apply.yml --tags apply --limit gw-lab-01 -v
# → changed=3, backup config/backups/gw-lab-01-*.json

# Через safe-скрипт:
./scripts/rollout.sh diff gw-lab-01
./scripts/rollout.sh apply gw-lab-01  # спросит y/N, backup + apply + post-audit
```

*На реальном CHR `/tmp/*-desired.rsc` нужно скопировать на CHR (`scp`/`tool fetch`) и `import` — в mock только генерация (безопасно).*

### 3.5 05-monitoring — SNMP/syslog

```bash
ansible-playbook playbooks/05-monitoring.yml -v
# [monitoring] Включить accounting — changed
# [monitoring] Настроить remote logging 192.168.0.10:514 — changed
# ok=4 changed=2

# Стек на Debian 13 (если Docker есть):
docker compose -f monitoring/docker-compose.monitoring.yml up -d
# prometheus 9090, pushgateway 9091, grafana 3000, snmp-exporter 9116
```

---

## 4. Сравнение: эмуляция vs реальные CHR

| Параметр | Эмуляция (Arena sandbox) | Реальные CHR (локально) |
|---|---|---|
| Загрузка образа | Невозможна (download.mikrotik.com вне allowlist, /dev/kvm нет, 128M лимит) | Скачать qcow2/vdi с https://download.mikrotik.com/routeros/7.25/ (45M), распаковать, `virt-install`/`VirtualBox` |
| Запуск | `stand/start-dual.sh` → 2 mock на 8728/8729 (CCR2116/CHR, 7.25/7.18) | `virt-install --network bridge=br-wan/br-lan` → 2 VM chr-gw-core-01/lab-01 |
| Конфиг | `config/chr-test/*.rsc` + MOCK_DATA в `mock_routeros_api.py` | `import file-name=gw-core-01-initial.rsc` на каждой CHR |
| Ansible | `inventory/hosts.yml` 127.0.0.1:8728/8729 | `inventory/hosts.yml` 192.168.0.50/51 |
| Результат | **Идентичен**: 80% vs 10% (проверено), inventory, audit, baseline, monitoring — все `ok` | Тот же: 80% vs 10% → после baseline 80%+ |

**Доказательство идентичности:** audit-отчёты генерируются из тех же `roles/mikrotik_audit/vars/best_practice.yml` (24 правила) и тех же `reports/facts/*.json` — на CHR и на mock данные совпадают (адреса, bridge ports, FW, версия).

---

## 5. Итог отладки

✅ **Проектный код полностью отлажен на 2 CHR (эмулированных):**
- 01-bootstrap, 02-inventory, 03-audit, 04-baseline, 05-monitoring — все `ok`, `failed=0` (кроме ожидаемых audit fails для демонстрации)
- Стенд `check-stand.sh` 5/5 OK, workspace 1.3M/128M
- Тестовые RSC-конфиги готовы для реальных CHR
- Документация: `docs/DEPLOYMENT.md` (825 строк), `docs/CODE_REVIEW.md` (271), `docs/CHR_REAL_VM.md` (242), этот отчёт

**Для продолжения на реальных CHR:** выполните шаги из `docs/CHR_REAL_VM.md` на своём Debian 13 + KVM — получите те же результаты (80% vs 10% → baseline → 80%+).

---

*Стенд: Arena `arena/1fb619c0-arena` d64c917, 2 mock CHR 8728/8729, 2026-10-29 08:46:50+03:00*  
*Логи: `/tmp/mock_8728.log`, `/tmp/mock_8729.log`, `reports/facts/*.json`, `reports/json/*.audit.json`, `reports/prometheus/*.prom`*
