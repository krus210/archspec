import json
from pathlib import Path

import jsonschema
import pytest

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "skills" / "architecture-sync" / "schema" / "servicemap.schema.json"
)


def _wrap_minimal_with(overrides: dict) -> dict:
    import yaml as _yaml
    minimal_path = (
        Path(__file__).resolve().parent / "fixtures" / "yaml" / "valid" / "minimal.yaml"
    )
    base = _yaml.safe_load(minimal_path.read_text(encoding="utf-8"))
    base.update(overrides)
    return base


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validator(schema):
    return jsonschema.Draft7Validator(schema)


def test_schema_is_valid_draft7(schema):
    jsonschema.Draft7Validator.check_schema(schema)


def test_minimal_yaml_passes(validator, load_yaml):
    doc = load_yaml("valid/minimal.yaml")
    errors = list(validator.iter_errors(doc))
    assert errors == [], [e.message for e in errors]


def test_idempotency_required_must_have_key_source(validator, load_yaml):
    doc = load_yaml("invalid/idempotency_required_no_key_source.yaml")
    errors = list(validator.iter_errors(doc))
    assert any("key_source" in e.message or "storage" in e.message for e in errors), \
        [e.message for e in errors]


def test_downstream_sync_requires_known_fields(validator):
    bad = {
        "service": "x", "timeout": "1s", "retries": 0,
        "fallback": "fail", "on_failure": "return error",
        "extra_field": "nope",
    }
    doc = _wrap_minimal_with(
        {
            "dependencies": {
                "upstream": [],
                "downstream": {"sync": [bad], "async": []},
                "storage": [],
            }
        }
    )
    errors = list(validator.iter_errors(doc))
    assert any("extra_field" in e.message for e in errors)


def test_full_yaml_passes(validator, load_yaml):
    doc = load_yaml("valid/full.yaml")
    errors = list(validator.iter_errors(doc))
    assert errors == [], [e.message for e in errors]


def test_exception_with_unknown_rule_id_pattern_fails(validator, load_yaml):
    doc = load_yaml("invalid/exception_unknown_rule.yaml")
    errors = list(validator.iter_errors(doc))
    assert errors, "expected schema-level error for malformed exception rule id"


def test_go_extensions_allowed_when_language_go(validator, load_yaml):
    doc = load_yaml("valid/full.yaml")
    assert "go_extensions" in doc
    errors = list(validator.iter_errors(doc))
    assert errors == []


def test_missing_metadata_fails(validator, load_yaml):
    doc = load_yaml("invalid/missing_metadata.yaml")
    errors = list(validator.iter_errors(doc))
    assert any("metadata" in e.message for e in errors), [e.message for e in errors]
