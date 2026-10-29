.PHONY: install dev test lint run serve docker

install:
	python -m venv .venv && .venv/bin/pip install -e .

dev:
	.venv/bin/pip install -e ".[dev]"

test:
	.venv/bin/pytest -q

lint:
	.venv/bin/rosctl lint playbooks/example.yml

run:
	.venv/bin/rosctl inventory list
	.venv/bin/rosctl exec "/system/resource/print" -g edge

serve:
	.venv/bin/rosctl serve --host 0.0.0.0 --port 8000

docker:
	docker compose up --build

demo:
	.venv/bin/rosctl exec "/system/resource/print" -g edge
	.venv/bin/rosctl play playbooks/example.yml --dry-run --diff
	.venv/bin/rosctl backup create -g edge
	.venv/bin/rosctl monitor stats
