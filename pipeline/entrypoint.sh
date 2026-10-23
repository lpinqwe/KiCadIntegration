#!/bin/sh
# Точка входа контейнера: первый аргумент без "-" — PROJECT (каталог проекта),
# остальные аргументы передаются verify-CLI как есть.
#
# Примеры:
#   docker compose run verify fixtures/simple-divider
#   docker compose run verify fixtures/missing-power --only parse
#   docker run ... kicad-pipeline --project /work/fixtures/simple-divider
#   docker run ... kicad-pipeline verify --project /work/fixtures/no-bench
#     (слово "verify" для совместимости со старым вызовом отбрасывается)
set -e

if [ "$1" = "verify" ]; then
    shift
fi

PROJECT="${PROJECT:-/work}"
if [ "$#" -gt 0 ]; then
    case "$1" in
        -*) ;;
        *) PROJECT="$1"; shift ;;
    esac
fi

exec /opt/venv/bin/python3 /opt/pipeline/verify/__main__.py --project "$PROJECT" "$@"
