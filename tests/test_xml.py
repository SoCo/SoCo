"""Tests for the xml module."""


from soco import xml


def test_ns_tag():
    """Test the ns_tag function."""
    namespaces = [
        "http://purl.org/dc/elements/1.1/",
        "urn:schemas-upnp-org:metadata-1-0/upnp/",
        "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/",
    ]
    for ns_in, namespace in zip(["dc", "upnp", ""], namespaces):
        res = xml.ns_tag(ns_in, "testtag")
        correct = "{{{}}}{}".format(namespace, "testtag")
        assert res == correct
