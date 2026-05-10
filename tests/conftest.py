import json
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def worktree_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def vtt_fixture_path(worktree_root: Path) -> Path:
    return worktree_root / "fixtures" / "sample_transcript.vtt"


@pytest.fixture(scope="session")
def srt_fixture_path(worktree_root: Path) -> Path:
    return worktree_root / "fixtures" / "sample_transcript.srt"


@pytest.fixture(scope="session")
def txt_fixture_path(worktree_root: Path) -> Path:
    return worktree_root / "fixtures" / "sample_transcript.txt"


@pytest.fixture(scope="session")
def expected_normalized(worktree_root: Path) -> dict:
    return json.loads((worktree_root / "fixtures" / "expected_normalized.json").read_text())
