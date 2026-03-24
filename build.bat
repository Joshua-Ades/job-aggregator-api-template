@echo off
:: ─────────────────────────────────────────────────────────────────────────────
::  Job Aggregator API — Windows build helper
::  Usage:  build.bat [command]
::  Same targets as the Makefile, for machines without GNU Make.
:: ─────────────────────────────────────────────────────────────────────────────

set CMD=%1

if "%CMD%"=="" goto help
if "%CMD%"=="help" goto help
if "%CMD%"=="setup" goto setup
if "%CMD%"=="build" goto build
if "%CMD%"=="test" goto test
if "%CMD%"=="test-rebuild" goto test_rebuild
if "%CMD%"=="up" goto up
if "%CMD%"=="up-full" goto up_full
if "%CMD%"=="down" goto down
if "%CMD%"=="logs" goto logs
if "%CMD%"=="smoke" goto smoke
if "%CMD%"=="clean" goto clean

echo Unknown command: %CMD%
goto help

:help
echo.
echo   Job Aggregator API
echo   ---------------------------------------------------------
echo   build.bat setup          Copy .env.example to .env
echo   build.bat build          Build all Docker images
echo   build.bat test           Run full pytest suite (49 tests)
echo   build.bat test-rebuild   Force rebuild test image + run tests
echo   build.bat up             Start API + DB + Redis (background)
echo   build.bat up-full        Start full stack incl. Celery
echo   build.bat down           Stop all containers
echo   build.bat logs           Tail logs for all services
echo   build.bat smoke          Run live endpoint smoke test
echo   build.bat clean          Remove containers, volumes, images
echo   ---------------------------------------------------------
echo.
goto end

:setup
if not exist .env (
    copy .env.example .env
    echo [setup] .env created -- open it and fill in your API keys
) else (
    echo [setup] .env already exists -- skipping
)
goto end

:build
docker compose build
goto end

:test
docker compose --profile test run --rm test
goto end

:test_rebuild
docker compose --profile test run --rm --build test
goto end

:up
docker compose up web db redis -d
goto end

:up_full
docker compose up --build -d
goto end

:down
docker compose down
goto end

:logs
docker compose logs -f
goto end

:smoke
python scripts/smoke_test.py
goto end

:clean
docker compose down -v --rmi local
goto end

:end
