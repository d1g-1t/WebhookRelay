#!/bin/sh
set -e

case "$1" in
  api)
    echo "Running migrations..."
    alembic upgrade head
    echo "Starting API server..."
    exec uvicorn webhook_relay.main:app --host 0.0.0.0 --port 8000 --log-level info
    ;;
  worker)
    echo "Starting delivery worker..."
    exec arq webhook_relay.worker.arq_worker.WorkerSettings
    ;;
  *)
    exec "$@"
    ;;
esac
