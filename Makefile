.PHONY: install check stand audit baseline monitoring clean size

install:
	ansible-galaxy collection install -r collections/requirements.yml
	@echo "✓ collections installed"

check:
	ansible-playbook --syntax-check playbooks/*.yml
	ansible-lint playbooks/*.yml || true

stand:
	./scripts/check-stand.sh

audit:
	ansible-playbook playbooks/02-inventory.yml
	ansible-playbook playbooks/03-audit.yml
	@echo "Отчёты: reports/json/*.audit.json → Grafana http://192.168.0.10:3000"

baseline-diff:
	ansible-playbook playbooks/04-baseline-apply.yml --tags diff

baseline-apply:
	./scripts/rollout.sh apply

monitoring:
	docker compose -f monitoring/docker-compose.monitoring.yml up -d
	@echo "Prometheus http://192.168.0.10:9090  Grafana http://192.168.0.10:3000 admin/admin"

size:
	du -sh . .cache reports config/backups 2>/dev/null
	@echo "Лимит 128M — если превышен, make clean"

clean:
	rm -rf .cache/* reports/facts/* reports/json/* reports/prometheus/* config/backups/*
	@echo "Очищено (сообщите в ERROR_JOURNAL если мажор)"

journal:
	./scripts/journal.sh $(file) "$(msg)"
