# -*- coding: utf-8 -*-
from __future__ import unicode_literals

"""
Classes representing Sonos UPnP services.

>>> s = SoCo('192.168.1.102')
>>> print s.RenderingControl.GetMute([('InstanceID', 0),
...     ('Channel', 'Master')])

>>> r = s.ContentDirectory.Browse([
...    ('ObjectID', 'Q:0'),
...    ('BrowseFlag', 'BrowseDirectChildren'),
...    ('Filter', '*'),
...    ('StartingIndex', '0'),
...    ('RequestedCount', '100'),
...    ('SortCriteria', '')
...    ])

>>> print prettify(r['Result'])

>>> for action, in_args, out_args in s.QPlay.iter_actions():
...    print action, in_args, out_args

"""
# UPnP Spec at http://upnp.org/specs/arch/UPnP-arch-DeviceArchitecture-v1.0.pdf

from types import MethodType
from collections import namedtuple
from xml.sax.saxutils import escape
import logging
try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

import requests


log = logging.getLogger(__name__)
#logging.basicConfig()
#log.setLevel(logging.INFO)

Action = namedtuple('Action', 'name, in_args, out_args')
Argument = namedtuple('Argument', 'name, vartype')


def prettify(unicode_text):
    """Return a pretty-printed version of a unicode XML string. Useful for
    debugging.

    """
    import xml.dom.minidom
    reparsed = xml.dom.minidom.parseString(unicode_text.encode('utf-8'))
    return reparsed.toprettyxml(indent="  ", newl="\n")


# An object to contain info about UPnP Services. There is other information
# we could record, but this will do for the moment.
# Info about a Sonos device is available at
#   <IP_address>/xml/device_description.xml
# in the <service> tags


