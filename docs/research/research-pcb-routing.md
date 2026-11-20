# Автоматизированная разводка плат в agent-пайплайне KiCad — исследовательский отчёт

Дата: 2026-10-07. Режим: research-only (изменения в коде не выполнялись).
Правила отчёта: каждое фактическое утверждение сопровождается ссылкой; непроверенные или вторичные данные помечены явно.

---

## 0. Проверенные версии (актуальность)

| Компонент | Версия | Источник |
|---|---|---|
| KiCad (последний релиз) | **10.0.6**, опубликован 2026-08-29 | https://github.com/KiCad/kicad-source-mirror/releases |
| KiCad 9 (последний релиз ветки) | **9.0.9**, опубликован 2026-05-02 | там же |
| Документация KiCad 10.0 | заявлена как «based on KiCad **10.0.7**» | https://docs.kicad.org/10.0/en/cli/cli.html |
| Freerouting | **v2.5.0**, опубликован 2026-10-05, лицензия GPL-3.0 | https://github.com/freerouting/freerouting/releases |
| KiCad 11 | в разработке (ветка `master`, релиза нет) | https://docs.kicad.org/master/en/cli/cli.html |

⚠️ **Расхождение (не подтверждено):** руководство CLI KiCad 10.0 собиралось от версии 10.0.7, но тега `10.0.7` среди релизов `KiCad/kicad-source-mirror` на 2026-10-07 нет (новейший — 10.0.6). Трактовать так: 10.0.7 — версия сборки документации/ветки, релизный «железный» потолок — 10.0.6.

---

## 1. Что умеет KiCad 9.0.9 / 10.0.6 по роутингу

### 1.1 Интерактивный роутер, глобального автороутера нет

- В описании PCB Editor (10.0) роутинг перечислен как **интерактивный**: режимы push-and-shove / walkaround / highlight collisions, поддержка разводки дифф-пар, подстройки длины и скью. Глобального (однокнопочного) автороутера в списке функций нет: https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html
- То же описание присутствует уже в ветке 9.0 (значит, поведение 9.0.9 и 10.0.6 по этому пункту совпадает): https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html
- Подробное описание интерактивного роутера (PNS), включая дифф-пары и тюнинг: https://github.com/KiCad/kicad-doc/blob/master/src/pcbnew/pcbnew_interactive_router.adoc

### 1.2 Tuning Profiles (новое в KiCad 10)

- Профили тюнинга задают **per-layer** ширину дорожки и gap для дифф-пар, ширина/gap **автоматически считаются из стека платы и целевого импеданса**; профиль назначается на netclass колонкой **Tuning Profile**, после чего интерактивный роутер использует эти значения: https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html#board-setup-tuning-profiles
- DRC может выдавать нарушение «Tuning profile track geometries» (уровни Warning/Error, включается в Violation Severities) и `missing_tuning_profile`: https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html#list-of-drc-checks
- Наличие ключей подтверждено по исходникам: `tuning_profile_track_geometries`, `missing_tuning_profile`, `net_chain_tuning_profiles`: https://github.com/KiCad/kicad-source-mirror/blob/master/pcbnew/drc/drc_item.cpp

### 1.3 Time-domain тюнинг (новое в KiCad 10)

- Полная переработка тюнинга (James Jackson): расчёты длины между роутером, статусбаром, Net Inspector и DRC унифицированы; добавлены **time-domain constraints** (задержка распространения, а не только длина) и Tuning Profiles per-layer: https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/
- Подробности: задержки propagation считаются вручную (по данным стека), «Pad-to-die delay» у pad'ов, многострочный Net Inspector, единый расчёт через-в-слоя (via height): https://forum.kicad.info/t/post-v10-new-features-and-development-news/66611
- В 9.0 time-domain тюнинга нет — это эксклюзив 10.x.

### 1.4 Пользовательские правила DRC (`.kicad_dru`)

