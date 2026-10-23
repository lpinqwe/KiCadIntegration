"""Общая обвязка pytest: pipeline/ на sys.path, пути к фикстурам."""

import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PIPELINE_DIR.parent
FIXTURES_DIR = REPO_ROOT / "fixtures"

sys.path.insert(0, str(PIPELINE_DIR))