class Service(object):
    """ An class representing a UPnP service.

    This class has a dynamic method dispatcher. Calls to methods which are not
    explicitly defined here are dispatched automatically to the service action
    with the same name.

    """
    soap_body_template = "".join([
        '<?xml version="1.0"?>',
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"',
        ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">',
            '<s:Body>',
                '<u:{action} xmlns:u="urn:schemas-upnp-org:service:',
                    '{self.service_type}:{self.version}">',
                    '{arguments}',
                '</u:{action}>',
            '</s:Body>',
        '</s:Envelope>'])  # noqa PEP8

    """ The base class for all Sonos Service classes"""

    def __init__(self, soco):
        self.soco = soco
        # Some defaults. Some or all these will need to be overridden
        # specifically in a sub-class.
        self.service_type = self.__class__.__name__
        self.version = 1
        self.service_id = self.service_type
        self.base_url = 'http://{}:1400'.format(self.soco.speaker_ip)
        self.control_url = '/{}/Control'.format(self.service_type)
        # Service control protocol description
        self.scpd_url = '/xml/{}{}.xml'.format(self.service_type, self.version)
        log.debug(
            "Created service %s, ver %s, id %s, base_url %s, control_url %s",
            self.service_type, self.version, self.service_id, self.base_url,
            self.control_url)

        # From table 3.3 in
        # http://upnp.org/specs/arch/UPnP-arch-DeviceArchitecture-v1.1.pdf
        # This list may not be complete, but should be good enough to be going
        # on with.  Error codes between 700-799 are defined for particular
        # services, and may be overriden in subclasses. Error codes >800
        # are generally SONOS specific. NB It may well be that SONOS does not
        # use some of these error codes.

        self.UPNP_ERRORS = {
            400: 'Bad Request',
            401: 'Invalid Action',
            402: 'Invalid Args',
            404: 'Invalid Var',
            412: 'Precondition Failed',
            501: 'Action Failed',
            600: 'Argument Value Invalid',
            601: 'Argument Value Out of Range',
            602: 'Optional Action Not Implemented',
            603: 'Out Of Memory',
            604: 'Human Intervention Required',
            605: 'String Argument Too Long',
            606: 'Action Not Authorized',
            607: 'Signature Failure',
            608: 'Signature Missing',
            609: 'Not Encrypted',
            610: 'Invalid Sequence',
            611: 'Invalid Control URL',
            612: 'No Such Session',
        }

    def __getattr__(self, action):

        def _dispatcher(self, args):
            return self.send_command(action, args)

        _dispatcher.__name__ = action
        method = MethodType(_dispatcher, self, self.__class__)
        setattr(self, action, method)
        log.debug("Dispatching method %s", action)
        return method

    def wrap_arguments(self, args=None):
        """ Wrap a list of tuples in xml ready to pass into a SOAP request.

        args is a list of (name, value) tuples specifying the name of each
        argument and its value, eg [('InstanceID', 0), ('Speed', 1)]. The value
        can be a string or something with a string representation. The
        arguments are escaped and wrapped in <name> and <value> tags.

        >>> from soco import SoCo
        >>> device = SoCo('192.168.1.101')
        >>> s = Service(device)
        >>> s.wrap_arguments([('InstanceID', 0), ('Speed', 1)])
        u'<InstanceID>0</InstanceID><Speed>1</Speed>'

        """
        if not args:
            args = []
        l = ["<{name}>{value}</{name}>".format(
            name=name, value=escape(unicode(value))) for name, value in args]
        xml = "".join(l)
        return xml

    def unwrap_arguments(self, xml_response):
        """ Extract arguments and their values from a SOAP response.

        Given an soap/xml response, return a dict of {argument_name, value)}
        items

        """

        # A UPnP SOAP response (including headers) looks like this:

        # HTTP/1.1 200 OK
        # CONTENT-LENGTH: bytes in body
        # CONTENT-TYPE: text/xml; charset="utf-8" DATE: when response was
        # generated
        # EXT:
        # SERVER: OS/version UPnP/1.0 product/version
        #
        # <?xml version="1.0"?>
        # <s:Envelope
        #   xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
        #   s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
        #   <s:Body>
        #       <u:actionNameResponse
        #           xmlns:u="urn:schemas-upnp-org:service:serviceType:v">
        #           <argumentName>out arg value</argumentName>
        #               ... other out args and their values go here, if any
        #       </u:actionNameResponse>
        #   </s:Body>
        # </s:Envelope>

        # Get all tags in order. Elementree (in python 2.x) seems to prefer to
        # be fed bytes, rather than unicode
        xml_response = xml_response.encode('utf-8')
        tree = ET.fromstring(xml_response)
        # Get the first chiled of the <Body> tag which will be
        # <{actionNameResponse}> (depends on what actionName is). Turn the
        # children of this into a {tagname, content} dict
        action_response = tree.find(
            ".//{http://schemas.xmlsoap.org/soap/envelope/}Body")[0]
        return {i.tag: i.text for i in action_response}

    def build_command(self, action, args):
        """ Build a SOAP request.

        Given the name of an action (a string as specified in the service
        description XML file) to be sent, and the relevant arguments as a list
        of (name, value) tuples, return a tuple containing the POST headers (as
        a dict) and a string containing the relevant SOAP body. Does not set
        content-length, or host headers, which are completed upon sending.

        """

        # A complete request should look something like this:

        # POST path of control URL HTTP/1.1
        # HOST: host of control URL:port of control URL
        # CONTENT-LENGTH: bytes in body
        # CONTENT-TYPE: text/xml; charset="utf-8"
        # SOAPACTION: "urn:schemas-upnp-org:service:serviceType:v#actionName"
        #
        # <?xml version="1.0"?>
        # <s:Envelope
        #   xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
        #   s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
        #   <s:Body>
        #       <u:actionName
        #           xmlns:u="urn:schemas-upnp-org:service:serviceType:v">
        #           <argumentName>in arg value</argumentName>
        #           ... other in args and their values go here, if any
        #       </u:actionName>
        #   </s:Body>
        # </s:Envelope>

        arguments = self.wrap_arguments(args)
        body = self.soap_body_template.format(**locals())
        soap_action_template = \
            "urn:schemas-upnp-org:service:{service_type}:{version}#{action}"
        soap_action = soap_action_template.format(
            service_type=self.service_type, version=self.version,
            action=action)
        headers = {'Content-Type': 'text/xml; charset="utf-8"',
                   'SOAPACTION': soap_action}
        return (headers, body)

    def send_command(self, action, args):
        """ Send a command to a Sonos device.

        Given the name of an action (a string as specified in the service
        description XML file) to be sent, and the relevant arguments as a list
        of (name, value) tuples, send the command to the Sonos device. Return
        a dict of {argument_name, value)} items or True on success. Raise
        an exception on failure.

        """

        headers, body = self.build_command(action, args)
        log.info("Sending %s %s to %s", action, args, self.soco.speaker_ip)
        log.debug("Sending %s, %s", headers, prettify(body))
        response = requests.post(
            self.base_url + self.control_url, headers=headers, data=body)
        log.debug("Received %s, %s", response.headers, response.content)
        status = response.status_code
        if status == 200:
            # The response is good. Get the output params, and return them.
            # NB an empty dict is a valid result. It just means that no
            # params are returned.
            result = self.unwrap_arguments(response.content) or True
            log.info(
                "Received status %s from %s", status, self.soco.speaker_ip)
            return result
        elif status == 500:
            # Internal server error. UPnP requires this to be returned if the
            # device does not like the action for some reason. The returned
            # content will be a SOAP Fault. Parse it and raise an error.
            try:
                self.handle_upnp_error(response.content)
            except Exception as e:
                log.exception(e.message)
                raise
        else:
            # Something else has gone wrong. Probably a network error. Let
            # Requests handle it
            response.raise_for_status()

    def handle_upnp_error(self, xml_error):
        """ Disect a UPnP error, and raise an appropriate exception

        xml_error is a string containing the body of the UPnP/SOAP Fault
        response. Raises an exception containing the error code

        """

        # An error code looks something like this:

        # HTTP/1.1 500 Internal Server Error
        # CONTENT-LENGTH: bytes in body
        # CONTENT-TYPE: text/xml; charset="utf-8"
        # DATE: when response was generated
        # EXT:
        # SERVER: OS/version UPnP/1.0 product/version

        # <?xml version="1.0"?>
        # <s:Envelope
        #   xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
        #   s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
        #   <s:Body>
        #       <s:Fault>
        #           <faultcode>s:Client</faultcode>
        #           <faultstring>UPnPError</faultstring>
        #           <detail>
        #               <UPnPError xmlns="urn:schemas-upnp-org:control-1-0">
        #                   <errorCode>error code</errorCode>
        #                   <errorDescription>error string</errorDescription>
        #               </UPnPError>
        #           </detail>
        #       </s:Fault>
        #   </s:Body>
        # </s:Envelope>
        #
        # All that matters for our purposes is the errorCode.
        # errorDescription is not required, and Sonos does not seem to use it.

        error = ET.fromstring(xml_error)
        log.debug("Error %s", xml_error)
        error_code = error.findtext(
            './/{urn:schemas-upnp-org:control-1-0}errorCode')
        if error_code is not None:
            description = self.UPNP_ERRORS.get(int(error_code), '')
            raise Exception('UPnP Error {} received: {} from {}'.format(
                error_code, description, self.soco.speaker_ip))
        else:
            # Unknown error, so just return the entire response
            log.error("Unknown error received from %s", self.soco.speaker_ip)
            raise Exception(xml_error)

    def iter_actions(self):
        """ Yield the service's actions with their in_arguments (ie parameters
        to pass to the action) and out_arguments (ie returned values).

        Each action is an Action namedtuple, consisting of action_name (a
        string), in_args (a list of Argument namedtuples consisting of name and
        argtype), and out_args (ditto), eg:

        Action(name='SetFormat',
            in_args=[Argument(name='DesiredTimeFormat', vartype='string'),
                     Argument(name='DesiredDateFormat', vartype='string')],
            out_args=[]) """

        # TODO: Provide for Allowed value list, Allowed value range,
        # default value
        ns = '{urn:schemas-upnp-org:service-1-0}'
        scpd_body = requests.get(self.base_url + self.scpd_url).content
        tree = ET.fromstring(scpd_body)
        # parse the state variables to get the relevant variable types
        statevars = tree.iterfind('.//{}stateVariable'.format(ns))
        vartypes = {}
        for s in statevars:
            name = s.findtext('{}name'.format(ns))
            vartypes[name] = s.findtext('{}dataType'.format(ns))
        # find all the actions
        actions = tree.iterfind('.//{}action'.format(ns))
        for i in actions:
            action_name = i.findtext('{}name'.format(ns))
            args_iter = i.iterfind('.//{}argument'.format(ns))
            in_args = []
            out_args = []
            for a in args_iter:
                arg_name = a.findtext('{}name'.format(ns))
                direction = a.findtext('{}direction'.format(ns))
                related_variable = a.findtext(
                    '{}relatedStateVariable'.format(ns))
                vartype = vartypes[related_variable]
                if direction == "in":
                    in_args.append(Argument(arg_name, vartype))
                else:
                    out_args.append(Argument(arg_name, vartype))
            yield Action(action_name, in_args, out_args)


