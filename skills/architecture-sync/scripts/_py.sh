#!/usr/bin/env bash
# Portable python launcher for archspec skill scripts.
#
# Works the same whether archspec runs as a Claude Code plugin, a Codex/opencode
# skill, or an `npx skills` install — it never depends on a host-specific env var.
#
# Resolution order:
#   1. $ARCHSPEC_PYTHON            — explicit override (e.g. a project venv)
#   2. $CLAUDE_PLUGIN_ROOT/.venv   — the plugin's own venv, when present
#   3. <repo>/.venv               — a venv at the current git root, when present
#   4. python3 / python           — first interpreter on PATH
#
# The interpreter must have pyyaml, jsonschema and jinja2 importable. When none of
# the venvs above supply them, install into the active python3:
#   python3 -m pip install pyyaml jsonschema jinja2
set -euo pipefail

pick_python() {
  if [ -n "${ARCHSPEC_PYTHON:-}" ] && [ -x "${ARCHSPEC_PYTHON}" ]; then
    printf '%s\n' "${ARCHSPEC_PYTHON}"; return 0
  fi
  if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -x "${CLAUDE_PLUGIN_ROOT}/.venv/bin/python" ]; then
    printf '%s\n' "${CLAUDE_PLUGIN_ROOT}/.venv/bin/python"; return 0
  fi
  local root
  root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  if [ -n "${root}" ] && [ -x "${root}/.venv/bin/python" ]; then
    printf '%s\n' "${root}/.venv/bin/python"; return 0
  fi
  if command -v python3 >/dev/null 2>&1; then printf 'python3\n'; return 0; fi
  if command -v python  >/dev/null 2>&1; then printf 'python\n';  return 0; fi
  return 1
}

if ! PY="$(pick_python)"; then
  echo "archspec: no python interpreter found (need python3 with pyyaml, jsonschema, jinja2)" >&2
  exit 127
fi

exec "${PY}" "$@"
