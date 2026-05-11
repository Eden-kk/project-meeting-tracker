#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/datamodel-codegen \
  --input schemas/ \
  --input-file-type jsonschema \
  --output src/storage_router/models/contracts.py \
  --output-model-type pydantic_v2.BaseModel \
  --use-schema-description \
  --use-standard-collections \
  --use-union-operator \
  --target-python-version 3.12 \
  --field-constraints