class AlarmClock(Service):
    def __init__(self, soco):
        super(AlarmClock, self).__init__(soco)


class MusicServices(Service):
    def __init__(self, soco):
        super(MusicServices, self).__init__(soco)


class DeviceProperties(Service):
    def __init__(self, soco):
        super(DeviceProperties, self).__init__(soco)


class SystemProperties(Service):
    def __init__(self, soco):
        super(SystemProperties, self).__init__(soco)


class ZoneGroupTopology(Service):
    def __init__(self, soco):
        super(ZoneGroupTopology, self).__init__(soco)


class GroupManagement(Service):
    def __init__(self, soco):
        super(GroupManagement, self).__init__(soco)


class QPlay(Service):
    """ Tencent QPlay """
    def __init__(self, soco):
        super(QPlay, self).__init__(soco)


class ContentDirectory(Service):
    def __init__(self, soco):
        super(ContentDirectory, self).__init__(soco)
        self.control_url = "/MediaServer/ContentDirectory/Control"
        # For error codes, see table 2.7.16 in
        # http://upnp.org/specs/av/UPnP-av-ContentDirectory-v1-Service.pdf
        self.UPNP_ERRORS.update({
            701: 'No such object',
            702: 'Invalid CurrentTagValue',
            703: 'Invalid NewTagValue',
            704: 'Required tag',
            705: 'Read only tag',
            706: 'Parameter Mismatch',
            708: 'Unsupported or invalid search criteria',
            709: 'Unsupported or invalid sort criteria',
            710: 'No such container',
            711: 'Restricted object',
            712: 'Bad metadata',
            713: 'Restricted parent object',
            714: 'No such source resource',
            715: 'Resource access denied',
            716: 'Transfer busy',
            717: 'No such file transfer',
            718: 'No such destination resource',
            719: 'Destination resource access denied',
            720: 'Cannot process the request',
        })


