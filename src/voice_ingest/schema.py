"""JSON Schema validation for NormalizedTranscript.

Loads the two schemas from the worktree's `schemas/` directory and exposes a
single `validate(transcript)` helper. Uses `referencing` (modern jsonschema
≥4.18 API) so the cross-schema `$ref` resolves without network.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from . import config

_SCHEMA_DIR = config.WORKTREE_ROOT / "schemas"


def _load(name: str) -> dict:
    return json.loads((_SCHEMA_DIR / name).read_text(encoding="utf-8"))


_NORMALIZED = _load("normalized_transcript.schema.json")
_SEGMENT = _load("speaker_segment.schema.json")

_registry = Registry().with_resource(
    uri=_SEGMENT["$id"],
    resource=Resource.from_contents(_SEGMENT),
).with_resource(
    uri="speaker_segment.schema.json",
    resource=Resource.from_contents(_SEGMENT),
)

_validator = Draft202012Validator(_NORMALIZED, registry=_registry)


def validate(transcript: dict) -> None:
    """Raise jsonschema.ValidationError if transcript does not conform."""
    _validator.validate(transcript)


__all__ = ["validate"]
