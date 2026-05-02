import pytest
from _common import JINJA_ENV, is_read_endpoint, slugify
from jinja2 import UndefinedError


def test_slugify_lowercases_and_replaces_separators():
    assert slugify("Listing Service") == "listing-service"
    assert slugify("payment_facade") == "payment-facade"
    assert slugify("Item/v2") == "item-v2"


def test_slugify_strips_repeats_and_edges():
    assert slugify("--Foo--Bar--") == "foo-bar"
    assert slugify("  hello   world  ") == "hello-world"


def test_slugify_is_pure_and_stable():
    assert slugify("X") == slugify("X")


def test_jinja_env_uses_strict_undefined():
    template = JINJA_ENV.from_string("{{ unknown }}")
    with pytest.raises(UndefinedError):
        template.render()


def test_is_read_endpoint_recognizes_grpc_camelcase():
    assert is_read_endpoint("GetTask") is True
    assert is_read_endpoint("ListTasks") is True
    assert is_read_endpoint("FindMatches") is True
    assert is_read_endpoint("CreateTask") is False
    assert is_read_endpoint("VerifyIdentity") is False


def test_is_read_endpoint_recognizes_http_verbs():
    """Bucket 5.3: HTTP gateway endpoint names like `GET /api/v1/health` are read.

    Reproduces the freelance-marketplace api-gateway false-positive: every
    endpoint there is named `<VERB> <path>`, and DEP-005 used to flag them
    all because plain `is_read_endpoint("GET /...")` returned False.
    """
    assert is_read_endpoint("GET /api/v1/tasks") is True
    assert is_read_endpoint("HEAD /health") is True
    assert is_read_endpoint("OPTIONS /api") is True
    assert is_read_endpoint("POST /api/v1/tasks") is False
    assert is_read_endpoint("DELETE /api/v1/tasks/{id}") is False
    # Trailing-space disambiguation: `GET ` vs `GetX` (the latter is also read,
    # but via the gRPC prefix branch — verify we don't accidentally match
    # `GETX` or other false positives).
    assert is_read_endpoint("GETX") is False  # not a real verb prefix


def test_is_read_endpoint_unknown_http_path_is_not_read():
    """Without an explicit verb prefix, intent is ambiguous → not read."""
    assert is_read_endpoint("/api/v1/tasks") is False
