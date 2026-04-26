import pytest
from _common import JINJA_ENV, slugify
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
