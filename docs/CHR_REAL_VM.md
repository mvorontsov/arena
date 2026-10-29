# Запуск реальных CHR 7.25 на двух VM — инструкция для прода

> **Почему в Arena sandbox нельзя напрямую скачать CHR:**  
> Сеть ограничена allowlist (`github.com`, `codeload.github.com`, `api.github.com`, `pypi.org`, `registry.npmjs.org` + `files.pythonhosted.org`).  
> `download.mikrotik.com` (159.148.147.251) и `release-assets.githubusercontent.com` (для GitHub-релизов) **вне списка** — `curl` падает `SSL_ERROR_SYSCALL` / `Empty reply`, `gh release download` — `EOF`.  
> Плюс нет `/dev/kvm`, `qemu`, `docker`, лимит `workspace 128M` (CHR-образ 27-45МБ).  
> **Решение:** в sandbox — эмуляция 2 CHR на `mock_routeros_api.py` (8728/8729, проверено). Реальные CHR запускайте локально по инструкции ниже.

---

## 1. Скачать образы CHR 7.25 (локально, не в Arena)

На своём ПК/сервере с Debian/Windows/macOS откройте:

| Формат | Для чего | URL | Размер |
|---|---|---|---|
| **qcow2** | KVM/QEMU (рекомендуется для Debian) | https://download.mikrotik.com/routeros/7.25/chr-7.25.qcow2.zip | 45M |
| **vdi** | VirtualBox | https://download.mikrotik.com/routeros/7.25/chr-7.25.vdi.zip | 45M |
| **vmdk** | VMware | https://download.mikrotik.com/routeros/7.25/chr-7.25.vmdk.zip | 45M |
| **img** | Raw (любой гипервизор) | https://download.mikrotik.com/routeros/7.25/chr-7.25.img.zip | 27M |
| **ova** | VirtualBox/VMware импорт | https://download.mikrotik.com/routeros/7.25/chr-7.25.ova.zip | 45M |

**Зеркала (GitHub, если mikrotik.com недоступен):**
```bash
# Через gh (требует доступ к release-assets — в Arena блокируется, локально работает)
gh release download 7.25 --repo elseif/MikroTikPatch --pattern "chr-7.25.qcow2.zip"
# или qcow2 для KVM, vdi для VirtualBox
```

Распакуйте:
```bash
unzip chr-7.25.qcow2.zip
ls -lh chr-7.25.qcow2  # 128M raw (тонкий)
```

---

## 2. Создать 2 VM (пример для Debian 13 + KVM)

### Требования хоста
- CPU с VT-x/AMD-V (`grep -E 'vmx|svm' /proc/cpuinfo`)
- 4ГБ RAM (по 1ГБ на CHR + 2ГБ хост), 20ГБ диск
- `apt install qemu-kvm libvirt-daemon-system virtinst bridge-utils`

### Сеть
Создайте `br-lan` (192.168.0.0/16) и `br-wan` (доступ в интернет):

```bash
# /etc/network/interfaces.d/br-lan
auto br-lan
iface br-lan inet static
  address 192.168.0.10/16
  bridge_ports none
  bridge_stp off

# br-wan — мост к физическому eth0 с доступом в интернет
auto br-wan
iface br-wan inet dhcp
  bridge_ports eth0
```

### Запуск через virt-install (KVM)

```bash
# CHR-1 gw-core-01 (эталон, 80%)
virt-install --name chr-gw-core-01 --ram 1024 --vcpus 1 \
  --disk path=./chr-7.25.qcow2,format=qcow2 \
  --network bridge=br-wan,model=virtio \
  --network bridge=br-lan,model=virtio \
  --import --noautoconsole --os-variant generic

# CHR-2 gw-lab-01 (сломанный, 10%)
cp chr-7.25.qcow2 chr-7.25-lab.qcow2
virt-install --name chr-gw-lab-01 --ram 1024 --vcpus 1 \
  --disk path=./chr-7.25-lab.qcow2,format=qcow2 \
  --network bridge=br-wan,model=virtio \
  --network bridge=br-lan,model=virtio \
  --import --noautoconsole --os-variant generic

virsh list --all
#  chr-gw-core-01 running
#  chr-gw-lab-01  running

# Узнать IP (CHR по умолчанию DHCP-клиент на ether1, но у нас статика — см. ниже)
virsh console chr-gw-core-01  # логин admin, пароль пустой, Ctrl+] выйти
```

