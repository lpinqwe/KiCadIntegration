# Спецификация v1 — схематический пайплайн с верификацией

Дата: 2026-10-07
Статус: draft, на ревью у заказчика
Объём: **только схемы и симуляции**. Плата (placement/routing/DRC) — v2.

---

## 1. Цель

Дать AI-агентам способ собирать схемы и **проверять свою работу до того, как человек их увидит**. Не «запретить косячить», а дать проверенный материал, из которого собирается схема, плюс гейты, которые ловят оставшиеся ошибки машинно.

Заказчик работает как с кодом: агенты пушат из любой точки, при необходимости человек делает `git pull` и открывает схему в локальном KiCad или симуляторе.

### Границы v1

| Входит | Не входит (v2) |
|---|---|
| Сборка `.kicad_sch` агентом | Размещение компонентов |
| Каталог проверенных подсхем | Трассировка, роутинг |
| ERC-гейт | DRC-гейт |
| SPICE-верификация, corner/Monte Carlo | Импеданс-чек, `.kicad_dru` |
| PR + CI + отчёт | Gerber/производство |
| Индекс каталога для поиска | Эмбеддинги/RAG |

### Широта покрытия (заказчик)

Обвязка ESP/MCU, периферия, аналоговые датчики, цифровые датчики, двигатели, нагрузка, серво. Реализуется не перечислением, а **каталогом подсхем**, который пополняется самими агентами.

---

## 2. Ключевые решения

| # | Решение | Обоснование |
|---|---|---|
| D1 | Агент пишет `.kicad_sch` **только через структурные операции** (`kicad-skip`), не печатает S-expr руками | Прямая запись S-expr агентом — основной источник битых файлов |
| D2 | Подсхема попадает в каталог только как **схема + контракт + тестбенч** | «Красивый чертёж» без проверки не переиспользуем |
| D3 | Источник правды — git; индекс — производный артефакт | Никакого второго источника правды, версии = коммиты |
| D4 | Один код гейтов для локального прогона агентом и для CI | Иначе две реализации расходятся |
| D5 | Формат артефакта блока и `report.json` — контракты всего проекта | Связывают каталог, гейты и рабочий цикл |
| D6 | Контейнер `kicad/kicad:10.0` (Debian 13, ngspice 44.2) | Официальный образ под `kicad-cli` в CI, X не нужен (`wxAppConsole`) |
| D7 | Первые ~10 блоков — обязательное ревью человеком; далее автопроверка | Калибровка контракта тестбенчей |

### Альтернативы, отвергнутые

| Альтернатива | Почему отклонена |
|---|---|
| Fork KiCad-AI-Assistant (MCP + IPC) | Требует живую GUI-сессию KiCad; DRC возвращает диалог, а не JSON; в CI хрупко |
| Прямая запись S-expr агентом | См. D1 |
| Эмбеддинги/RAG по схемам | Схема — граф, а не проза; структурный запрос закрывает 90% нужд. RAG — только для даташитов |
| Монолитные проектные шаблоны вместо каталога | Не переиспользуются, дублирование |
| Регистр (SQLite/сервис) поверх git | Два источника правды, рассинхронизация |

---

## 3. Артефакты

### 3.1 Каталог блоков

Одна папка на блок:

```
library/
  <domain>/<block-name>/
    block.kicad_sch        # подсхема, порты — global labels
    block.yaml             # интерфейс + контракт (см. 3.2)
    bench/
      testbench.kicad_sch  # возбуждение + нагрузка
      checks.spice         # .meas → машинные проверки
      expect.yaml          # ожидаемые значения и допуски
    README.md
    datasheets/            # кэш PDF/JSON по MPN (kicad-happy)
```

`<domain>` — из фиксированного списка: `power`, `mcu`, `sensor-analog`, `sensor-digital`, `motor`, `servo`, `load`, `interface`, `misc`.

### 3.2 `block.yaml` — контракт блока

```yaml
name: ldo-3v3
version: 1                    # bump при несовместимом изменении контракта
domain: power
tags: [power, ldo, 3v3, linear]
summary: "Линейный стабилизатор 3.3 В, до 500 мА"

ports:
  vin:   { dir: in,  type: power, min: 4.5, max: 5.5, unit: V }
  vout:  { dir: out, type: power, nom: 3.3, unit: V }
  gnd:   { dir: power, type: power }

limits:
  iout_max: { value: 500, unit: mA }
  vdrop_typ: { value: 0.25, unit: V }

parts:                        # для проверки BOM в будущем (v2)
  - { ref: U1, mpn: "TPS7333QPWR", role: regulator }

requires: []                  # ссылки на другие блоки
verified:
  erc: pass
  spice: pass
  rev: 3
  date: 2026-10-07
```

