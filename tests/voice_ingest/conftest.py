from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def worktree_root() -> Path:
    # tests/voice_ingest/conftest.py -> parents[2] = repo root
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def audio_fixture_path(worktree_root: Path) -> Path:
    return worktree_root / "fixtures" / "sample_audio.wav"


@pytest.fixture(scope="session")
def expected_text(worktree_root: Path) -> str:
    return (worktree_root / "fixtures" / "sample_audio_expected_text.txt").read_text(
        encoding="utf-8"
    )
