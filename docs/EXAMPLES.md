# Примеры использования rosctl

## 1. Массовая смена DNS
```bash
rosctl exec "/ip dns set servers=1.1.1.1,9.9.9.9" -g edge --dry-run
rosctl exec "/ip dns set servers=1.1.1.1,9.9.9.9" -g edge
```

## 2. Плейбук VLAN для филиалов
```yaml
# playbooks/vlan.yml уже готов — запуск:
rosctl play playbooks/vlan.yml --limit branch -e vlan_id=20 --diff --dry-run
rosctl play playbooks/vlan.yml --limit branch
```

## 3. WireGuard mesh
```bash
rosctl wireguard genkey
# вставьте ключи в inventory.yml vars
rosctl play playbooks/wireguard.yml --limit edge --tags wireguard --diff
rosctl wireguard status -g edge
```

## 4. Бэкапы и откат
```bash
rosctl backup create -g edge
rosctl backup list gw-msk-01
rosctl backup diff gw-msk-01
# восстановить вручную:
cat backups/gw-msk-01/20251029-120000.rsc | ssh admin@10.10.0.1
```

## 5. Мониторинг в CI
```bash
rosctl monitor stats --json | jq '.alerts'
rosctl monitor stats -g prod --watch
rosctl audit -g edge
```

## 6. Шаблоны
```bash
rosctl template render base.rsc.j2 --host gw-msk-01 --var timezone=Europe/Berlin > /tmp/out.rsc
rosctl exec "/import file=/tmp/out.rsc" --limit gw-msk-01
```

## 7. Web API (curl)
```bash
curl http://localhost:8000/api/inventory | jq
curl -X POST http://localhost:8000/api/exec -H 'Content-Type: application/json' \
  -d '{"command":"/system/resource/print","group":"edge"}' | jq
curl -X POST http://localhost:8000/api/playbook/run -H 'Content-Type: application/json' \
  -d '{"playbook":"example","dry_run":true,"diff":true}' | jq
```

## 8. Расписание (через cron + systemd)
```bash
# /etc/cron.d/rosctl
0 3 * * * root /opt/rosctl/.venv/bin/rosctl backup create --group all && /opt/rosctl/.venv/bin/rosctl play /opt/rosctl/playbooks/harden.yml
```