**Правило:** `block.yaml` обязателен. Блок без контракта в каталог не попадает.

### 3.3 `expect.yaml` — ожидания тестбенча

```yaml
analysis:
  - { type: tran, step: 1u, stop: 5m }
  - { type: dc,   start: 3.0, stop: 6.0, step: 0.1 }

checks:
  - name: vout_nom
    meas: "vout_nom"
    kind: value
    expected: 3.3
    tol_abs: 0.05
    severity: hard
  - name: load_reg
    meas: "vload_reg"
    kind: inequality
    op: "<="
    expected: 0.02
    unit: V
    severity: hard
  - name: settling
    meas: "t_settle"
    kind: inequality
    op: "<"
    expected: 1.0
    unit: ms
    severity: soft
```

`severity: hard` → блок не в каталог. `soft` → warning в отчёте, решает человек.

### 3.4 `report.json` — результат гейтов

```json
{
  "schema": "kicad-agent/report.v1",
  "project": "esp32-c6-current-servo",
  "revision": "a1b2c3d",
  "timestamp": "2026-10-07T12:00:00Z",
  "kicad_version": "10.0.6",
  "gates": {
    "parse":      { "status": "pass", "errors": [] },
    "lib-check":  { "status": "pass", "errors": [] },
    "erc":        { "status": "fail", "artifact": "reports/erc.json",
                    "summary": { "error": 2, "warning": 11, "exclusion": 0 } },
    "spice":      { "status": "pass", "artifact": "reports/sim.json",
                    "summary": { "checked": 9, "passed": 9, "failed": 0 } }
  },
  "verdict": "fail",
  "errors": [
    { "gate": "erc", "severity": "error", "type": "power_pin_not_driven",
      "message": "Input Power pin not driven by any Output Power pins",
      "items": [{ "ref": "#PWR01", "pos": { "x": 1.1938, "y": 0.9652 } }] }
  ]
}
```

`verdict` ∈ `pass | fail`. Гейт со статусом `fail` при `severity: hard` → `verdict: fail`.

### 3.5 `sim-report.json` — глубокий прогон (фаза 3)

```json
{
  "schema": "kicad-agent/sim.v1",
  "cases": [
    { "block": "ldo-3v3", "name": "vout_nom", "value": 3.298,
      "expected": 3.3, "tol": 0.05, "result": "pass" },
    { "block": "ldo-3v3", "name": "vout_hot", "value": 3.271,
      "expected": 3.3, "tol": 0.05, "result": "warn", "dev_pct": -0.88 }
  ],
  "mc": { "runs": 200, "seed": 42, "yield_pct": 100.0 },
  "verdict": "pass"
}
```

---

## 4. Гейты верификации

Порядок выполнения и уровень жёсткости:

| # | Гейт | Инструмент | Уровень |
|---|---|---|---|
| 1 | `parse` | `kicad-skip` + `kicad-happy/skills/kicad/scripts/analyze_schematic.py` | **hard** |
| 2 | `lib-check` | сверка `block.yaml` из индекса: существует, порты совпадают с использованием | **hard** |
| 3 | `erc` | `kicad-cli sch erc --format json --severity-error --severity-warning --exit-code-violations -o reports/erc.json <sch>` | **hard** по `error`, **soft** по `warning` |
| 4 | `datasheet` | `kicad-happy/skills/datasheets` — MPN существует, V/I в допуске | soft |
| 5 | `spice` | netlist → ngspice → `.meas` → assert против `expect.yaml` | **hard** |

### 4.1 Правила запуска

```bash
# 3. ERC (exit 5 при нарушениях)
kicad-cli sch erc --format json \
  --severity-error --severity-warning --exit-code-violations \
  -o reports/erc.json design.kicad_sch

# 5. SPICE
kicad-cli sch export netlist --format spice -o reports/circuit.net design.kicad_sch
ngspice -b -o reports/circuit.log reports/circuit.net
```

Перед запуском ngspice в нетлист вставляются проверки из `bench/checks.spice`
(`.dc`, `.meas`, ...) — перед последней строкой `.end`. Флаг `-r` не
используется: с ним ngspice не печатает результаты `.meas` в лог, а гейт
читает значения именно из лога.

### 4.2 Обязательная настройка ERC

`simulation_model_issue` в ERC **по умолчанию `IGNORE`**. Включаем в настройках проекта (`erc.rule_severities.simulation_model_issue = "error"`), иначе «у компонента нет SPICE-модели» проглатывается и гейт `spice` падает без внятной причины.

