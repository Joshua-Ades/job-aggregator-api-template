#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  Job Aggregator API — build helper (Mac / Linux)
#  Usage:  chmod +x build.sh && ./build.sh [command]
# ─────────────────────────────────────────────────────────────────────────────

CMD=${1:-help}

case "$CMD" in

  help)
    echo ""
    echo "  Job Aggregator API"
    echo "  ---------------------------------------------------------"
    echo "  ./build.sh setup          Copy .env.example to .env"
    echo "  ./build.sh build          Build all Docker images"
    echo "  ./build.sh test           Run full pytest suite (49 tests)"
    echo "  ./build.sh test-rebuild   Force rebuild test image + run tests"
    echo "  ./build.sh up             Start API + DB + Redis (background)"
    echo "  ./build.sh up-full        Start full stack incl. Celery"
    echo "  ./build.sh down           Stop all containers"
    echo "  ./build.sh logs           Tail logs for all services"
    echo "  ./build.sh smoke          Run live endpoint smoke test"
    echo "  ./build.sh clean          Remove containers, volumes, images"
    echo "  ---------------------------------------------------------"
    echo ""
    ;;

  setup)
    if [ ! -f .env ]; then
      cp .env.example .env
      echo "[setup] .env created — open it and fill in your API keys"
    else
      echo "[setup] .env already exists — skipping"
    fi
    ;;

  build)
    docker compose build
    ;;

  test)
    docker compose --profile test run --rm test
    ;;

  test-rebuild)
    docker compose --profile test run --rm --build test
    ;;

  up)
    docker compose up web db redis -d
    ;;

  up-full)
    docker compose up --build -d
    ;;

  down)
    docker compose down
    ;;

  logs)
    docker compose logs -f
    ;;

  smoke)
    python scripts/smoke_test.py
    ;;

  clean)
    docker compose down -v --rmi local
    ;;

  *)
    echo "Unknown command: $CMD"
    echo "Run ./build.sh help for available commands"
    exit 1
    ;;
esac
