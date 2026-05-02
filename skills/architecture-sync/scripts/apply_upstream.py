"""Deterministically merge reverse-scan consumers into a SERVICE_MAP.yaml.

Reads ``<service-yaml>`` and a reverse-scan JSON (output of
``scan_go.py --reverse-scan``), merges discovered consumers into
``dependencies.upstream[]``, and either prints a unified diff (default)
or rewrites the file in place (``--write``).

Merge rules (per consumer entry, keyed by ``name``):
  * Bare-string upstream entry (``- foo``) is upgraded to the structured form.
  * Existing structured entry with ``discovered_via: manual`` is preserved
    as manual; only ``endpoints_used`` is union-merged with scan results.
  * Existing structured entry with non-manual provenance gets its scan-derived
    fields refreshed (``protocol``, ``endpoints_used``, ``confidence``).
  * Unseen consumer is appended as a new structured entry.

Existing surrounding YAML (other sections, comments, quoting style) is
preserved verbatim — the script edits only the ``dependencies.upstream``
block.

CLI:
  apply_upstream.py <service-yaml> --reverse-scan-json <path>
                    [--write] [--protocol-filter PROTOCOL]
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

_DISCOVERED_VIA_MANUAL = "manual"
_DISCOVERED_VIA_SCAN = "monorepo-scan"
_UPSTREAM_KEY_ORDER = (
    "name",
    "protocol",
    "endpoints_used",
    "discovered_via",
    "confidence",
    "source",
)


def _load_existing_upstream(yaml_path: Path) -> list[Any]:
    doc = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    deps = (doc.get("dependencies") or {}) if isinstance(doc, dict) else {}
    raw = deps.get("upstream") or []
    return raw if isinstance(raw, list) else []


def _normalize_to_dict(entry: Any) -> dict[str, Any]:
    if isinstance(entry, str):
        return {"name": entry}
    if isinstance(entry, dict) and entry.get("name"):
        return {k: v for k, v in entry.items() if v is not None}
    raise ValueError(f"unrecognised upstream entry: {entry!r}")


def merge_upstream(
    existing: list[Any], scan_consumers: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge scan consumers into existing upstream list, returning structured dicts.

    Output ordering: existing entries first (in source order), then any new
    consumers (sorted by name) — keeps diffs minimal for users.
    """
    by_name: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw in existing:
        entry = _normalize_to_dict(raw)
        name = entry["name"]
        if name in by_name:
            continue
        by_name[name] = entry
        order.append(name)

    for consumer in scan_consumers:
        name = consumer.get("name")
        if not name:
            continue
        scan_endpoints = list(consumer.get("endpoints_used") or [])
        if name not in by_name:
            new_entry: dict[str, Any] = {"name": name}
            if consumer.get("protocol"):
                new_entry["protocol"] = consumer["protocol"]
            if scan_endpoints:
                new_entry["endpoints_used"] = sorted(set(scan_endpoints))
            new_entry["discovered_via"] = _DISCOVERED_VIA_SCAN
            by_name[name] = new_entry
            order.append(name)
            continue

        existing_entry = by_name[name]
        is_manual = existing_entry.get("discovered_via") == _DISCOVERED_VIA_MANUAL
        if scan_endpoints:
            current_endpoints = set(existing_entry.get("endpoints_used") or [])
            existing_entry["endpoints_used"] = sorted(current_endpoints | set(scan_endpoints))
        if not is_manual:
            if consumer.get("protocol") and not existing_entry.get("protocol"):
                existing_entry["protocol"] = consumer["protocol"]
            if "discovered_via" not in existing_entry:
                existing_entry["discovered_via"] = _DISCOVERED_VIA_SCAN

    return [by_name[n] for n in order]


