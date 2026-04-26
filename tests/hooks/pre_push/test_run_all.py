from hooks.pre_push import run_all


def test_run_all_returns_zero_on_clean_repo(synced_repo):
    rc = run_all(repo_root=synced_repo, base_ref="main")
    assert rc == 0


def test_run_all_returns_one_when_diagrams_stale(stale_diagrams_repo):
    rc = run_all(repo_root=stale_diagrams_repo, base_ref="main")
    assert rc == 1
