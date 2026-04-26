import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "architecture-sync" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

HOOKS = ROOT / "hooks" / "pre-commit"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "yaml"


@pytest.fixture
def load_yaml():
    def _load(rel_path: str) -> dict:
        return yaml.safe_load((FIXTURE_ROOT / rel_path).read_text(encoding="utf-8"))
    return _load


@pytest.fixture
def fixture_path():
    def _path(rel_path: str) -> Path:
        return FIXTURE_ROOT / rel_path
    return _path
