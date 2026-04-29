"""Deterministic Mermaid generator.

Reads a SERVICE_MAP.yaml document and renders three Mermaid diagrams
(context, container, sequence) into a target directory.

CLI: generate_mermaid.py <yaml> <out_dir>.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common import JINJA_ENV, is_read_endpoint, read_yaml, slugify, write_text_atomic


def _normalize_upstream(item) -> dict:
    """Accept either a legacy string or a structured object form."""
    if isinstance(item, str):
        return {"name": item, "slug": slugify(item), "endpoints_used": []}
    obj = dict(item)
    obj.setdefault("endpoints_used", [])
    obj["slug"] = slugify(obj["name"])
    return obj


def _enrich(doc: dict) -> dict:
    deps = doc.get("dependencies", {})
    events = doc.get("events", {})
    raw_endpoints = doc.get("api", {}).get("endpoints", [])
    return {
        "service": doc["service"],
        "upstream": [_normalize_upstream(u) for u in deps.get("upstream", [])],
        "downstream_sync": [
            {**d, "slug": slugify(d["service"])} for d in deps.get("downstream", {}).get("sync", [])
        ],
        "downstream_async": [
            {**d, "slug": slugify(d["topic"])} for d in deps.get("downstream", {}).get("async", [])
        ],
        "storage": [{**s, "slug": slugify(s["name"])} for s in deps.get("storage", [])],
        "published": [{**t, "slug": slugify(t["topic"])} for t in events.get("published", [])],
        "consumed": [{**t, "slug": slugify(t["topic"])} for t in events.get("consumed", [])],
        "endpoints": [
            {
                **e,
                "is_read": is_read_endpoint(e["name"]),
                "storage_op": "read" if is_read_endpoint(e["name"]) else "write",
            }
            for e in raw_endpoints
        ],
    }


def generate_context(doc: dict) -> str:
    """Render the context (system landscape) Mermaid diagram for ``doc``."""
    return JINJA_ENV.get_template("context.mmd.j2").render(_enrich(doc))


def generate_container(doc: dict) -> str:
    """Render the container (service internals + dependencies) Mermaid diagram for ``doc``."""
    return JINJA_ENV.get_template("container.mmd.j2").render(_enrich(doc))


def generate_sequence(doc: dict) -> str:
    """Render the sequence (interaction) Mermaid diagram for ``doc``."""
    return JINJA_ENV.get_template("sequence.mmd.j2").render(_enrich(doc))


DIAGRAMS = (
    ("context.mmd", generate_context),
    ("container.mmd", generate_container),
    ("sequence.mmd", generate_sequence),
)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("yaml", type=Path, help="Path to SERVICE_MAP.yaml")
    parser.add_argument(
        "out_dir",
        type=Path,
        help="Directory where context.mmd, container.mmd, sequence.mmd will be written",
    )
    args = parser.parse_args(argv)
    doc = read_yaml(args.yaml)
    for filename, fn in DIAGRAMS:
        write_text_atomic(args.out_dir / filename, fn(doc))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
