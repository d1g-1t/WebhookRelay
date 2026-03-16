#!/bin/bash
# WebhookRelay Setup Script
# Автоматическая настройка и запуск проекта для Linux/Mac

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

echo -e "${CYAN}=========================================${NC}"
echo -e "${CYAN}  WebhookRelay Setup${NC}"
echo -e "${CYAN}=========================================${NC}"
echo ""

# Проверка Docker
echo -e "${YELLOW}Checking Docker...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker not found. Please install Docker.${NC}"
    exit 1
fi
DOCKER_VERSION=$(docker --version)
echo -e "${GREEN}✓ Docker found: ${DOCKER_VERSION}${NC}"

# Проверка Docker daemon
echo -e "${YELLOW}Checking Docker daemon...${NC}"
if ! docker info &> /dev/null; then
    echo -e "${RED}✗ Docker daemon is not running. Please start Docker.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker daemon is running${NC}"

echo ""
echo -e "${CYAN}=========================================${NC}"
echo -e "${CYAN}  Pulling base images...${NC}"
echo -e "${CYAN}=========================================${NC}"
echo ""

# Функция для pull с retry
pull_image_with_retry() {
    local image=$1
    local max_retries=3
    local retry=0

    while [ $retry -lt $max_retries ]; do
        echo -e "${YELLOW}Pulling ${image}...${NC}"
        if docker pull "$image" 2>&1; then
            echo -e "${GREEN}✓ ${image} pulled successfully${NC}"
            return 0
        else
            retry=$((retry + 1))
            if [ $retry -lt $max_retries ]; then
                echo -e "${YELLOW}! Retry ${retry}/${max_retries} for ${image}${NC}"
                sleep 3
            else
                echo -e "${RED}✗ Failed to pull ${image} after ${max_retries} attempts${NC}"
                return 1
            fi
        fi
    done
}

# Pull базовых образов
images=(
    "python:3.12-slim"
    "postgres:16-alpine"
    "redis:7-alpine"
)

all_success=true
for image in "${images[@]}"; do
    if ! pull_image_with_retry "$image"; then
        all_success=false
    fi
done

if [ "$all_success" = false ]; then
    echo ""
    echo -e "${YELLOW}⚠ Some images failed to pull, but continuing with build...${NC}"
fi

echo ""
echo -e "${CYAN}=========================================${NC}"
echo -e "${CYAN}  Building and starting services...${NC}"
echo -e "${CYAN}=========================================${NC}"
echo ""

# Остановка старых контейнеров
docker compose down 2>/dev/null || true

# Сборка и запуск
if docker compose up --build -d; then
    echo -e "${GREEN}✓ Services started successfully${NC}"
else
    echo -e "${RED}✗ Failed to start services${NC}"
    echo ""
    echo -e "${YELLOW}Showing logs:${NC}"
    docker compose logs
    exit 1
fi

echo ""
echo -e "${YELLOW}Waiting for services to be healthy...${NC}"
sleep 8

echo ""
echo -e "${CYAN}=========================================${NC}"
echo -e "${CYAN}  Service Status${NC}"
echo -e "${CYAN}=========================================${NC}"
docker compose ps

echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  WebhookRelay is ready!${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo -e "${WHITE}  📡 API:   ${CYAN}http://localhost:8742${NC}"
echo -e "${WHITE}  📚 Docs:  ${CYAN}http://localhost:8742/docs${NC}"
echo -e "${WHITE}  🗄️  DB:    ${CYAN}localhost:54320${NC}"
echo -e "${WHITE}  🔴 Redis: ${CYAN}localhost:63790${NC}"
echo ""
echo -e "${YELLOW}  Useful commands:${NC}"
echo -e "${WHITE}    make logs    ${GRAY}# View logs${NC}"
echo -e "${WHITE}    make test    ${GRAY}# Run tests${NC}"
echo -e "${WHITE}    make down    ${GRAY}# Stop services${NC}"
echo -e "${WHITE}    make clean   ${GRAY}# Stop and remove volumes${NC}"
echo ""
echo -e "${GREEN}=========================================${NC}"
echo ""

# Проверка API health
echo -e "${YELLOW}Checking API health...${NC}"
sleep 2
if curl -sf http://localhost:8742/api/v1/health > /dev/null; then
    echo -e "${GREEN}✓ API is healthy and responding${NC}"
else
    echo -e "${YELLOW}⚠ API is still starting up. Check with: make logs${NC}"
fi

echo ""

