from hooks.pre_push import check_drift


def test_check_drift_returns_no_findings_when_diagrams_in_sync(synced_repo):
    findings = check_drift(repo_root=synced_repo)
    assert findings == []


def test_check_drift_returns_block_when_yaml_changed_but_diagrams_stale(stale_diagrams_repo):
    findings = check_drift(repo_root=stale_diagrams_repo)
    assert len(findings) >= 1
    assert findings[0].rule == "DET-004"
    assert findings[0].severity == "BLOCK"


def test_check_drift_returns_block_when_diagram_was_hand_edited(hand_edited_diagram_repo):
    findings = check_drift(repo_root=hand_edited_diagram_repo)
    assert any(f.rule == "DET-005" and f.severity == "BLOCK" for f in findings)


def test_check_drift_ignores_uncommitted_working_tree_edits(synced_repo):
    # HEAD is clean (synced YAML + diagrams). Mutate the working-tree YAML only,
    # without staging or committing. Pre-push must compare HEAD blobs, not the
    # working tree, so check_drift must report no findings — the commits being
    # pushed are clean even if the developer has uncommitted local edits.
    yaml = synced_repo / "docs" / "SERVICE_MAP.yaml"
    text = yaml.read_text(encoding="utf-8")
    yaml.write_text(
        text.replace(
            "    - \"create and update listings\"",
            "    - \"create and update listings\"\n    - \"reindex on demand\"",
        ),
        encoding="utf-8",
    )

    findings = check_drift(repo_root=synced_repo)
    assert findings == []
