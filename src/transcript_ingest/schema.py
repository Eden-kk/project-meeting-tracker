"""Schema loader and validator for NormalizedTranscript.

Uses the modern ``referencing`` registry (jsonschema>=4.18); the deprecated
``RefResolver`` API is intentionally avoided.
"""
from __future__ import annotations

import json
from pathlib import Path

import referencing
from jsonschema import Draft202012Validator
from referencing.jsonschema import DRAFT202012

_SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "schemas"


def _load(name: str) -> dict:
    return json.loads((_SCHEMA_DIR / name).read_text())


_NORMALIZED = _load("normalized_transcript.schema.json")
_SEGMENT = _load("speaker_segment.schema.json")

# Register both schemas under their $id AND under the relative filename used by
# the $ref in normalized_transcript.schema.json.
_registry = (
    referencing.Registry()
    .with_resource(
        uri=_SEGMENT["$id"],
        resource=referencing.Resource(contents=_SEGMENT, specification=DRAFT202012),
    )
    .with_resource(
        uri="speaker_segment.schema.json",
        resource=referencing.Resource(contents=_SEGMENT, specification=DRAFT202012),
    )
    .with_resource(
        uri=_NORMALIZED["$id"],
        resource=referencing.Resource(contents=_NORMALIZED, specification=DRAFT202012),
    )
)

_VALIDATOR = Draft202012Validator(_NORMALIZED, registry=_registry)


def validate(transcript: dict) -> None:
    """Raise ``jsonschema.ValidationError`` if ``transcript`` violates the schema."""
    _VALIDATOR.validate(transcript)