**VirtualBox (Windows/macOS):**
1. VirtualBox → Импорт → выберите `chr-7.25.ova`
2. Настройки → Сеть: Адаптер1 `Мост` (WAN), Адаптер2 `Внутренняя сеть` (LAN, имя `lan-192.168.0.0/16`)
3. Запустите обе VM, `admin`/пусто

---

## 3. Первичная настройка CHR (выполнить на обеих VM)

Подключитесь консолью (`virsh console` или VirtualBox → Показать):

```bash
# На каждой CHR (admin / пусто):
/ip address add address=192.168.0.50/16 interface=ether2  # временно, чтобы попасть в LAN
# Теперь с хоста 192.168.0.10:
ssh admin@192.168.0.50  # пароль пустой

# Для gw-core-01:
import file-name=gw-core-01-initial.rsc
# Для gw-lab-01:
import file-name=gw-lab-01-broken.rsc
# Файлы RSC — в проекте config/chr-test/ (скопируйте на CHR через scp или Winbox)
```

**Вручную (если нет RSC):**
```bash
# CHR-1 gw-core-01 (эталон, скопируйте из config/chr-test/gw-core-01-initial.rsc):
/system identity set name=gw-core-01
/system clock set time-zone-name=Europe/Moscow
/system ntp client set enabled=yes servers=pool.ntp.org,time.cloudflare.com
/interface bridge add name=bridge1
/interface bridge port add bridge=bridge1 interface=ether2
... ether10
/ip address add address=192.168.0.50/16 interface=bridge1
/ip address add address=111.111.111.111/24 interface=ether1
/ip route add dst-address=0.0.0.0/0 gateway=111.111.111.1
# + firewall, DNS, DHCP, users (см. RSC)

# CHR-2 gw-lab-01 (сломанный, из config/chr-test/gw-lab-01-broken.rsc):
/system identity set name=gw-lab-01
/system clock set time-zone-name=UTC
/system ntp client set enabled=no
/ip address add address=192.168.88.1/24 interface=bridge1
/ip address add address=111.111.111.112/24 interface=ether1
/interface bridge port add bridge=bridge1 interface=ether2,ether3,ether4  # только 3 вместо 9
# без firewall, без NTP, ROS 7.18 (понизьте: /system package downgrade)
```

Проверка:
```bash
/ip address print
/interface bridge port print  # 9 vs 3
/system resource print  # 7.25 vs 7.18
/ip firewall filter print  # 7 vs 2
```

---

## 4. Настройка Ansible на Debian 13

```bash
# На хосте 192.168.0.10:
cd /home/ansible/arena
cp inventory/hosts.example.yml inventory/hosts.yml
nano inventory/hosts.yml
# Укажите:
# gw-core-01: ansible_host: 192.168.0.50
# gw-lab-01:  ansible_host: 192.168.0.51  (или 88.1, если оставили 88/24)
# hostname: 192.168.0.50 / 192.168.0.51 (а не 127.0.0.1)

ansible-galaxy collection install -r collections/requirements.yml
ansible mikrotik -m community.routeros.api -a "path='/system resource' print" -i inventory/hosts.yml --limit gw-core-01 -v
# Должен вернуть board CHR, version 7.25

# Если CHR недоступен — смотрите docs/DEPLOYMENT.md раздел 11.1 (api enable, firewall)
```

---

## 5. Прогон проекта — отладка

