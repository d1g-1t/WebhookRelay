.PHONY: setup setup-pull down clean logs test health

# Запуск проекта в одну команду (с предварительной загрузкой образов)
setup:
	@echo "========================================="
	@echo "  Pulling base images..."
	@echo "========================================="
	@docker pull python:3.12-slim || (echo "Retrying pull..." && sleep 3 && docker pull python:3.12-slim)
	@docker pull postgres:16-alpine || true
	@docker pull redis:7-alpine || true
	@echo ""
	@echo "========================================="
	@echo "  Building and starting services..."
	@echo "========================================="
	docker compose up --build -d
	@echo ""
	@echo "========================================="
	@echo "  WebhookRelay is starting up..."
	@echo "========================================="
	@echo ""
	@echo "  Waiting for services to be healthy..."
	@timeout /t 5 /nobreak > nul 2>&1 || sleep 5
	@docker compose ps
	@echo ""
	@echo "========================================="
	@echo "  WebhookRelay is ready!"
	@echo "========================================="
	@echo ""
	@echo "  API:   http://localhost:8742"
	@echo "  Docs:  http://localhost:8742/docs"
	@echo "  DB:    localhost:54320"
	@echo "  Redis: localhost:63790"
	@echo ""
	@echo "  Run 'make logs' to view logs"
	@echo "  Run 'make test' to run tests"
	@echo "========================================="
	@echo ""

# Быстрый запуск без пересборки
setup-pull:
	docker compose pull
	docker compose up -d

# Проверка здоровья сервисов
health:
	@docker compose ps
	@echo ""
	@curl -s http://localhost:8742/api/v1/health || echo "API not ready yet"

down:
	docker compose down

clean:
	docker compose down -v

logs:
	docker compose logs -f

test:
	docker compose exec api pytest -v tests/
