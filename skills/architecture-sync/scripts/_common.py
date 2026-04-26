"""Shared helpers for archspec generators. Pure-functional, deterministic."""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

MANAGED_REGION_START = "<!-- archspec:managed-region:start -->"
MANAGED_REGION_END = "<!-- archspec:managed-region:end -->"

JINJA_ENV = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    lstrip_blocks=True,
    trim_blocks=True,
    autoescape=False,
    newline_sequence="\n",
)


def slugify(value: str) -> str:
    """Deterministic slug: ASCII-fold, lowercase, [^a-z0-9] -> '-', collapse, strip."""
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    lowered = folded.lower()
    replaced = re.sub(r"[^a-z0-9]+", "-", lowered)
    return replaced.strip("-")


def read_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return its top-level mapping.

    Raises ``ValueError`` if the document is not a mapping.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(
            f"{path}: expected YAML mapping at top level, got {type(data).__name__}"
        )
    return data


def write_text_atomic(path: Path, text: str) -> None:
    """Write LF-only, UTF-8, no BOM, with a single trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text = text + "\n"
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_bytes(text.encode("utf-8"))
    tmp.replace(path)


def _split_managed_region(text: str, source: str) -> tuple[str, str, str]:
    start = text.find(MANAGED_REGION_START)
    if start == -1:
        raise ValueError(f"{source}: missing {MANAGED_REGION_START}")
    end = text.find(MANAGED_REGION_END, start + len(MANAGED_REGION_START))
    if end == -1:
        raise ValueError(
            f"{source}: {MANAGED_REGION_START} present but {MANAGED_REGION_END} missing"
        )
    end_after = end + len(MANAGED_REGION_END)
    return text[:start], text[start:end_after], text[end_after:]


def apply_managed_region(target: Path, fresh_text: str) -> str:
    """Splice fresh managed region into target, preserving content outside markers.

    If ``target`` does not exist or has no start marker, returns ``fresh_text`` as-is.
    """
    if not target.exists():
        return fresh_text
    existing = target.read_text(encoding="utf-8")
    if MANAGED_REGION_START not in existing:
        return fresh_text
    before, _old_managed, after = _split_managed_region(existing, str(target))
    _, new_managed, _ = _split_managed_region(fresh_text, "fresh template")
    return before + new_managed + after
