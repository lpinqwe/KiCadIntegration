# Каталог проверенных подсхем (library/)

Каталог содержит переиспользуемые блоки KiCad. Каждый блок — это подсхема с формализованным контрактом и тестбенчем для верификации.

## Структура блока (§3.1–§3.2)

Для каждого блока `library/<domain>/<block-name>/` обязательны следующие артефакты:

```text
<domain>/<block-name>/
  block.kicad_sch        # подсхема (порты — global labels)
  block.yaml             # интерфейс и контракт блока
  bench/
    testbench.kicad_sch  # тестовый бенч (возбуждение + нагрузка)
    checks.spice         # определения .meas для ngspice
    expect.yaml          # ожидаемые значения, допуски, типы проверок
  README.md
  datasheets/            # PDF/JSON по MPN (опционально)
```

`<domain>` — из фиксированного списка: `power`, `mcu`, `sensor-analog`, `sensor-digital`, `motor`, `servo`, `load`, `interface`, `misc`.

## Обязательность block.yaml

Файл `block.yaml` обязателен (§3.2). Блок без контракта в каталог не попадает. В нём фиксируются порты (направления, типы, допуски), лимиты, состав частей и статус верификации.

## Обязательность bench/ и правило `--strict`

Тестбенч обязателен для принятия блока в каталог (§5.3): **блок библиотеки принимается только с `bench/`**.

Важно понимать поведение гейта: без `bench/expect.yaml` гейт `spice` работает в режиме `skip` и не проваливает верификацию (exit 0). Это нормально для регрессии фикстур («skip работает»), но недопустимо для блоков каталога — блок без теста прошёл бы CI.

Поэтому **в CI блоки библиотеки прогоняются с `verify --strict`**: с флагом `--strict` warning'и и soft-гейты (включая `spice: skip`) тоже роняют прогон. Локально перед PR проверяй блок так же:

```bash
docker run --rm -u 1000:1000 -v "$PWD:/work" -w /work -e HOME=/home/kicad \
  kicad-pipeline verify --project /work/library/<domain>/<block-name> --strict --format both
```

Если `bench/` есть, но прогон с `--strict` падает — блок не принимается, пока гейты не зелёные.

## Пример структуры

```text
library/power/ldo-3v3/
  block.kicad_sch
  block.yaml
  bench/
    testbench.kicad_sch
    checks.spice
    expect.yaml
  README.md
```

См. также: `docs/specs/2026-10-07-kicad-agent-pipeline-v1.md`.
