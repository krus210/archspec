# Contributing

Contributions are welcome, especially linters for new languages under
`linters/<lang>/`.

## One-time setup

The project uses a local virtualenv at `.venv/` so commands work the same
on every machine regardless of system `python` / `pip`:

```bash
make bootstrap     # python3 -m venv .venv + pip install -r requirements-dev.txt
```

Requires `python3 >= 3.11` and `go >= 1.23` on PATH.

## Before opening a PR

Run the local checks:

```bash
.venv/bin/ruff check .
make test                  # pytest + go test
make benchmarks            # ./benchmarks/run.sh
```

If the change edits `SERVICE_MAP.yaml`, regenerate derived docs before
committing (the launcher picks `.venv/bin/python` automatically and falls
back to system `python3`):

```bash
bin/archspec-python skills/architecture-sync/scripts/sync.py docs/SERVICE_MAP.yaml docs
```

## Releasing a new version

archspec follows [SemVer](https://semver.org). To cut a release, the version
string must be bumped in **four** files in lock-step — Claude Code's installer
reads `marketplace.json` for catalog discovery, `plugin.json` for the install
manifest, and the plugin tests assert on both. Forgetting any one of them
either breaks `pytest` or makes `/plugin update` no-op silently.

1. **Bump the version** in all four files:
   - `.claude-plugin/plugin.json` → `"version"`
   - `.claude-plugin/marketplace.json` → `plugins[0].version`
   - `pyproject.toml` → `[project] version`
   - `tests/test_plugin_manifest.py` → the `data["version"] == "..."` assertion

2. **Add a CHANGELOG entry** under a new `## [X.Y.Z] - YYYY-MM-DD` heading
   summarising what changed. Do not skip this — `/archspec:validate` does not
   rely on the changelog, but downstream users do.

3. **Run the full local check** to make sure nothing else drifted:

   ```bash
   .venv/bin/ruff check .
   .venv/bin/python -m pytest -q
   ```

4. **Open a PR**, merge with squash, then **tag and release**:

   ```bash
   git checkout main && git pull --ff-only
   git tag -a vX.Y.Z -m "vX.Y.Z — short description"
   git push origin vX.Y.Z
   gh release create vX.Y.Z --title "vX.Y.Z — title" --notes "..."
   ```

5. **Note on `marketplace.json` `source.ref`**: it is pinned to `main`
   intentionally — it forces Claude Code's `/plugin update` to re-clone the
   repository on every version bump. Do *not* change it to a specific tag
   unless you also automate updating it on every release; otherwise users will
   keep getting the version the ref was last pointed at.

If `/plugin update archspec` still does not pick up the new version on a user's
machine (a known Claude Code installer quirk where `installed_plugins.json` is
updated but files are not copied), they can work around it with:

```bash
cp -R ~/.claude/plugins/marketplaces/archspec \
      ~/.claude/plugins/cache/archspec/archspec/X.Y.Z
```

…and restart Claude Code.

## Adding a language linter

Add a new directory under `linters/<lang>/`, document its activation in a
`README.md`, and emit findings using the JSON contract described in
`docs/EXTENDING.md`.
