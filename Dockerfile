FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ROS_DEMO=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends tini && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY ros_orchestrator ./ros_orchestrator
RUN pip install -e .

COPY inventory.example.yml inventory.yml ./
COPY playbooks ./playbooks
COPY templates ./templates
RUN mkdir -p backups

EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["rosctl", "serve", "--host", "0.0.0.0", "--port", "8000"]