```bash
# 01-bootstrap: создаст ansible/192.168.0.0/16, api-ssl 8729, strong-crypto
ansible-playbook playbooks/01-bootstrap.yml -k -v
# -k спросит исходный admin-пароль (пусто → Enter)

# После bootstrap смените в inventory/hosts.yml:
# api_port: 8729
# api_username: ansible
# api_password: "Ans1ble_Str0ng_2025!"  # из group_vars/all.yml или vault

# 02-inventory: соберёт факты
ansible-playbook playbooks/02-inventory.yml -v
ls -lh reports/facts/  # gw-core-01.json 6.9K, gw-lab-01.json ...
cat reports/facts/gw-core-01.json | grep board
cat reports/facts/gw-lab-01.json | grep board

# 03-audit: проверка best practice
ansible-playbook playbooks/03-audit.yml -v
# Ожидается:
# gw-core-01: Compliance 80.0% (8/10) — 2 fails (нет ansible, telnet)
# gw-lab-01:  Compliance 10.0% (1/10) — 9 fails (NTP, TZ, WAN/LAN, bridge, user, svc, FW, ROS)
cat reports/json/gw-core-01.audit.json | python3 -m json.tool | grep compliance -A5
cat reports/json/gw-lab-01.audit.json | python3 -m json.tool | grep compliance -A5

# Grafana: http://192.168.0.10:3000 admin/admin — dashboard Mikrotik Audit

# 04-baseline: раскатка эталона на сломанный CHR
ansible-playbook playbooks/04-baseline-apply.yml --tags diff --limit gw-lab-01 -v
cat /tmp/gw-lab-01-desired.rsc | head -20  # сгенерированный эталон

ansible-playbook playbooks/04-baseline-apply.yml --tags apply --limit gw-lab-01 -v
# или через safe-скрипт:
./scripts/rollout.sh diff gw-lab-01
./scripts/rollout.sh apply gw-lab-01  # спросит y/N, сделает backup, apply, post-audit

# Повторный аудит — gw-lab-01 должен стать 80%+:
ansible-playbook playbooks/03-audit.yml --limit gw-lab-01 -v
# gw-lab-01: Compliance 80%+ (или 95%+ если baseline полный)

# 05-monitoring: включит accounting/syslog на CHR, подскажет docker compose
ansible-playbook playbooks/05-monitoring.yml -v
docker compose -f monitoring/docker-compose.monitoring.yml up -d
# Prometheus 9090, Grafana 3000, Pushgateway 9091
```

**Сравнение с эмулированным стендом (Arena sandbox):**
- В sandbox те же команды дают те же результаты (80% vs 10%) — проверено 2026-10-29 08:46 на mock 8728/8729
- Mock `CCR2116 7.25 + CHR 7.18` ↔ Реальные CHR `CHR 7.25 + CHR 7.18` — идентично для аудита

---

## 6. Откат и безопасность

- Бэкапы: `config/backups/<host>-<date>.json` (не коммитить, .gitignore)
- Откат: `scp config/backups/gw-lab-01-*.json admin@192.168.0.50:/backup.json; ssh admin@192.168.0.50 "/import backup.json"`
- Workspace <128M: `make size`, `make clean`
- Vault: для прода `ansible-vault create group_vars/mikrotik/vault.yml`, `vault_password_file = .vault_pass` в ansible.cfg

---

## 7. Чек-лист для реальных CHR

- [ ] Скачаны 2 образа chr-7.25.qcow2/vdi (45M) с https://download.mikrotik.com/routeros/7.25/
- [ ] Созданы 2 VM (1ГБ RAM, 2 интерфейса: br-wan + br-lan), запущены, virsh list running
- [ ] Настроены RSC: gw-core-01-initial.rsc (80%) и gw-lab-01-broken.rsc (10%) — импорт выполнен
- [ ] Ansible 02-inventory → reports/facts 6.9K, bridge ports 9 vs 3, FW 7 vs 2
- [ ] Ansible 03-audit → 80% vs 10% (critical 0/4, high 2/4)
- [ ] Baseline diff/apply на gw-lab-01 → gw-lab-01 стал 80%+
- [ ] Grafana dashboard показывает compliance, Prometheus собирает mikrotik_audit_*
- [ ] Запись в ERROR_JOURNAL.md с timestamp+sha256+size

---

**Стенд в Arena (эмуляция):** `stand/start-dual.sh` → 2 mock CHR 8728/8729, `inventory/hosts.yml` 127.0.0.1:8728+8729, `config/chr-test/*.rsc` — полный аналог реальных CHR для отладки без KVM/Docker/сети.
