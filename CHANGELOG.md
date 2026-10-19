# Changelog

## Unreleased

- `5e89631` fix: missing-power на официальных lib_symbols KiCad 10 — грузится kicad-cli
- `f966f70` fix: фикстуры под реальный контейнер — PWR_FLAG, checks.spice инжект, ngspice без -r, путь анализатора
- `4743839` ci: отчёты в /tmp внутри контейнера — uid 1000 не пишет в checkout uid 1001
- `4718721` ci: убрать глобальный HOME=/home/kicad — ломал buildx на раннере (EACCES)
- `b20677b` docs: CHANGELOG — реальные хеши после пересборки истории
- `e59b103` docs: CHANGELOG — фиксы по итогам ревью
- `2d5f30f` docs: README, CHANGELOG по фактическим хешам, .gitignore += .env
- `3b0ee6f` ci: пины зависимостей, кэш Docker, permissions: read, entrypoint
- `1297249` test: pytest-набор на verify CLI (30 тестов)
- `9eb0720` fix: замечания ревью — contract_invalid, ConfigError, DependencyError, escaping
- `9e41f54` ci: воркфлоу гейтов + deep-sim по лейблу
- `06581f6` docs: README, CHANGELOG
- `696a95f` docs: библиотека блоков — формат и правила
- `906686d` test: три фикстуры KiCad 10 (pass/fail/no-bench)
- `2f51aa5` chore: убрать __pycache__ из индекса
- `685a9c0` feat: verify CLI (5 гейтов), Dockerfile, docker-compose
- `c559e7d` feat: requirements для verify CLI
- `5c84331` docs: спецификация v1 схематического пайплайна + исследование роутинга
