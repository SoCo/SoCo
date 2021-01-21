"""Tests for the soap module."""


from soco.soap import SoapMessage
from soco.xml import XML
from unittest import mock


DUMMY_VALID_RESPONSE = "".join(
    [
        '<?xml version="1.0"?>',
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"',
        ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">',
        "<s:Body>",
        "<u:GetLEDStateResponse ",
        'xmlns:u="urn:schemas-upnp-org:service:DeviceProperties:1">',
        "<CurrentLEDState>On</CurrentLEDState>",
        "<Unicode>data</Unicode>",
        "</u:GetLEDStateResponse>",
        "</s:Body>",
        "</s:Envelope>",
    ]
)  # noqa PEP8


def test_init():
    """Tests for initialisation of classes."""
    s = SoapMessage("http://endpoint_url", "a_method")
    assert s.endpoint == "http://endpoint_url"
    assert s.method == "a_method"
    assert s.parameters == []
    assert s.soap_action is None
    assert s.http_headers is None
    assert s.soap_header is None
    assert s.namespace is None
    assert s.request_args == {}


def test_prepare_headers():
    """Check http_headers are correctly prepared."""
    s = SoapMessage("endpoint", "method")
    h = s.prepare_headers({"test1": "one", "test2": "two"}, None)
    assert h == {
        "Content-Type": 'text/xml; charset="utf-8"',
        "test2": "two",
        "test1": "one",
    }
    h = s.prepare_headers(
        http_headers={"test1": "one", "test2": "two"}, soap_action="soapaction"
    )
    assert h == {
        "Content-Type": 'text/xml; charset="utf-8"',
        "test2": "two",
        "test1": "one",
        "SOAPACTION": '"soapaction"',
    }


def test_prepare_soap_header():
    """Check that the SOAP header is correctly wrapped."""
    s = SoapMessage("endpoint", "method")
    h = s.prepare_soap_header("<a><b></b></a>")
    assert h == "<s:Header><a><b></b></a></s:Header>"
    s = SoapMessage("endpoint", "method", http_headers={"test1": "one", "test2": "two"})
    h = s.prepare_soap_header(None)
    assert h == ""


def test_prepare_soap_body():
    """Check that the SOAP body is correctly prepared."""
    # No params
    s = SoapMessage("endpoint", "method")
    b = s.prepare_soap_body("a_method", [], None)
    assert b == "<a_method></a_method>"
    # One param
    b = s.prepare_soap_body("a_method", [("one", "1")], None)
    assert b == "<a_method><one>1</one></a_method>"
    # Two params
    b = s.prepare_soap_body("a_method", [("one", "1"), ("two", "2")], None)
    assert b == "<a_method><one>1</one><two>2</two></a_method>"

    # And with a namespace

    b = s.prepare_soap_body(
        "a_method", [("one", "1"), ("two", "2")], "http://a_namespace"
    )
    assert (
        b == "<a_method "
        'xmlns="http://a_namespace"><one>1</one><two>2</two'
        "></a_method>"
    )


def test_prepare():
    """Test preparation of whole SOAP message."""
    s = SoapMessage(
        endpoint="endpoint",
        method="getData",
        parameters=[("one", "1")],
        http_headers={"timeout": "3"},
        soap_action="ACTION",
        soap_header="<a_header>data</a_header>",
        namespace="http://namespace.com",
    )
    headers, data = s.prepare()
    assert (
        data == '<?xml version="1.0"?><s:Envelope '
        'xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap'
        '/encoding/"><s:Header><a_header>data</a_header></s'
        ":Header><s:Body><getData "
        'xmlns="http://namespace.com"><one>1</one></getData></s'
        ":Body></s:Envelope>"
    )


def test_call():
    """Calling a command should result in an http request."""

    s = SoapMessage(
        endpoint="http://endpoint.example.com",
        method="getData",
        parameters=[("one", "1")],
        http_headers={"user-agent": "sonos"},
        soap_action="ACTION",
        soap_header="<a_header>data</a_header>",
        namespace="http://namespace.com",
        other_arg=4,
    )

    response = mock.MagicMock()
    response.headers = {}
    response.status_code = 200
    response.content = DUMMY_VALID_RESPONSE
    with mock.patch("requests.post", return_value=response) as fake_post:
        result = s.call()
        assert XML.tostring(result)
        fake_post.assert_called_once_with(
            "http://endpoint.example.com",
            headers={
                "SOAPACTION": '"ACTION"',
                "Content-Type": 'text/xml; charset="utf-8"',
                "user-agent": "sonos",
            },
            data=mock.ANY,
            other_arg=4,
        )
