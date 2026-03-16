#!/usr/bin/env pwsh
# WebhookRelay Setup Script
# Автоматическая настройка и запуск проекта

$ErrorActionPreference = "Stop"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  WebhookRelay Setup" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Checking Docker..." -ForegroundColor Yellow
try {
    $dockerVersion = docker --version
    Write-Host "✓ Docker found: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker not found. Please install Docker Desktop." -ForegroundColor Red
    exit 1
}

Write-Host "Checking Docker daemon..." -ForegroundColor Yellow
try {
    docker info | Out-Null
    Write-Host "✓ Docker daemon is running" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker daemon is not running. Please start Docker Desktop." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Pulling base images..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

function Pull-ImageWithRetry {
    param(
        [string]$ImageName,
        [int]$MaxRetries = 3
    )

    $retries = 0
    while ($retries -lt $MaxRetries) {
        try {
            Write-Host "Pulling $ImageName..." -ForegroundColor Yellow
            docker pull $ImageName
            Write-Host "✓ $ImageName pulled successfully" -ForegroundColor Green
            return $true
        } catch {
            $retries++
            if ($retries -lt $MaxRetries) {
                Write-Host "! Retry $retries/$MaxRetries for $ImageName" -ForegroundColor Yellow
                Start-Sleep -Seconds 3
            } else {
                Write-Host "✗ Failed to pull $ImageName after $MaxRetries attempts" -ForegroundColor Red
                return $false
            }
        }
    }
}

$images = @(
    "python:3.12-slim",
    "postgres:16-alpine",
    "redis:7-alpine"
)

$allSuccess = $true
foreach ($image in $images) {
    if (-not (Pull-ImageWithRetry -ImageName $image)) {
        $allSuccess = $false
    }
}

if (-not $allSuccess) {
    Write-Host ""
    Write-Host "⚠ Some images failed to pull, but continuing with build..." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Building and starting services..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

docker compose down 2>$null

try {
    docker compose up --build -d
    Write-Host "✓ Services started successfully" -ForegroundColor Green
} catch {
    Write-Host "✗ Failed to start services" -ForegroundColor Red
    Write-Host ""
    Write-Host "Showing logs:" -ForegroundColor Yellow
    docker compose logs
    exit 1
}

Write-Host ""
Write-Host "Waiting for services to be healthy..." -ForegroundColor Yellow
Start-Sleep -Seconds 8

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Service Status" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
docker compose ps

Write-Host ""
Write-Host "=========================================" -ForegroundColor Green
Write-Host "  WebhookRelay is ready!" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  📡 API:   " -NoNewline -ForegroundColor White
Write-Host "http://localhost:8742" -ForegroundColor Cyan
Write-Host "  📚 Docs:  " -NoNewline -ForegroundColor White
Write-Host "http://localhost:8742/docs" -ForegroundColor Cyan
Write-Host "  🗄️  DB:    " -NoNewline -ForegroundColor White
Write-Host "localhost:54320" -ForegroundColor Cyan
Write-Host "  🔴 Redis: " -NoNewline -ForegroundColor White
Write-Host "localhost:63790" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Useful commands:" -ForegroundColor Yellow
Write-Host "    make logs    " -NoNewline -ForegroundColor White
Write-Host "# View logs" -ForegroundColor Gray
Write-Host "    make test    " -NoNewline -ForegroundColor White
Write-Host "# Run tests" -ForegroundColor Gray
Write-Host "    make down    " -NoNewline -ForegroundColor White
Write-Host "# Stop services" -ForegroundColor Gray
Write-Host "    make clean   " -NoNewline -ForegroundColor White
Write-Host "# Stop and remove volumes" -ForegroundColor Gray
Write-Host ""
Write-Host "=========================================" -ForegroundColor Green
Write-Host ""

Write-Host "Checking API health..." -ForegroundColor Yellow
Start-Sleep -Seconds 2
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8742/api/v1/health" -UseBasicParsing -TimeoutSec 5
    if ($response.StatusCode -eq 200) {
        Write-Host "✓ API is healthy and responding" -ForegroundColor Green
    }
} catch {
    Write-Host "⚠ API is still starting up. Check with: make logs" -ForegroundColor Yellow
}

Write-Host ""