- Правила живут в отдельном файле формата s-expression (не в самом `.kicad_pcb`), редактируются в Board Setup → Custom Rules, есть кнопка «Check rule syntax» (**только GUI**): https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html#custom-design-rules
- Ограничения, подтверждённые документацией: `length`, `skew`, `diff_pair_gap`, `diff_pair_uncoupled`, `track_width`, `clearance`, `via_diameter`, `annular_width`, `creepage` (правило для высокого напряжения, пример `(constraint creepage (min 5mm))`): https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html#custom-design-rules
- Функция `fromTo('<from_pad>','<to_pad>')` комбинируется с `length`/`skew` — адресация по конкретным pad'ам `RefDes-PadNumber`, допускаются `*`/`?`: https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html#drc-rule-editor-constraint-reference

### 1.5 Ключи нарушений DRC (сверено с исходником `master`)

Из `pcbnew/drc/drc_item.cpp` извлечены строки-идентификаторы, в том числе:
`length_out_of_range`, `skew_out_of_range`, `diff_pair_gap_out_of_range`, `diff_pair_uncoupled_length_too_long`, `track_width`, `via_diameter`, `annular_width`, `too_many_vias`, `creepage`, `tuning_profile_track_geometries`, `missing_tuning_profile`, `net_chain_tuning_profiles`, `tracks_crossing`, `track_angle`, `track_segment_length`, `unconnected_items`.
Источник: https://github.com/KiCad/kicad-source-mirror/blob/master/pcbnew/drc/drc_item.cpp
(Те же ключи фигурируют в разделе «List of DRC checks» руководства 10.0: https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html#list-of-drc-checks)

### 1.6 Чего НЕТ (важно для CI)

- **`kicad-cli pcb route` не существует.** Полный список подкоманд `kicad-cli pcb` в 10.0: `drc`, `export`, `import`, `render`, `upgrade` — https://docs.kicad.org/10.0/en/cli/cli.html. То же в `master` (11.x): https://docs.kicad.org/master/en/cli/cli.html
- **Экспорт Specctra DSN и импорт SES — только через GUI**: File → Export → Specctra DSN…, File → Import → Specctra Session…, шаги описаны в руководстве: https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html#specctra-session-import. То же подтверждает документация Freerouting («Current KiCad releases exchange Specctra files from the File menu»): https://freerouting.org/freerouting/using-with-kicad
  → Следствие: «DSN → autorouter → SES» в чистом headless-цикле на KiCad 10 невозможен без GUI-шага либо без стороннего инструмента, который пишет/читает `.kicad_pcb` напрямую (см. §2.6).
- **Официального AI/ML-роутера в KiCad 10 не обнаружено.** На форуме KiCad интеграция AI обсуждалась и была отклонена разработчиками (недостаток времени, стоимость LLM-инфраструктуры); рекомендация сообщества — внешние скрипты/плагины: https://forum.kicad.info/t/kicad-ai-integration-artificial-intelligence/53078
- ⚠️ **Не подтверждено:** наличие некоего «kicad_ai» или AI-фичи в официальных релизах KiCad — в ходе исследования не найдено ни в блоге 10.0.0, ни в changelog, ни в CLI-доках.

### 1.7 Прочее полезное в 10.0

- Проверка **creepage** (для высоких напряжений) как constraint custom rules: https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html#custom-design-rules
- Сетевые классы: колонка Tuning Profile, агрегация нескольких netclass по приоритету, «Import colors from schematic»: https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html

---

## 2. Freerouting и альтернативные роутеры

### 2.1 Freerouting (базовый кандидат)

| Параметр | Значение | Источник |
|---|---|---|
| Репозиторий / лицензия | https://github.com/freerouting/freerouting, **GPL-3.0** | страница репо |
| Актуальный релиз | **v2.5.0** (2026-10-05), до этого 2.4.1 (2026-09-03), 2.3.0 (2026-08-07) | https://github.com/freerouting/freerouting/releases |
| CLI | `-de in.dsn[+ses+rules]`, `-do out.ses/dsn/scr`, `-da` (откл. аналитика), `-inc GND,VCC` (пропустить netclass), `-dr rules`, `-drc report.json` | https://github.com/freerouting/freerouting/blob/master/docs/command_line_arguments.md |
| Отчёт DRC | ключ `-drc` пишет отчёт **в формате JSON-схемы DRC KiCad** — удобно для CI-диффа | там же |
| Алгоритм (с 2.0.1) | A*-волна по «rooms/doors/drills», rip-up-and-retry, оптимизатор ≤40 проходов, финальная чистка (straighten/chamfer/pull-tight) | https://freerouting.org/freerouting/autorouter-algorithm |
| Интеграция с KiCad | PCM-плагин (Tools → External Plugins), либо ручной DSN/SES обмен | https://github.com/freerouting/freerouting/blob/master/docs/integrations.md |
| IPC/JSON-мост с KiCad | PR «Add KiCad IPC API support (alpha)» — дуальный режим IPC + fallback на DSN | https://github.com/freerouting/freerouting/pull/705 |

### 2.2 Качество: что заявлено

- **Вендорские бенчмарки** (сайт freerouting.app, автор — Andras Fuchs): 1157 «реальных» плат; v2.5.0: 74.8% полностью чистых по DRC, 75% полностью разведанных; «Tier A» — 99.6% чистых; у 1.9.0 было 35.9% чистых.
  ⚠️ Источник: https://www.freerouting.app/benchmarks.html — **данные издателя, нами не независимо проверены**.
- **Официальная инфраструктура бенчмарков в репозитории** (скрипты, DRC-scoring, Markdown/HTML-отчёты, quality_score): https://github.com/freerouting/freerouting/commit/94be35190642f9ead3266292bbb8176441ce8b51
- ⚠️ **Пробел:** независимого практического обзора качества Freerouting именно по USB/DDR-платам (2 vs 4 vs 6 слоёв) в этой сессии не найдено.

### 2.3 Главное ограничение Freerouting для high-speed

- **Активной подстройки длины (меандров) у Freerouting нет**: в docs явно «This software has no good support for routing nets with minimal lengths» + есть только окно отчёта Length Violations: https://freerouting.org/freerouting/manual/routing-options
- Фича «Adding Length Tuning» (серпантин/accordion/trombone + фазовый мэтчинг дифф-пар) — **только proposal** в issue #716, не реализация: https://github.com/freerouting/freerouting/issues/716
  → Вывод для пайплайна: после Freerouting длину/скью всё равно тюнят в KiCad (или сторонним инструментом, §2.6).

### 2.4 fastroute (альтернатива без JVM)

- Open-source роутер: Specctra DSN → SES, параллельные проходы, длина, **контроль импеданса из стека платы**, дифф-пары (в том числе intra-pair skew), импорт правил `diff_pair_gap` из KiCad: https://fastroute.baltavista.com/
- Заявления сайта: 4–5× быстрее Freerouting на 20 бенч-платах (2102 s → 420 s), 20–300 МБ RAM вместо 1–2 ГБ, «0 unrouted / 0 DRC errors» на плате STM32H7 4 слоя 158 nets; на демо-платах KiCad plugin даёт 0/0 там, где «Plain Freerouting flow» даёт 160 unrouted.
  ⚠️ **Заявления разработчика, нами не проверены:** https://fastroute.baltavista.com/

### 2.5 KiCadRoutingTools (самый интересный для agent-пайплайна)

- Репозиторий: https://github.com/drandyhaas/KiCadRoutingTools — **MIT**, язык Python + Rust-ядро, **508★**, последний push 2026-10-07 (т.е. проект живой), заявленная совместимость **«KiCad 9 and KiCad 10»**, есть и GUI-плагин, и **CLI**.
- Ключевые возможности (из README): A*-роутинг с rip-up/reroute; **дифф-пары** (pose-based A*, автополярность, GND return-via, per-layer impedance-controlled ширины); **length matching** «trombone meanders + авто-группировка DQ/DQS»; **time matching** (microstrip vs stripline задержки); шинная разводка; plane pours; **«KiCad-oracle reconnect»** — доразводит именно те связи, которые DRC KiCad пометил как unconnected; чекеры DRC/connectivity/orphan-stubs.
  Источник: https://github.com/drandyhaas/KiCadRoutingTools (раздел Features)
- Документация length/time matching (tolerance в мм и ps, `--diff-pair-intra-match`, via-barrel aware): https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/length-matching.md
- CLI-пример: `python py_router/route.py input.kicad_pcb output.kicad_pcb --nets "…"` — работает **напрямую с `.kicad_pcb`**, без DSN-этапа (обход GUI-ограничения §1.6): https://github.com/drandyhaas/KiCadRoutingTools#command-line-interface
- Ограничения (из README): нет push-and-shove, нет blind/buried via, нет правил «по области»: https://github.com/drandyhaas/KiCadRoutingTools#limitations
- Встроенный **AI tab / claude-skills** — планирование routing-workflow агентом: https://github.com/drandyhaas/KiCadRoutingTools (раздел Features → AI assistance)
  ⚠️ Метрики (A/B-баттчи на корпусе открытых плат, ~600 тестов) приводит сам проект.

### 2.6 Прочее

- ⚠️ **Не подтверждено первичным репозиторием:** «freeroute» — нативный Python-клон движка FreeRouting без JVM (найдено только зеркало `warehack.ing/freeroute` / git.supported.systems, помечено как alpha, «не на уровне плотности JAR на плотных платах»): https://git.supported.systems/warehack.ing/freeroute/src/commit/fd3bee108526a20ea04288a59a904adab7ffd36f/CLAUDE.md
- ⚠️ **Не подтверждено официальной документацией CLI:** статья CSDN упоминает флаги `--router.differential_pairs.enabled=true` / `max_separation` — в официальном `docs/command_line_arguments.md` их нет: https://blog.csdn.net/gitblog_00097/article/details/161131496

---

## 3. Высокоскоростные интерфейсы: что реально требуется

### 3.1 USB 2.0 / 3.x (проверенные спецификации и прикладные гайды)

| Параметр | Значение | Источник |
|---|---|---|
| USB2 дифф. импеданс | **90 Ω ±15%**; одиночный — 45 Ω ±15% | TI SLLA414: https://www.ti.com/lit/an/slla414a/slla414a.pdf |
| USB2 AC-конденсаторы | не требуются | там же |
| USB3 дифф. импеданс | 90 Ω ±15%, AC-конденсаторы **на TX**, макс. длина канала 3 м | там же |
| USB3 intra-pair skew | **≤ 15 ps/m** (TI рекомендует укладываться в ~5 mil) | там же |
| USB2 рассинхрон пары | расхождение длины D+/D− **≤ 0.150" (3.81 мм)** | https://www.digikey.com/en/maker/projects/how-to-route-differential-pairs-in-kicad-for-usb/45b99011f5d34879ae1831dce1f13e93 |
| Топология | маршрут над **неразрывной** землёй, без 90°, без стабов | там же |

### 3.2 Геометрия под импеданс (реальные цифры для стеков)

- Стек **JLC04161H-7628** (JLCPCB): 90 Ω дифф → ширина **0.2332 мм**, gap **0.15 мм**; 50 Ω SE → **0.3244 мм**: https://docs.jitx.com/en/latest/jitxlib/jitxlib.jlcpcb.JLC04161H_7628.html
- Онлайн-калькулятор JLCPCB (подбор ширины/gap под целевой импеданс): https://jlcpcb.com/help/article/user-guide-to-the-jlcpcb-impedance-calculator
- Независимая перекрёстная сверка (спека 90 Ω, ~0.23 мм ширина / ~0.14 мм gap): https://electronics.stackexchange.com/questions/540263/routing-usb-3-x-type-c-signals ⚠️ ссылка отдаёт 403 автоматам, в браузере доступна.
- ⚠️ **Практический вывод для 2-слойных плат:** на 2-слойной 1.6 мм плате для 90 Ω нужны дорожки порядка **0.77 мм** при gap 0.15 мм — то есть разводка становится нереалистичной; автор гайда прямо указывает, что 4+ слоя с тонким диэлектриком предпочтительнее: https://www.digikey.com/en/maker/projects/how-to-route-differential-pairs-in-kicad-for-usb/45b99011f5d34879ae1831dce1f13e93
- Встроенный **TransLine-калькулятор KiCad** (Tools → Calculator Tools → TransLine, включая Coupled Microstrip) — **только GUI, в `kicad-cli` отсутствует**: https://docs.kicad.org/10.0/en/pcb_calculator/pcb_calculator.html

### 3.3 DDR (официальные guideline'и)

- **Intel, DDR4 Layout Design Guidelines**: данные (DQ/DM/DQS) — на одном слое/верхних слоях, минимальный Z-переход, без маршрутизации поверх разрезов/воздухов в референсе, back-drill/минимальные стабы, отдельные правила для differential clock, skew-matching «right after FPGA»: https://www.intel.com/content/www/us/en/docs/programmable/817467/24-1-6-1-0/ddr4-general-design-considerations.html
- **JEDEC DDR4 UDIMM Design Specification Rev 1.10**: fly-by топология; ADD/CMD/CTRL ↔ CK матчится до **±0.5 мм**; стаб TL2 ≤ **3.0 мм** и матчинг стабов ±1.5 мм; внутри байт-лейны DQ/DQS — до **±1.0 мм** (компенсированная длина); velocity compensation 1.1 (microstrip → stripline equivalent); компенсация через-в-диэлектрике: https://www.jedec.org/sites/default/files/docs/4_20_26R25A.pdf ⚠️ PDF отдаёт 403 автоматам (анти-бот), открывается в браузере.
- **NXP AN5097** (чек-лист DDR4: порядок маршрутизации Data → Addr/Cmd → Control → Clocks → Power, дистанции до края референса 30–40 mil, via count одинаков в байте, опции 40 Ω SE vs 48–50 Ω): https://docslib.org/doc/2836471/an5097-hardware-and-layout-design-considerations-for-ddr4 ⚠️ это зеркало первичного AN (сам PDF на nxp.com в этой сессии не открылся — прямая ссылка не подтверждена).
- ⚠️ Ссылки на **Micron TN-40-40 / TN-46-14** в этой сессии не подтвердились (micron.com отдаёт 404, зеркала блокируют ботов) — цифры (±50 mil внутри группы данных, ±20 mil CK↔CK#, ±500 mil CK↔DQS, ≤800 mil между длинными/короткими шинами) цитировались из найденного PDF, но **URL не верифицирован**.
- ⚠️ **LVDS: не исследовалось в этой сессии** — фактов со ссылками нет.

### 3.4 Что из этого следует для автоматизации

- Авто-роутеры (Freerouting, fastroute, KiCadRoutingTools) закрывают **топологию, клиренсы, через-в-слой, дифф-пары как пару**. Точечные требования (миллиметры/пикосекунды матчинга, fly-by, AC-конды, терминирование, back-drill, «одинаковый via count в байте») остаются **инженерными правилами проекта** — их нужно кодировать в `.kicad_dru` + netclass + tuning profiles и проверять DRC-ом в CI (см. §4).
- KiCad 10 частично закрывает это сам: tuning profiles (ширина/gap из стека) + time-domain constraints + `length`/`skew`/`diff_pair_gap`/`diff_pair_uncoupled`/`creepage` правила (§1.2–§1.5).

---

## 4. Headless-верификация в CI (что доступно из консоли)

### 4.1 DRC как CI-гейт

`kicad-cli pcb drc` (10.0) поддерживает:
`--format report|json`, `--severity-all/error/warning/exclusions`, **`--exit-code-violations`** (ненулевой код выхода при нарушениях — готовый «fail the build»), `--schematic-parity`, `--all-track-errors`, `--units mm|in|mils`, `--refill-zones`, `--save-board`, `-D KEY=VALUE`.
Источник: https://docs.kicad.org/10.0/en/cli/cli.html
Ключи нарушений (length/skew/diff pair/creepage/tuning) — §1.5.

### 4.2 Артефакты

`kicad-cli pcb export` (10.0): gerbers, drill, IPC-2581, IPC-D-356, ODB++, GenCAD, position file, statistics, STEP/GLB/STL/VRML, PDF/SVG/PS/DXF/HPGL; плюс `kicad-cli pcb render` (растровый рендер): https://docs.kicad.org/10.0/en/cli/cli.html
Пары `sch erc` + `pcb drc --schematic-parity` дают связку «схема ↔ плата» в CI.

### 4.3 Верификация вне KiCad

- **Freerouting `-drc report.json`** → отчёт в схеме JSON DRC KiCad, удобно для сравнения «до/после»: https://github.com/freerouting/freerouting/blob/master/docs/command_line_arguments.md
- **gerbonara** — Python-библиотека + CLI для чтения/правки/рендера Gerber, Excellon, IPC-356; лицензия **Apache-2.0**, Python ≥3.12, тестовый корпус включает файлы из KiCad/Altium/Eagle/Allegro/…: https://github.com/jaseg/gerbonara , https://pypi.org/project/gerbonara/ , https://gerbolyze.gitlab.io/gerbonara
- **pcb-tools** — фактически unmaintained (README прямо: «currently without a maintainer», смотрите альтернативы): https://github.com/curtacircuitos/pcb-tools
- **Импеданс-проверка отдельно от KiCad:**
  - `pcb-toolkit` (Rust, CLI, `--json`): `impedance microstrip|stripline`, `differential` (5 топологий): https://github.com/akiselev/pcb-toolkit
  - `lineforge` (pip, CLI + MCP, closed-form IPC-2141A/Cohn/Wen/Wadell + FD-solver для произвольных сечений; заявлена сверка с openEMS ±2%): https://github.com/rfingadam/lineforge
  - `RF2DFieldSolver` (GPLv3, 2D field solver): https://github.com/jankae/RF2DFieldSolver — в README есть полезная таблица расхождений калькуляторов (микрострип ~53.5…58.3 Ω у разных инструментов при одних же входах, «для дифф-пар и копланарки разброс ещё больше»).

### 4.4 Граница «headless» по версиям

- **KiCad 9 и 10: IPC API работает только через GUI-сессию** (named pipe / unix socket + `kicad-python`), headless-сервера в CLI нет. Источник (карта возможностей): https://github.com/belaszalontai/kipilot-mcp/blob/main/.github/kicad-api-capabilities.md
- **В `master` (KiCad 11, не выпущен)** уже есть подкоманда **`kicad-cli api-server`** — «runs the KiCad IPC API server in headless mode», плюс `kicad-cli gerber diff|info|convert`: https://docs.kicad.org/master/en/cli/cli.html
  → Для CI на 10.0.6 это пока недоступно; headless-автоматизация через IPC придёт с 11.x.
- ⚠️ **Не проверяли на практике:** поведение `kicad-cli pcb drc` при синтаксической ошибке в `.kicad_dru` (в GUI есть кнопка «Check rule syntax», в headless — неизвестно, падает ли DRC явно).

---

## 5. LLM/агентный prior art (что уже сделано)

| Проект | Что делает | Статус/источник |
|---|---|---|
| **PCBWorld** (LGAI-Research) | Бенчмарк PCB-задач для LLM+RL-агентов: ~58 Python API, цикл с DRC-обратной связью, сравнение моделей | arXiv: https://arxiv.org/abs/2607.05915 , репо: https://github.com/LGAI-Research/PCBWorld |
| **KiCadRoutingTools** | Не «LLM-роутер», но **CLI-роутер с AI-вкладкой/claude-skills** для планирования workflow + length/time matching (§2.5) | https://github.com/drandyhaas/KiCadRoutingTools |
| **kicad-mcp** (Gato513) | Полный цикл: placement → zones → **Freerouting headless** → DRC → export; по описанию автора: прошло валидацию на плате 63 footprints / 48 nets / 2 слоя, **упёрлось на 437 footprints (HackRF)** | https://github.com/Gato513/kicad-mcp ; упоминание DSN/ограничений: https://glama.ai/mcp/servers/antonmadto/kicad-mcp/tools/autoroute_board |
| **KiPilot MCP** (belaszalontai) | MCP поверх **официального IPC KiCad 10.x** (`kicad-python`): чтение платы, guarded-мутации (tracks/vias/zones/refill/save), 135 tools (v0.3.0); scope — GUI-сессия, headless отложен до 11.x | https://github.com/belaszalontai/kipilot-mcp , https://kipilot.org , анонс: https://forum.kicad.info/t/kipilot-mcp-server-has-been-released-for-kicad-10-x-pcb-workflows/69049 |
| **mcp-pcb-emcopilot** (Yverr0y) | 93 инструмента ревью: EMC, SI, PI, thermal, DFM; входы KiCad / ODB++ / Gerber / IPC-2581 / Altium / STEP | https://github.com/Yverr0y/mcp-pcb-emcopilot |
| **lineforge MCP** | Импеданс-солвер как MCP-инструмент (для «агент считает геометрию дорожек») | https://github.com/rfingadam/lineforge |
| **DeepPCB vs «GPT-6 Astra»** | Коммерческое сравнение: LLM-роутер разводит плату, но USB-пару «ломает» на 4 via против 0 у специализированного роутера; вывод автора — связка «LLM задаёт ограничения → роутер кладёт медь» | https://deeppcb.ai/usb-differential-pair-routing-comparison/ ⚠️ **вендорский блог** |
| **Официальный AI в KiCad** | — | **не обнаружен**; см. §1.6 (форум: идея отклонена) |

---

## 6. Явные пробелы и неподтверждённые утверждения (сводка)

1. **10.0.7 vs 10.0.6** — документация 10.0 собрана от 10.0.7, тега релиза нет (§0).
2. **Цифры качества** freerouting.app/benchmarks, fastroute.baltavista.com, DeepPCB/Astra — данные издателей, не проверены независимо (§2.2, §2.4, §5).
3. **Независимый обзор качества Freerouting именно по USB/DDR-платам** — не найден (§2.2).
4. **LVDS** — не исследовалось (§3.3).
5. **Micron TN-40-40 / TN-46-14** — содержание найдено, но первичный URL не верифицирован; NXP AN5097 — только зеркало (§3.3).
6. **Флаги `--router.differential_pairs.*`** — только из вторичной статьи, в официальной CLI-доке Freerouting отсутствуют (§2.6).
7. **`kicad_ai` / встроенный AI-роутер KiCad** — не найден ни в 9.0.9, ни в 10.0.6 (§1.6).
8. **`kicad-cli pcb route`** — отсутствует; DSN/SES — только GUI; headless IPC (`kicad-cli api-server`) — только в master/11.x (§1.6, §4.4).
9. **Поведение DRC в headless при ошибке в `.kicad_dru`** — не проверялось (§4.4).
10. **«freeroute» (Python-клон)** — найдено только зеркало, первичный репозиторий и статус не подтверждены (§2.6).
11. Источники StackExchange и JEDEC отдают 403 автоматам, но открываются в браузере (§3.1, §3.3).

---

## 7. Итоговая таблица: инструменты для agent-пайплайна

| Задача | Инструмент | Головной запуск? | Источник |
|---|---|---|---|
| DRC-гейт в CI | `kicad-cli pcb drc --format json --exit-code-violations` | да | https://docs.kicad.org/10.0/en/cli/cli.html |
| Экспорт артефактов | `kicad-cli pcb export …`, `pcb render` | да | там же |
| Правила (длина/скью/импеданс/creepage) | `.kicad_dru` + netclass + tuning profile | применяются DRC; синтаксис-редактор GUI | https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html#custom-design-rules |
| Автороутер (без GUI-шага) | **KiCadRoutingTools CLI** (пишет `.kicad_pcb` напрямую) | да (Python + Rust wheel) | https://github.com/drandyhaas/KiCadRoutingTools |
| Автороутер (классика) | Freerouting v2.5.0 CLI (`-de/-do/-drc`) | да, но DSN/SES-мост делается в GUI KiCad | https://github.com/freerouting/freerouting/blob/master/docs/command_line_arguments.md |
| Длина/скью после автороутера | KiCad tuning tools (GUI) или KiCadRoutingTools `--length-match-*` | смешано | §1.1, §2.5 |
| Импеданс-чек | pcb-toolkit / lineforge / RF2DFieldSolver | да | §4.3 |
| Gerber-чек | gerbonara | да | §4.3 |
| Слой «агент общается с KiCad» | KiPilot MCP (GUI IPC, KiCad 10) / `kicad-cli api-server` (11.x) | только GUI (10) | https://github.com/belaszalontai/kipilot-mcp , https://docs.kicad.org/master/en/cli/cli.html |
