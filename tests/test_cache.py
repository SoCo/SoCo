"""Tests for the cache module."""


from soco.cache import Cache, NullCache, TimedCache


def test_instance_creation():
    assert isinstance(Cache(), TimedCache)
    from soco import config

    config.CACHE_ENABLED = False
    assert isinstance(Cache(), NullCache)
    config.CACHE_ENABLED = True


def test_cache_put_get():
    """Test putting items into, and getting them from, the cache."""
    from time import sleep

    cache = Cache()
    cache.put("item", "some", kw="args", timeout=3)
    assert not cache.get("some", "otherargs") == "item"
    assert cache.get("some", kw="args") == "item"
    sleep(2)
    assert cache.get("some", kw="args") == "item"
    sleep(2)
    assert not cache.get("some", kw="args") == "item"

    cache.put("item", "some", "args", and_a="keyword", timeout=3)
    assert cache.get("some", "args", and_a="keyword") == "item"
    assert not cache.get("some", "otherargs", and_a="keyword") == "item"


def test_cache_clear_del():
    """Test removal of items and clearing the cache."""
    cache = Cache()
    cache.put("item", "some", kw="args", timeout=2)
    # Check it's there
    assert cache.get("some", kw="args") == "item"
    # delete it
    cache.delete("some", kw="args")
    assert not cache.get("some", kw="args") == "item"
    # put it back
    cache.put("item", "some", kw="args", timeout=3)
    cache.clear()
    assert not cache.get("some", kw="args") == "item"


def test_with_typical_args():
    cache = Cache()
    cache.put(
        "result",
        "SetAVTransportURI",
        [
            ("InstanceID", 1),
            ("CurrentURI", "URI2"),
            ("CurrentURIMetaData", "abcd"),
            ("Unicode", "μИⅠℂ☺ΔЄ💋"),
        ],
        timeout=3,
    )
    assert (
        cache.get(
            "SetAVTransportURI",
            [
                ("InstanceID", 1),
                ("CurrentURI", "URI2"),
                ("CurrentURIMetaData", "abcd"),
                ("Unicode", "μИⅠℂ☺ΔЄ💋"),
            ],
        )
        == "result"
    )


def test_cache_disable():
    cache = Cache()
    assert cache.enabled is True
    cache.enabled = False
    cache.put("item", "args", timeout=3)
    assert cache.get("args") is None
    # Check it's there
    assert cache.get("some", kw="args") is None
