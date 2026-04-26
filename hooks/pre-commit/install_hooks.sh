#!/usr/bin/env bash
# Install archspec pre-commit hook with a chained-runner pattern.
# Idempotent. Coexists with husky/lefthook by preserving any pre-existing hook
# under .git/hooks/pre-commit.d/05-existing.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOKS_DIR="$(git rev-parse --git-path hooks)"
PARTS_DIR="$HOOKS_DIR/pre-commit.d"
DISPATCHER="$HOOKS_DIR/pre-commit"

mkdir -p "$PARTS_DIR"

# 1. Preserve any pre-existing hook that is not already our dispatcher.
if [ -f "$DISPATCHER" ] && ! grep -q "archspec-dispatcher" "$DISPATCHER" 2>/dev/null; then
  cp "$DISPATCHER" "$PARTS_DIR/05-existing"
  chmod +x "$PARTS_DIR/05-existing"
fi

# 2. Write the dispatcher (always overwritten — its content is generated, not user-owned).
cat > "$DISPATCHER" <<'EOF'
#!/usr/bin/env bash
# archspec-dispatcher — runs every executable in .git/hooks/pre-commit.d/ in lexical order.
set -euo pipefail
PARTS="$(git rev-parse --git-path hooks)/pre-commit.d"
[ -d "$PARTS" ] || exit 0
shopt -s nullglob 2>/dev/null || true
for hook in "$PARTS"/*; do
  [ -x "$hook" ] || continue
  "$hook" || exit $?
done
EOF
chmod +x "$DISPATCHER"

# 3. Write the archspec part as 10-archspec — runs after husky/lefthook (05-existing).
cat > "$PARTS_DIR/10-archspec" <<EOF
#!/usr/bin/env bash
REPO_ROOT="\$(git rev-parse --show-toplevel)"
PYTHON="\$REPO_ROOT/.venv/bin/python"
if [ ! -x "\$PYTHON" ]; then
  PYTHON="python3"
fi
exec "\$PYTHON" "$SCRIPT_DIR/run_all_checks.py"
EOF
chmod +x "$PARTS_DIR/10-archspec"

echo "archspec: pre-commit installed at $DISPATCHER"

# 4. Install pre-push dispatcher (parallel to pre-commit pattern above).
PRE_PUSH_PARTS_DIR="$HOOKS_DIR/pre-push.d"
PRE_PUSH_DISPATCHER="$HOOKS_DIR/pre-push"
PRE_PUSH_SCRIPT_DIR="$(cd "$SCRIPT_DIR/../pre-push" && pwd)"

mkdir -p "$PRE_PUSH_PARTS_DIR"

# Preserve any pre-existing pre-push hook (mirrors pre-commit logic).
if [ -f "$PRE_PUSH_DISPATCHER" ] \
   && ! grep -q "archspec-pushdispatcher" "$PRE_PUSH_DISPATCHER" 2>/dev/null; then
  cp "$PRE_PUSH_DISPATCHER" "$PRE_PUSH_PARTS_DIR/05-existing"
  chmod +x "$PRE_PUSH_PARTS_DIR/05-existing"
fi

cat > "$PRE_PUSH_DISPATCHER" <<'EOF'
#!/usr/bin/env bash
# archspec-pushdispatcher — runs every executable in .git/hooks/pre-push.d/ in lexical order.
set -euo pipefail
PARTS="$(git rev-parse --git-path hooks)/pre-push.d"
[ -d "$PARTS" ] || exit 0
shopt -s nullglob 2>/dev/null || true
for hook in "$PARTS"/*; do
  [ -x "$hook" ] || continue
  "$hook" "$@" || exit $?
done
EOF
chmod +x "$PRE_PUSH_DISPATCHER"

cat > "$PRE_PUSH_PARTS_DIR/10-archspec" <<EOF
#!/usr/bin/env bash
REPO_ROOT="\$(git rev-parse --show-toplevel)"
PYTHON="\$REPO_ROOT/.venv/bin/python"
if [ ! -x "\$PYTHON" ]; then
  PYTHON="python3"
fi
exec "\$PYTHON" "$PRE_PUSH_SCRIPT_DIR/run_all_pushchecks.py" --base-ref "\${ARCHSPEC_BASE_REF:-origin/main}"
EOF
chmod +x "$PRE_PUSH_PARTS_DIR/10-archspec"

echo "archspec: pre-push installed at $PRE_PUSH_DISPATCHER"
