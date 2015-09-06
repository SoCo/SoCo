# -*- coding: utf-8 -*-
# pylint: disable=fixme

"""
Classes for handling SoCo's basis SOAP requirements.

This module does not handle anything like the full SOAP specification, but is
enough for SoCo's needs.

Sonos uses SOAP for UPnP communications, and for communication with third party
music services.
"""

# The state of Python's SOAP libraries is poor. In any event, the two main
# libraries, PySimpleSOAP and SUDS (or the more up-to-date SUDS-Jurko),
# are too complex for our needs. SUDS requires a WSDL file to be parsed,
# and although SONOS provides one in relation to music services (at
# http://musicpartners.sonos.com/sites/default/files/Sonos.wsdl) the various
# music services themselves provide buggy, incomplete or old
# implementations which cause SUDS to break. PySimpleSOAP can work without a
# WSDL file, but contains various bugs which mean that we would have to use
# a patched version (upstream releases are infrequent).  Since SONOS only
# appears to use basic SOAP features, and after experimenting with other
# libraries, it seems best to write our own.

# Some is the same as that in services.py.
# TODO: refactor services.py to depend on this code

from __future__ import (
    absolute_import, unicode_literals
)

import logging
from xml.sax.saxutils import escape

import requests

from soco.exceptions import SoCoException
from soco.utils import prettify
from soco.xml import XML

_LOG = logging.getLogger(__name__)


class SoapFault(SoCoException):

    """An exception encapsulating a SOAP Fault."""

    def __init__(self, faultcode, faultstring, detail=None):
        """ Args:
                faultcode (str): The SOAP faultcode
                faultstring (str): The SOAP faultstring
                detail (Element): The SOAP fault detail, as an ElementTree
                     Element. Default, None

        """
        self.faultcode = faultcode
        self.faultstring = faultstring
        self.detail = detail
        self.detail_string = XML.tostring(detail) if detail is not None else ''
        super(SoapFault, self).__init__(faultcode, faultstring)

    def __str__(self):
        return '%s: %s' % (self.faultcode, self.faultstring)

    def __repr__(self):
        return "SoapFault(faultcode={0}, faultstring={1}, detail={2})".format(
            repr(self.faultcode),
            repr(self.faultstring),
            repr(self.detail)
        )


# Sonos uses SOAP to send commands in the RPC form. A complete RPC SOAP
# message should look something like this. See generally
# http://www.w3.org/TR/2000/NOTE-SOAP-20000508/

# POST Endpoint URL HTTP/1.1
# HOST: Host of Endpoint URL:port
# CONTENT-LENGTH: bytes in body
# CONTENT-TYPE: text/xml; charset="utf-8"
# SOAPACTION: URI
#
# <?xml version="1.0"?>
# <s:Envelope
#   xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
#   s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
#   <s:Header>
#       </Header elements go here>
#   </s:Header>
#   <s:Body>
#       <ns:MethodName xmlns:ns="MethodNamespace>"
#           <param1>value</param1>
#           ...
#           <param_n>value</param_n>
#       </ns:MethodName>
#   </s:Body>
# </s:Envelope>

# pylint: disable=too-many-instance-attributes, too-many-arguments
# pylint: disable=no-self-use, fixme


