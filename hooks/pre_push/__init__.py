"""Importable mirror of hooks/pre-push for tests; runtime CLI lives at hooks/pre-push/*.py."""
import sys
from pathlib import Path

_DASH_DIR = Path(__file__).resolve().parents[1] / "pre-push"
if str(_DASH_DIR) not in sys.path:
    sys.path.insert(0, str(_DASH_DIR))

from check_contract_changes import check_contract_changes  # noqa: E402,F401
from check_drift import check_drift  # noqa: E402,F401
from run_all_pushchecks import run_all  # noqa: E402,F401