### 4.3 Зависимость контейнера

Образ `kicad/kicad:10.0` работает от юзера `kicad` (uid 1000) с конфигами в `/home/kicad`. Запуск с `-u $(id -u)` ломает поиск библиотек → ERC сыплет `lib_symbol_issues`. Решение: запускать от uid 1000 или монтировать `$HOME/.config/kicad` вручную.

---

## 5. Рабочий цикл агента

### 5.1 Внутреннее кольцо (секунды)

```
задача → найти блоки в index.json → собрать kicad-skip
       → ./verify → report.json → править → снова
```

### 5.2 Внешнее кольцо (минуты)

```
push feature/* → PR → GitHub Actions (те же гейты) → report.md в комментарий
              → ревью человеком → merge → index.json + CHANGELOG + vault
```

### 5.3 Публикация нового блока

1. Агент создаёт `library/<domain>/<name>/` с полным набором файлов.
2. Тестбенч **обязателен** — блок без него не принимается.
3. Регрессия всех существующих тестбенчей должна остаться зелёной.
4. Первые ~10 блоков — обязательное ревью человеком.
5. Мерж → CI пересобирает `index.json`.

---

## 6. Инфраструктура

### 6.1 Контейнер

- Базовый образ: `kicad/kicad:10.0` (Debian 13 trixie, ngspice 44.2).
- Дополнительно ставится: Python 3.12, `kicad-skip`, `kicad-happy` (vendor-копия), `pytest`.
- Точка входа: `verify` (CLI) и `python -m ...` для агентских операций.
- `LANG/LC_ALL=C.UTF-8` — уже в образе.

### 6.2 docker-compose

Сервисы:
- `verify` — гейты фазы 2 (локальный прогон агентом)
- `sim` — глубокий прогон фазы 3 (по label/вручную)
- `ci` — проксирует те же гейты для GitHub Actions

Один Dockerfile. Compose задаёт только точки входа и тома.

### 6.3 CI

GitHub Actions, один workflow с двумя job'ами:
- `gates` — гейты фазы 2 на каждый push в `feature/*` и на PR
- `deep-sim` — фаза 3, только по label `sim-deep` или перед мержем

Контейнер собирать в CI и кэшировать по хешу `Dockerfile` + `requirements.txt`.

---

## 7. Структура репозитория

```
.
├── docs/
│   ├── specs/2026-10-07-kicad-agent-pipeline-v1.md
│   └── ...
├── library/                    # каталог блоков (см. 3.1)
│   └── .gitkeep
├── pipeline/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── requirements.txt
│   └── verify/                 # CLI гейтов
├── .github/workflows/
│   └── ci.yml
├── fixtures/                   # тестовые схемы для регрессии pipeline
├── CHANGELOG.md
└── README.md
```

---

## 8. Критерии приёмки v1

1. `docker compose build` проходит без ошибок.
2. `docker compose run verify fixtures/simple-divider` возвращает `report.json` со схемой из §3.4 и `verdict: pass`.
3. Специально сломанная фикстура (разомкнутый net) даёт `verdict: fail` с `type` из ERC и ненулевым exit code.
4. Гейт `spice` на фикстуре с тестбенчем проходит; без тестбенча — `status: skip` (не fail).
5. CI на PR красится в соответствии с `verdict`.
6. Пример-блок в `library/power/` с полным контрактом принимается и индексируется.

---

## 9. Риски

| Риск | Митигация |
|---|---|
| `kicad-skip` не умеет части формата KiCad 10 | Фикстуры покрывающие используемые конструкции; при провале — фолбэк на прямую запись S-expr через шаблоны |
| `kicad-happy` меняется и ломает API | Vendor-копия в `pipeline/vendor/`, обновление точечное и ревьюится |
| ngspice не сходится на нелинейных схемах | `timeout` на каждый прогон; `strict_errorhandling`; fail → `status: fail` с логом |
| Агент генерирует тестбенч, который «проверяет сам себя» | `expect.yaml` пишется отдельно от `checks.spice`; человек сверяет на первых блоках |
| ERC-варнинги зашумляют отчёт | Разделение hard/soft; warning'и не роняют PR |

---

## 10. Вне v1 (намеренно)

- Плата: размещение, трассировка, DRC, `.kicad_dru`, импеданс, gerber.
- Роутинг: `KiCadRoutingTools` (работает с `.kicad_pcb` напрямую) — кандидат в v2.
- Эмбеддинги поверх `index.json`.
- Автономный `kicad-cli api-server` (headless IPC) — придёт с KiCad 11.
- Термический/EMC-анализ (у `kicad-happy` есть EMC — подключить в v2).
