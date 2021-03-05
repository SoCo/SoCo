"""Tests for the services module."""

# These tests require pytest.


import pytest

from soco.exceptions import SoCoUPnPException
from soco.services import Service, Action, Argument, Vartype

from unittest import mock

# Dummy known-good errors/responses etc.  These are not necessarily valid as
# actual commands, but are valid XML/UPnP. They also contain unicode characters
# to test unicode handling.

DUMMY_ERROR = "".join(
    [
        '<?xml version="1.0"?>',
        "<s:Envelope ",
        'xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" ',
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">',
        "<s:Body>",
        "<s:Fault>",
        "<faultcode>s:Client</faultcode>",
        "<faultstring>UPnPError</faultstring>",
        "<detail>",
        '<UPnPError xmlns="urn:schemas-upnp-org:control-1-0">',
        "<errorCode>607</errorCode>",
        "<errorDescription>Oops μИⅠℂ☺ΔЄ💋</errorDescription>",
        "</UPnPError>",
        "</detail>",
        "</s:Fault>",
        "</s:Body>",
        "</s:Envelope>",
    ]
)  # noqa PEP8

DUMMY_VALID_RESPONSE = "".join(
    [
        '<?xml version="1.0"?>',
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"',
        ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">',
        "<s:Body>",
        "<u:GetLEDStateResponse ",
        'xmlns:u="urn:schemas-upnp-org:service:DeviceProperties:1">',
        "<CurrentLEDState>On</CurrentLEDState>",
        "<Unicode>μИⅠℂ☺ΔЄ💋</Unicode>",
        "</u:GetLEDStateResponse>",
        "</s:Body>",
        "</s:Envelope>",
    ]
)  # noqa PEP8

DUMMY_VALID_ACTION = "".join(
    [
        '<?xml version="1.0"?>',
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"',
        ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">',
        "<s:Body>",
        "<u:SetAVTransportURI ",
        'xmlns:u="urn:schemas-upnp-org:service:Service:1">',
        "<InstanceID>0</InstanceID>",
        "<CurrentURI>URI</CurrentURI>",
        "<CurrentURIMetaData></CurrentURIMetaData>",
        "<Unicode>μИⅠℂ☺ΔЄ💋</Unicode>" "</u:SetAVTransportURI>",
        "</s:Body>" "</s:Envelope>",
    ]
)  # noqa PEP8

DUMMY_VARTYPE = Vartype("string", None, None, None)

DUMMY_ACTIONS = [
    Action(
        name="Test",
        in_args=[
            Argument(name="Argument1", vartype=DUMMY_VARTYPE),
            Argument(name="Argument2", vartype=DUMMY_VARTYPE),
        ],
        out_args=[],
    )
]

DUMMY_ARGS = [("Argument1", 1), ("Argument2", 2)]

DUMMY_ARGS_ALTERNATIVE = [("Argument1", 3), ("Argument2", 2)]


@pytest.fixture()
def service():
    """A mock Service, for use as a test fixture."""

    mock_soco = mock.MagicMock()
    mock_soco.ip_address = "192.168.1.101"
    mock_service = Service(mock_soco)
    return mock_service


def test_init_defaults(service):
    """Check default properties are set up correctly."""
    assert service.service_type == "Service"
    assert service.version == 1
    assert service.service_id == "Service"
    assert service.base_url == "http://192.168.1.101:1400"
    assert service.control_url == "/Service/Control"
    assert service.scpd_url == "/xml/Service1.xml"
    assert service.event_subscription_url == "/Service/Event"


def test_method_dispatcher_function_creation(service):
    """Testing __getattr__ functionality."""
    import inspect

    # There should be no testing method
    assert "testing" not in service.__dict__.keys()
    # but we should be able to inspect it
    assert inspect.ismethod(service.testing)
    # and then, having examined it, the method should be cached on the instance
    assert "testing" in service.__dict__.keys()
    assert service.testing.__name__ == "testing"
    # check that send_command is actually called when we invoke a method
    service.send_command = lambda x, y: "Hello {}".format(x)
    assert service.testing(service) == "Hello testing"


def test_method_dispatcher_arg_count(service):
    """_dispatcher should pass its args to send_command."""
    service.send_command = mock.Mock()
    # http://bugs.python.org/issue7688
    # __name__ must be a string in python 2
    method = service.__getattr__("test")
    assert method("onearg")
    service.send_command.assert_called_with("test", "onearg")
    assert method()  # no args
    service.send_command.assert_called_with("test")
    assert method("one", cache_timeout=4)  # one arg + cache_timeout
    service.send_command.assert_called_with("test", "one", cache_timeout=4)


def test_wrap(service):
    """wrapping args in XML properly."""
    assert (
        service.wrap_arguments([("first", "one"), ("second", 2)])
        == "<first>one</first><second>2</second>"
    )
    assert service.wrap_arguments() == ""
    # Unicode
    assert (
        service.wrap_arguments([("unicode", "μИⅠℂ☺ΔЄ💋")])
        == "<unicode>μИⅠℂ☺ΔЄ💋</unicode>"
    )
    # XML escaping - do we also need &apos; ?
    assert (
        service.wrap_arguments([("weird", '&<"2')]) == "<weird>&amp;&lt;&quot;2</weird>"
    )


