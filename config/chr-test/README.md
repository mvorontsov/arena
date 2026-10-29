# Тестовые конфигурации CHR 7.25 для стенда

Этот каталог содержит RSC-конфиги, которые используются в эмулированном стенде из 2 CHR.

## CHR-1 gw-core-01 — эталонный (80% compliance)

Файл: `gw-core-01-initial.rsc` (38 строк, 2.4K)
- WAN: ether1 111.111.111.111/24 GW 111.111.111.1
- LAN: bridge1 192.168.0.50/16, ether2-10 RSTP
- DNS 1.1.1.1/8.8.8.8, NTP pool.ntp.org, timezone Europe/Moscow, ROS 7.25
- Firewall best practice (input established/forward, NAT masquerade)
- Намеренно отсутствуют: ansible-учётка (USR-001), telnet enabled (SVC-001) → аудит 80% (2 fails)

Mock: `127.0.0.1:8728` board CCR2116 7.25, возвращает 7 filter rules, 9 bridge ports.

## CHR-2 gw-lab-01 — сломанный (10% compliance, для теста baseline)

Файл: `gw-lab-01-broken.rsc` (25 строк, 1.3K)
- WAN: ether1 111.111.111.112/24 (неверный IP, ожидается 111.111.111.111)
- LAN: bridge1 192.168.88.1/24 (неверная сеть, ожидается 192.168.0.50/16)
- Bridge: только ether2-4 вместо ether2-10 (3 вместо 9)
- System: ROS 7.18 (устарел, ожидается 7.25), timezone UTC, NTP disabled
- Firewall: только 2 правила (без established, без NAT)
- Services: все включены (telnet/ftp/www/api)
- Users: только admin, нет ansible

Mock: `127.0.0.1:8729` board CHR 7.18, 2 filter rules, 3 bridge ports, аудит 10% (9 fails: SYS-001/002, NET-001/002/b, USR-001, SVC-001, FW-001, SYS-004)

## Ожидаемый результат после baseline

Файл: `gw-lab-01-expected-after-baseline.rsc` — копия эталона `config/baseline/routeros-gateway.rsc`
- После `ansible-playbook 04-baseline-apply.yml --tags apply --limit gw-lab-01` CHR-2 должен стать идентичен CHR-1
- Повторный аудит: compliance 80% → 95-100% (в идеале)

## Использование на реальных CHR

```bash
# На Windows/Linux скачайте CHR 7.25:
# https://download.mikrotik.com/routeros/7.25/chr-7.25.vmdk.zip (VMware)
# https://download.mikrotik.com/routeros/7.25/chr-7.25.vdi.zip (VirtualBox)
# https://download.mikrotik.com/routeros/7.25/chr-7.25.qcow2.zip (KVM/QEMU)
# https://download.mikrotik.com/routeros/7.25/chr-7.25.img.zip (Raw)

# Импортируйте 2 VM, дайте им 2 сетевых интерфейса: ether1 (WAN-мост) + ether2-10 (LAN, internal network)
# Залогиньтесь admin/без пароля, выполните:
# Для CHR-1:
import file-name=gw-core-01-initial.rsc
# Для CHR-2:
import file-name=gw-lab-01-broken.rsc

# Затем прогоните проект:
ansible-playbook playbooks/01-bootstrap.yml
ansible-playbook playbooks/02-inventory.yml
ansible-playbook playbooks/03-audit.yml  # увидите 80% vs 10%
ansible-playbook playbooks/04-baseline-apply.yml --tags diff --limit gw-lab-01
ansible-playbook playbooks/04-baseline-apply.yml --tags apply --limit gw-lab-01
ansible-playbook playbooks/03-audit.yml  # gw-lab-01 должен стать 80%+
```

## Отладка в текущем стенде

Стенд использует эмуляцию из-за ограничений Arena (нет KVM, download.mikrotik.com вне allowlist, лимит 128M):
- `stand/mock_routeros_api.py` — два процесса на 8728/8729 с разным MOCK_DATA
- `stand/start-dual.sh` — запуск обоих
- `inventory/hosts.yml` — gw-core-01:8728 + gw-lab-01:8729
- Прогон: `ansible-playbook playbooks/02-inventory.yml && playbooks/03-audit.yml` → 80% vs 10% (проверено 2026-10-29)