class SoapMessage(object):

    """
    A SOAP Message representing a remote procedure call.

    Uses the Requests library for communication with a SOAP server.
    """

    def __init__(self, endpoint, method, parameters=None, http_headers=None,
                 soap_action=None, soap_header=None, namespace=None,
                 **request_args):
        """ Args:
                endpoint (str): The SOAP endpoint URL for this client
                method (str): The name of the method to call
                parameters (list): A list of (name, value) tuples containing
                    the parameters to pass to the method. Default None
                http_headers (dict): A dict in the form {'Header': 'Value,..}
                    containing http headers to use for the http request.
                    Content-type and SOAPACTION headers will be created
                    automatically, so do not include them here. Use this, for
                    example, to set a user-agent.
                soap_action (str): The value of the SOAPACTION header.
                    Default NONE
                soap_header (str): A string representation of the XML to be
                    used for the SOAP Header. Default None
                namespace (str): The namespace URI to use for the method and
                    parameters. None, by default.
                **request_args: Other keyword parameters will be passed to the
                    Requests request which is used to handle the http
                    communication. For example, a timeout value can be set.
        """
        self.endpoint = endpoint
        self.method = method
        self.parameters = [] if parameters is None else parameters
        self.http_headers = http_headers
        self.soap_action = soap_action
        self.soap_header = soap_header
        self.namespace = namespace
        self.request_args = request_args

    def prepare_headers(self, http_headers, soap_action):
        """Prepare the http headers for sending."""

        headers = {'Content-Type': 'text/xml; charset="utf-8"'}
        if soap_action is not None:
            headers.update({'SOAPACTION': '"{0}"'.format(soap_action)})
        if http_headers is not None:
            headers.update(http_headers)
        return headers

    def prepare_soap_header(self, soap_header):
        """Prepare the SOAP header for sending."""

        if soap_header is not None:
            return '<s:Header>{0}</s:Header>'.format(soap_header)
        else:
            return ''

    def prepare_soap_body(self, method, parameters, namespace):
        """Prepare the SOAP message body for sending."""

        tags = []
        for name, value in parameters:
            # pylint: disable=bad-format-string
            tag = "<{name}>{value}</{name}>".format(
                name=name, value=escape("%s" % value, {'"': "&quot;"}))
            # % converts to unicode because we are using unicode literals.
            # Avoids use of 'unicode' function which does not exist in python 3
            tags.append(tag)

        wrapped_params = "".join(tags)
        # Prepare the SOAP Body
        if namespace is not None:
            soap_body = (
                '<{method} xmlns="{namespace}">'
                '{params}'
                '</{method}>'.format(
                    method=method, params=wrapped_params,
                    namespace=namespace
                ))
        else:
            soap_body = (
                '<{method}>'
                '{params}'
                '</{method}>'.format(
                    method=method, params=wrapped_params
                ))

        return soap_body

    def prepare_soap_envelope(self, prepared_soap_header, prepared_soap_body):
        """Prepare the SOAP Envelope for sending."""

        # pylint: disable=bad-continuation
        soap_env_template = (
            '<?xml version="1.0"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
            ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
                '{soap_header}'
                    '<s:Body>'
                        '{soap_body}'
                    '</s:Body>'
            '</s:Envelope>')  # noqa PEP8
        return soap_env_template.format(
            soap_header=prepared_soap_header,
            soap_body=prepared_soap_body)

    def prepare(self):
        """Prepare the SOAP message for sending to the server."""
        headers = self.prepare_headers(self.http_headers, self.soap_action)

        soap_header = self.prepare_soap_header(self.soap_header)
        soap_body = self.prepare_soap_body(
            self.method, self.parameters, self.namespace
        )
        data = self.prepare_soap_envelope(soap_header, soap_body)
        return (headers, data)

    def call(self):
        """Call the SOAP method on the server."""

        headers, data = self.prepare()

        # Check log level before logging XML, since prettifying it is
        # expensive
        if _LOG.isEnabledFor(logging.DEBUG):
            _LOG.debug("Sending %s, %s", headers, prettify(data))

        response = requests.post(
            self.endpoint,
            headers=headers,
            data=data.encode('utf-8'),
            **self.request_args
        )
        _LOG.debug("Received %s, %s", response.headers, response.text)
        status = response.status_code
        if status == 200:
            # The response is good. Extract the Body
            tree = XML.fromstring(response.content)
            # Get the first child of the <Body> tag. NB There should only be
            # one if the RPC standard is followed.
            body = tree.find(
                "{http://schemas.xmlsoap.org/soap/envelope/}Body")[0]
            return body
        elif status == 500:
            # We probably have a SOAP Fault
            tree = XML.fromstring(response.content)
            fault = tree.find(
                './/{http://schemas.xmlsoap.org/soap/envelope/}Fault'
            )
            if fault is None:
                # Not a SOAP fault. Must be something else.
                response.raise_for_status()
            faultcode = fault.findtext("faultcode")
            faultstring = fault.findtext("faultstring")
            faultdetail = fault.find("detail")
            raise SoapFault(faultcode, faultstring, faultdetail)
        else:
            # Something else has gone wrong. Probably a network error. Let
            # Requests handle it
            response.raise_for_status()