def test_unwrap(service):
    """unwrapping args from XML."""
    assert service.unwrap_arguments(DUMMY_VALID_RESPONSE) == {
        "CurrentLEDState": "On",
        "Unicode": "μИⅠℂ☺ΔЄ💋",
    }


def test_unwrap_invalid_char(service):
    """Test unwrapping args from XML with invalid char"""
    responce_with_invalid_char = DUMMY_VALID_RESPONSE.replace("μИⅠℂ☺ΔЄ💋", "AB")
    # Note, the invalid ^D (code point 0x04) should be filtered out
    assert service.unwrap_arguments(responce_with_invalid_char) == {
        "CurrentLEDState": "On",
        "Unicode": "AB",
    }


def test_compose(service):
    """Test argument composition."""
    service._actions = DUMMY_ACTIONS
    service.DEFAULT_ARGS = {}

    # Detect unknown action
    with pytest.raises(AttributeError):
        service.compose_args("Error", {})
    # Detect missing / unknown arguments
    with pytest.raises(ValueError):
        service.compose_args("Test", {"Argument1": 1})
    with pytest.raises(ValueError):
        service.compose_args("Test", dict(DUMMY_ARGS + [("Error", 3)]))

    # Check correct output
    assert service.compose_args("Test", dict(DUMMY_ARGS)) == DUMMY_ARGS

    # Set Argument1 = 1 as default
    service.DEFAULT_ARGS = dict(DUMMY_ARGS[:1])

    # Check that arguments are completed with default values
    assert service.compose_args("Test", dict(DUMMY_ARGS[1:])) == DUMMY_ARGS
    # Check that given arguments override the default values
    assert (
        service.compose_args("Test", dict(DUMMY_ARGS_ALTERNATIVE))
        == DUMMY_ARGS_ALTERNATIVE
    )


def test_build_command(service):
    """Test creation of SOAP body and headers from a command."""
    headers, body = service.build_command(
        "SetAVTransportURI",
        [
            ("InstanceID", 0),
            ("CurrentURI", "URI"),
            ("CurrentURIMetaData", ""),
            ("Unicode", "μИⅠℂ☺ΔЄ💋"),
        ],
    )
    assert body == DUMMY_VALID_ACTION
    assert headers == {
        "Content-Type": 'text/xml; charset="utf-8"',
        "SOAPACTION": "urn:schemas-upnp-org:service:Service:1#SetAVTransportURI",
    }


def test_send_command(service):
    """Calling a command should result in a http request, unless the cache is
    hit."""
    response = mock.MagicMock()
    response.headers = {}
    response.status_code = 200
    response.text = DUMMY_VALID_RESPONSE
    with mock.patch("requests.post", return_value=response) as fake_post:
        result = service.send_command(
            "SetAVTransportURI",
            [
                ("InstanceID", 0),
                ("CurrentURI", "URI"),
                ("CurrentURIMetaData", ""),
                ("Unicode", "μИⅠℂ☺ΔЄ💋"),
            ],
            cache_timeout=2,
        )
        assert result == {"CurrentLEDState": "On", "Unicode": "μИⅠℂ☺ΔЄ💋"}
        fake_post.assert_called_once_with(
            "http://192.168.1.101:1400/Service/Control",
            headers=mock.ANY,
            data=DUMMY_VALID_ACTION.encode("utf-8"),
            timeout=20,
        )
        # Now the cache should be primed, so try it again
        fake_post.reset_mock()
        result = service.send_command(
            "SetAVTransportURI",
            [
                ("InstanceID", 0),
                ("CurrentURI", "URI"),
                ("CurrentURIMetaData", ""),
                ("Unicode", "μИⅠℂ☺ΔЄ💋"),
            ],
            cache_timeout=0,
        )
        # The cache should be hit, so there should be no http request
        assert not fake_post.called
        # but this should not affefct a call with different params
        fake_post.reset_mock()
        result = service.send_command(
            "SetAVTransportURI",
            [
                ("InstanceID", 1),
                ("CurrentURI", "URI2"),
                ("CurrentURIMetaData", "abcd"),
                ("Unicode", "μИⅠℂ☺ΔЄ💋"),
            ],
        )
        assert fake_post.called
        # calling again after the time interval will avoid the cache
        fake_post.reset_mock()
        import time

        time.sleep(2)
        result = service.send_command(
            "SetAVTransportURI",
            [
                ("InstanceID", 0),
                ("CurrentURI", "URI"),
                ("CurrentURIMetaData", ""),
                ("Unicode", "μИⅠℂ☺ΔЄ💋"),
            ],
        )
        assert fake_post.called


def test_handle_upnp_error(service):
    """Check errors are extracted properly."""
    with pytest.raises(SoCoUPnPException) as E:
        service.handle_upnp_error(DUMMY_ERROR)
    assert (
        "UPnP Error 607 received: Signature Failure from 192.168.1.101"
        == E.value.message
    )
    assert E.value.error_code == "607"
    assert E.value.error_description == "Signature Failure"
    # TODO: Try this with a None Error Code


# TODO: test iter_actions
