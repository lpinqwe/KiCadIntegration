# KiCad Integration — schematic pipeline v1

Это репозиторий пайплайна для верификации KiCad-схем и каталога проверенных подсхем. Цель — давать AI-агентам возможность собирать схемы и проверять их до ревью человеком с помощью единых гейтов, которые работают и локально, и в CI.

## Что это

- **Только схемы и симуляции** (плата — v2). Фокус на сборке `.kicad_sch`, ERC, SPICE-верификации и единых гейтах для локального прогона агентом и CI.
- **Каталог блоков** в `library/<domain>/<block-name>/` с контрактом `block.yaml`, тестбенчем `bench/` и регламентированным форматом артефактов.
- **Единый код верификации** в `pipeline/verify/`. Гейты: `parse`, `lib-check`, `erc`, `datasheet`, `spice`.
- **Контейнерный запуск**: образ `kicad/kicad:10.0` + Python-инструменты (`kicad-skip`, `kicad-happy`, `ngspice`).

Подробности см. в спецификации: [docs/specs/2026-10-07-kicad-agent-pipeline-v1.md](docs/specs/2026-10-07-kicad-agent-pipeline-v1.md).

## Запуск локально

В окружении, где есть `docker` и доступ к образу `kicad/kicad:10.0`, можно запускать верификацию через контейнер.

Сборка образа пайплайна:

```bash
docker build -f pipeline/Dockerfile -t kicad-pipeline pipeline/
```

Проверка фикстуры:

```bash
docker run --rm -u 1000:1000 -v "$PWD:/work" -w /work -e HOME=/home/kicad \
  kicad-pipeline verify --project /work/fixtures/simple-divider --format both
```

Результаты пишутся в `<project>/reports/` (`report.json`, `report.md`, а также артефакты гейтов вроде `sim.json`, `erc.json`, `analysis.json`).

Проверить только SPICE-гейт с повышенной строгостью:

```bash
docker run --rm -u 1000:1000 -v "$PWD:/work" -w /work -e HOME=/home/kicad \
  kicad-pipeline verify --project /work/fixtures/simple-divider --only spice --strict
```

## Как добавить блок

1. Создать папку `library/<domain>/<block-name>/`. Домен из списка: `power`, `mcu`, `sensor-analog`, `sensor-digital`, `motor`, `servo`, `load`, `interface`, `misc`.
2. Подготовить `block.kicad_sch` (порты — global labels).
3. Описать контракт в `block.yaml` (§3.2).
4. Обязателен тестбенч `bench/`: `testbench.kicad_sch`, `checks.spice` (определения `.meas`), `expect.yaml` (§3.3). Без тестбенча блок не принимается.
5. По желанию добавить `README.md` и `datasheets/`.
6. Проверить локально через `verify` на тестбенче и прогнать регрессию существующих бенчей.
7. Открыть PR. Первые ~10 блоков ревьюит человек; далее автопроверка по гейтам.

См. разделы 3.1–3.3 и 5.3 спецификации для форматов файлов.
