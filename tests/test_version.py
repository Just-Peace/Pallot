"""The commit shown in the footer, read from a checkout's .git without running git."""

from __future__ import annotations

from votebot import version

A = "1a2b3c4d" * 5
B = "9f8e7d6c" * 5


def _repo(tmp_path, head: str):
    git = tmp_path / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text(head + "\n")
    return git


def test_a_branch_from_its_loose_ref(tmp_path):
    git = _repo(tmp_path, "ref: refs/heads/develop")
    (git / "refs" / "heads" / "develop").write_text(A + "\n")
    assert version.git_commit(tmp_path) == A


def test_a_branch_from_packed_refs(tmp_path):
    git = _repo(tmp_path, "ref: refs/heads/develop")
    (git / "packed-refs").write_text(f"# pack-refs with: peeled fully-peeled sorted\n{B} refs/heads/dev\n{A} refs/heads/develop\n")
    assert version.git_commit(tmp_path) == A


def test_a_detached_head(tmp_path):
    _repo(tmp_path, A)
    assert version.git_commit(tmp_path) == A


def test_a_worktree_reads_the_shared_refs(tmp_path):
    main = _repo(tmp_path / "main", "ref: refs/heads/develop")
    (main / "refs" / "heads" / "feat").write_text(B + "\n")
    own = main / "worktrees" / "wt"
    own.mkdir(parents=True)
    (own / "HEAD").write_text("ref: refs/heads/feat\n")
    (own / "commondir").write_text("../..\n")
    (tmp_path / "wt").mkdir()
    (tmp_path / "wt" / ".git").write_text(f"gitdir: {own}\n")
    assert version.git_commit(tmp_path / "wt") == B


def test_no_commit_outside_a_checkout_or_on_an_unborn_branch(tmp_path):
    assert version.git_commit(tmp_path) is None
    _repo(tmp_path, "ref: refs/heads/main")
    assert version.git_commit(tmp_path) is None


def test_the_docker_build_bakes_the_commit_in(tmp_path, monkeypatch):
    monkeypatch.setattr(version, "BAKED", tmp_path / "COMMIT")
    (tmp_path / "COMMIT").write_text(B + "\n")
    assert version.short_commit() == B[:7]