def render_upstream_block(items: list[dict[str, Any]]) -> str:
    """Render the upstream list as a YAML fragment.

    Format matches what archspec init currently produces: 2-space indent for
    the ``upstream:`` key (under ``dependencies:``), 4-space indent for list
    items, 6-space indent for nested lists like ``endpoints_used``.
    """
    if not items:
        return "  upstream: []\n"
    lines = ["  upstream:"]
    for entry in items:
        keys = [k for k in _UPSTREAM_KEY_ORDER if k in entry] + [
            k for k in entry if k not in _UPSTREAM_KEY_ORDER
        ]
        first = True
        for key in keys:
            value = entry[key]
            prefix = "    - " if first else "      "
            first = False
            if isinstance(value, list):
                lines.append(f"{prefix}{key}:")
                for item in value:
                    lines.append(f"        - {item}")
            else:
                lines.append(f"{prefix}{key}: {value}")
    return "\n".join(lines) + "\n"


def replace_upstream_block(text: str, new_block: str) -> str:
    """Splice ``new_block`` in place of the existing ``dependencies.upstream`` block.

    Surgical text edit — preserves quoting, blank lines, and unrelated keys.
    Raises ``ValueError`` if the document does not contain
    ``dependencies:\\n  upstream: ...``.
    """
    lines = text.splitlines(keepends=True)
    deps_idx = next(
        (i for i, line in enumerate(lines) if line.startswith("dependencies:")),
        None,
    )
    if deps_idx is None:
        raise ValueError("dependencies: top-level key not found")

    deps_end = len(lines)
    for i in range(deps_idx + 1, len(lines)):
        line = lines[i]
        if line and not line.startswith((" ", "\t", "\n", "#")):
            deps_end = i
            break

    upstream_idx: int | None = None
    for i in range(deps_idx + 1, deps_end):
        if lines[i].startswith("  upstream:"):
            upstream_idx = i
            break
    if upstream_idx is None:
        raise ValueError("dependencies.upstream key not found")

    upstream_end = deps_end
    for i in range(upstream_idx + 1, deps_end):
        line = lines[i]
        if line.startswith("  ") and not line.startswith("   "):
            stripped = line[2:]
            if stripped and stripped[0].isalpha() and ":" in stripped:
                upstream_end = i
                break

    return "".join(lines[:upstream_idx]) + new_block + "".join(lines[upstream_end:])


def _filter_consumers(
    consumers: list[dict[str, Any]], protocol: str | None
) -> list[dict[str, Any]]:
    if not protocol:
        return consumers
    return [c for c in consumers if c.get("protocol") == protocol]


def _print_diff(old: str, new: str, label: str) -> None:
    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{label}",
        tofile=f"b/{label}",
    )
    sys.stdout.writelines(diff)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Merge reverse-scan consumers into upstream[]")
    parser.add_argument("yaml_path", type=Path, help="Path to SERVICE_MAP.yaml")
    parser.add_argument(
        "--reverse-scan-json",
        type=Path,
        required=True,
        help="Path to reverse-scan JSON (scan_go.py --reverse-scan output)",
    )
    parser.add_argument("--write", action="store_true", help="Apply changes in place")
    parser.add_argument(
        "--protocol-filter",
        default=None,
        help="Only merge consumers whose protocol matches (e.g. gRPC)",
    )
    args = parser.parse_args(argv)

    if not args.yaml_path.is_file():
        print(f"error: file not found: {args.yaml_path}", file=sys.stderr)
        return 2
    if not args.reverse_scan_json.is_file():
        print(f"error: file not found: {args.reverse_scan_json}", file=sys.stderr)
        return 2

    try:
        scan = json.loads(args.reverse_scan_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON in {args.reverse_scan_json}: {e}", file=sys.stderr)
        return 2

    consumers = _filter_consumers(scan.get("consumers") or [], args.protocol_filter)
    existing = _load_existing_upstream(args.yaml_path)

    try:
        merged = merge_upstream(existing, consumers)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    new_block = render_upstream_block(merged)
    old_text = args.yaml_path.read_text(encoding="utf-8")
    try:
        new_text = replace_upstream_block(old_text, new_block)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if old_text == new_text:
        if not args.write:
            print(f"# {args.yaml_path}: no changes")
        return 0

    if args.write:
        args.yaml_path.write_text(new_text, encoding="utf-8")
        return 0

    _print_diff(old_text, new_text, str(args.yaml_path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