class MS_ConnectionManager(Service):
    def __init__(self, soco):
        super(MS_ConnectionManager, self).__init__(soco)
        self.service_type = "ConnectionManager"
        self.control_url = "/MediaServer/ConnectionManager/Control"


class RenderingControl(Service):
    def __init__(self, soco):
        super(RenderingControl, self).__init__(soco)
        self.control_url = "/MediaRenderer/RenderingControl/Control"


class MR_ConnectionManager(Service):
    def __init__(self, soco):
        super(MR_ConnectionManager, self).__init__(soco)
        self.service_type = "ConnectionManager"
        self.control_url = "/MediaRenderer/ConnectionManager/Control"


class AVTransport(Service):
    def __init__(self, soco):
        super(AVTransport, self).__init__(soco)
        self.control_url = "/MediaRenderer/AVTransport/Control"
        # For error codes, see
        # http://upnp.org/specs/av/UPnP-av-AVTransport-v1-Service.pdf
        self.UPNP_ERRORS.update({
            701: 'Transition not available',
            702: 'No contents',
            703: 'Read error',
            704: 'Format not supported for playback',
            705: 'Transport is locked',
            706: 'Write error',
            707: 'Media is protected or not writeable',
            708: 'Format not supported for recording',
            709: 'Media is full',
            710: 'Seek mode not supported',
            711: 'Illegal seek target',
            712: 'Play mode not supported',
            713: 'Record quality not supported',
            714: 'Illegal MIME-Type',
            715: 'Content "BUSY"',
            716: 'Resource Not found',
            717: 'Play speed not supported',
            718: 'Invalid InstanceID',
            737: 'No DNS Server',
            738: 'Bad Domain Name',
            739: 'Server Error',
            })


class Queue(Service):
    def __init__(self, soco):
        super(Queue, self).__init__(soco)
        self.control_url = "/MediaRenderer/Queue/Control"


class GroupRenderingControl(Service):
    def __init__(self, soco):
        super(GroupRenderingControl, self).__init__(soco)
        self.control_url = "/MediaRenderer/GroupRenderingControl/Control"
