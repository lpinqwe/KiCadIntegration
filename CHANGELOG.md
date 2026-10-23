# Changelog

Все изменения проекта. Версия определяется мержем PR; идентификатор — номер PR.

## Unreleased — PR #1 (2026-10-23)

### Added
- Requirements для verify CLI
- Verify CLI (5 гейтов), Dockerfile, docker-compose

### Changed
- Bootstrap пустого репозитория
- Убрать __pycache__ из индекса
- Воркфлоу гейтов + deep-sim по лейблу
- Пины зависимостей, кэш Docker, permissions: read, entrypoint
- Убрать глобальный HOME=/home/kicad — ломал buildx на раннере (EACCES)
- Отчёты в /tmp внутри контейнера — uid 1000 не пишет в checkout uid 1001
- Негативные кейсы spice/erc с проверкой report.json, pytest, strict для библиотеки, пины actions и digest
- HashFiles только на steps-уровне — GitHub отвергал workflow целиком

### Docs
- Спецификация v1 схематического пайплайна + исследование роутинга
- Библиотека блоков — формат и правила
- README, CHANGELOG
- README, CHANGELOG по фактическим хешам, .gitignore += .env
- CHANGELOG — фиксы по итогам ревью
- CHANGELOG — реальные хеши после пересборки истории
- CHANGELOG — фиксы фикстур и CI

### Fixed
- Замечания ревью — contract_invalid, ConfigError, DependencyError, escaping
- Фикстуры под реальный контейнер — PWR_FLAG, checks.spice инжект, ngspice без -r, путь анализатора
- Missing-power на официальных lib_symbols KiCad 10 — грузится kicad-cli

### Tests
- Три фикстуры KiCad 10 (pass/fail/no-bench)
- Pytest-набор на verify CLI (30 тестов)

