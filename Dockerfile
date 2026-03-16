FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN mkdir -p src/webhook_relay && \
    touch src/webhook_relay/__init__.py && \
    pip install --no-cache-dir -e ".[dev]"

COPY . .
RUN pip install --no-cache-dir -e ".[dev]"

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
