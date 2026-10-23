# KiCad Integration — schematic pipeline v1

Это репозиторий пайплайна для верификации KiCad-схем и каталога проверенных подсхем. Цель — давать AI-агентам возможность собирать схемы и проверять их до ревью человеком с помощью единых гейтов, которые работают и локально, и в CI.

## Что это

- **Только схемы и симуляции** (плата — v2). Фокус на сборке `.kicad_sch`, ERC, SPICE-верификации и единых гейтах для локального прогона агентом и CI.
- **Каталог блоков** в `library/<domain>/<block-name>/` с контрактом `block.yaml`, тестбенчем `bench/` и регламентированным форматом артефактов.
- **Единый код верификации** в `pipeline/verify/`. Гейты: `parse`, `lib-check`, `erc`, `datasheet`, `spice`.
- **Контейнерный запуск**: образ `kicad/kicad:10.0` (закреплён по digest в `pipeline/Dockerfile`) + Python-инструменты (`kicad-skip`, `kicad-happy`, `ngspice`).

Подробности см. в спецификации: [docs/specs/2026-10-07-kicad-agent-pipeline-v1.md](docs/specs/2026-10-07-kicad-agent-pipeline-v1.md).

## Запуск локально

### Через docker compose (рекомендуется)

Сборка и запуск гейтов на фикстуре (по умолчанию — `fixtures/simple-divider`):

```bash
docker compose -f pipeline/docker-compose.yml build
docker compose -f pipeline/docker-compose.yml run verify
```

Свой проект — через явный `--project` (путь внутри контейнера, `/work` — корень репозитория):

```bash
docker compose -f pipeline/docker-compose.yml run verify --project /work/fixtures/missing-power
docker compose -f pipeline/docker-compose.yml run verify --project /work/fixtures/simple-divider --only parse
```

Сервисы: `verify` — гейты фазы 2, `sim` — глубокий прогон spice (фаза 3),
`ci` — те же гейты с `--format both`. Каталог репозитория монтируется в `/work`.

### Через docker run

Сборка образа пайплайна:

```bash
docker build -f pipeline/Dockerfile -t kicad-pipeline pipeline/
```

Проверка фикстуры. Единый стиль вызова — явный `verify --project <путь внутри контейнера>`:

```bash
docker run --rm -u 1000:1000 -v "$PWD:/work" -w /work -e HOME=/home/kicad \
  kicad-pipeline verify --project /work/fixtures/simple-divider --format both
```

Проверить только SPICE-гейт с повышенной строгостью:

```bash
docker run --rm -u 1000:1000 -v "$PWD:/work" -w /work -e HOME=/home/kicad \
  kicad-pipeline verify --project /work/fixtures/simple-divider --only spice --strict
```

### Локально без Docker

В окружении с установленными `kicad-skip`, `PyYAML` (см. `pipeline/requirements.txt`):

```bash
python3 pipeline/verify/__main__.py --project fixtures/simple-divider --only parse
```

Результаты пишутся в `<project>/reports/` (`report.json`, `report.md`, а также артефакты гейтов вроде `sim.json`, `erc.json`, `analysis.json`).

### Тесты

```bash
python3 -m pytest -q pipeline/tests
```

## Как добавить блок

1. Создать папку `library/<domain>/<block-name>/`. Домен из списка: `power`, `mcu`, `sensor-analog`, `sensor-digital`, `motor`, `servo`, `load`, `interface`, `misc`.
2. Подготовить `block.kicad_sch` (порты — global labels).
3. Описать контракт в `block.yaml` (§3.2).
4. Обязателен тестбенч `bench/`: `testbench.kicad_sch`, `checks.spice` (определения `.meas`), `expect.yaml` (§3.3). Без тестбенча блок не принимается.
5. По желанию добавить `README.md` и `datasheets/`.
6. Проверить локально через `verify` на тестбенче и прогнать регрессию существующих бенчей.
7. Открыть PR. Первые ~10 блоков ревьюит человек; далее автопроверка по гейтам.

### Правило `--strict` для блоков библиотеки

Гейт `spice` без `bench/expect.yaml` даёт `status: skip` и exit 0 — это ок для регрессии фикстур («skip работает»), но **дыра для блоков каталога**: блок без теста прошёл бы CI.

Правило: **блок библиотеки принимается только с `bench/`; в CI блоки прогоняются с `verify --strict`**, поэтому `spice: skip` (и любые warning'и/soft-гейты) становятся fail. Локально перед PR:

```bash
docker run --rm -u 1000:1000 -v "$PWD:/work" -w /work -e HOME=/home/kicad \
  kicad-pipeline verify --project /work/library/<domain>/<block-name> --strict --format both
```

См. разделы 3.1–3.3 и 5.3 спецификации для форматов файлов.

## CHANGELOG

- **Версия** = мерж PR, **идентификатор** = номер PR.
- **Записи генерируются** `git-cliff` при релизе, руками не ведутся.
- **Локально:**
  - `git cliff --unreleased` — просмотр черновика
  - `git cliff --tag v1.0.0 -o CHANGELOG.md` — генерация для релиза
