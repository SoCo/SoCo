# -*- coding: utf-8 -*-
# pylint: disable=fixme, invalid-name

"""Classes representing Sonos UPnP services.

>>> import soco
>>> device = soco.SoCo('192.168.1.102')
>>> print(RenderingControl(device).GetMute([('InstanceID', 0),
...     ('Channel', 'Master')]))
{'CurrentMute': '0'}
>>> r = ContentDirectory(device).Browse([
...    ('ObjectID', 'Q:0'),
...    ('BrowseFlag', 'BrowseDirectChildren'),
...    ('Filter', '*'),
...    ('StartingIndex', '0'),
...    ('RequestedCount', '100'),
...    ('SortCriteria', '')
...    ])
>>> print(r['Result'])
<?xml version="1.0" ?><DIDL-Lite xmlns="urn:schemas-upnp-org:metadata ...
>>> for action, in_args, out_args in AlarmClock(device).iter_actions():
...    print(action, in_args, out_args)
...
SetFormat [Argument(name='DesiredTimeFormat', vartype='string'), Argument(
name='DesiredDateFormat', vartype='string')] []
GetFormat [] [Argument(name='CurrentTimeFormat', vartype='string'),
Argument(name='CurrentDateFormat', vartype='string')] ...
"""

# UPnP Spec at http://upnp.org/specs/arch/UPnP-arch-DeviceArchitecture-v1.0.pdf

from __future__ import (
    absolute_import, unicode_literals
)

import logging
from collections import namedtuple
from xml.sax.saxutils import escape

import requests

from .cache import Cache
from .events import Subscription
from .exceptions import (
    SoCoUPnPException, UnknownSoCoException
)
from .utils import prettify
from .xml import XML, illegal_xml_re, PARSEERROR

# UNICODE NOTE
# UPnP requires all XML to be transmitted/received with utf-8 encoding. All
# strings used in this module are unicode. The Requests library should take
# care of all of the necessary encoding (on sending) and decoding (on
# receiving) for us, provided that we specify the correct encoding headers
# (which, hopefully, we do).
# But since ElementTree seems to prefer being fed bytes to unicode, at least
# for Python 2.x, we have to encode strings specifically before using it. see
# http://bugs.python.org/issue11033 TODO: Keep an eye on this when it comes to
# Python 3 compatibility


log = logging.getLogger(__name__)  # pylint: disable=C0103
# logging.basicConfig()
# log.setLevel(logging.INFO)

#: A UPnP Action and its arguments.
Action = namedtuple('Action', 'name, in_args, out_args')
#: A UPnP Argument and its type.
Argument = namedtuple('Argument', 'name, vartype')

# A shared cache for ZoneGroupState. Each zone has the same info, so when a
# SoCo instance is asked for group info, we can cache it and return it when
# another instance is asked. To do this we need a cache to be shared between
# instances
zone_group_state_shared_cache = Cache()


# pylint: disable=too-many-instance-attributes
class Service(object):

    """A class representing a UPnP service.

    This is the base class for all Sonos Service classes. This class has a
    dynamic method dispatcher. Calls to methods which are not explicitly
    defined here are dispatched automatically to the service action with the
    same name.
    """
    # pylint: disable=bad-continuation
    soap_body_template = (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
        ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            '<s:Body>'
                '<u:{action} xmlns:u="urn:schemas-upnp-org:service:'
                    '{service_type}:{version}">'
                    '{arguments}'
                '</u:{action}>'
            '</s:Body>'
        '</s:Envelope>')  # noqa PEP8

    def __init__(self, soco):
        """
        Args:
            soco (SoCo): A `SoCo` instance to which the UPnP Actions will be
                sent
        """

        #: `SoCo`: The `SoCo` instance to which UPnP Actions are sent
        self.soco = soco
        # Some defaults. Some or all these will need to be overridden
        # specifically in a sub-class. There is other information we could
        # record, but this will do for the moment. Info about a Sonos device is
        # available at <IP_address>/xml/device_description.xml in the
        # <service> tags

        #: str: The UPnP service type.
        self.service_type = self.__class__.__name__
        #: str: The UPnP service version.
        self.version = 1
        self.service_id = self.service_type
        #: str: The base URL for sending UPnP Actions.
        self.base_url = 'http://{0}:1400'.format(self.soco.ip_address)
        #: str: The UPnP Control URL.
        self.control_url = '/{0}/Control'.format(self.service_type)
        #: str: The service control protocol description URL.
        self.scpd_url = '/xml/{0}{1}.xml'.format(
            self.service_type, self.version)
        #: str: The service eventing subscription URL.
        self.event_subscription_url = '/{0}/Event'.format(self.service_type)
        #: A cache for storing the result of network calls. By default, this is
        #: a `TimedCache` with a default timeout=0.
        self.cache = Cache(default_timeout=0)

        # From table 3.3 in
        # http://upnp.org/specs/arch/UPnP-arch-DeviceArchitecture-v1.1.pdf
        # This list may not be complete, but should be good enough to be going
        # on with.  Error codes between 700-799 are defined for particular
        # services, and may be overriden in subclasses. Error codes >800
        # are generally SONOS specific. NB It may well be that SONOS does not
        # use some of these error codes.

        # pylint: disable=invalid-name
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
        """Called when a method on the instance cannot be found.

        Causes an action to be sent to UPnP server. See also
        `object.__getattr__`.

        Args:
            action (str): The name of the unknown method.
        Returns:
            callable: The callable to be invoked. .
        """

        # Define a function to be invoked as the method, which calls
        # send_command.
        def _dispatcher(self, *args, **kwargs):
            """Dispatch to send_command."""
            return self.send_command(action, *args, **kwargs)

        # rename the function so it appears to be the called method. We
        # probably don't need this, but it doesn't harm
        _dispatcher.__name__ = action

        # _dispatcher is now an unbound menthod, but we need a bound method.
        # This turns an unbound method into a bound method (i.e. one that
        # takes self - an instance of the class - as the first parameter)
        # pylint: disable=no-member
        method = _dispatcher.__get__(self, self.__class__)
        # Now we have a bound method, we cache it on this instance, so that
        # next time we don't have to go through this again
        setattr(self, action, method)
        log.debug("Dispatching method %s", action)

        # return our new bound method, which will be called by Python
        return method

    @staticmethod
    def wrap_arguments(args=None):
        """Wrap a list of tuples in xml ready to pass into a SOAP request.

        Args:
            args (list):  a list of (name, value) tuples specifying the
                name of each argument and its value, eg
                ``[('InstanceID', 0), ('Speed', 1)]``. The value
                can be a string or something with a string representation. The
                arguments are escaped and wrapped in <name> and <value> tags.

        Example:

            >>> from soco import SoCo
            >>> device = SoCo('192.168.1.101')
            >>> s = Service(device)
            >>> print(s.wrap_arguments([('InstanceID', 0), ('Speed', 1)]))
            <InstanceID>0</InstanceID><Speed>1</Speed>'
            """
        if args is None:
            args = []

        tags = []
        for name, value in args:
            tag = "<{name}>{value}</{name}>".format(
                name=name, value=escape("%s" % value, {'"': "&quot;"}))
            # % converts to unicode because we are using unicode literals.
            # Avoids use of 'unicode' function which does not exist in python 3
            tags.append(tag)

        xml = "".join(tags)
        return xml

    @staticmethod
    def unwrap_arguments(xml_response):
        """Extract arguments and their values from a SOAP response.

        Args:
            xml_response (str):  SOAP/xml response text (unicode,
                not utf-8).
        Returns:
             dict: a dict of ``{argument_name, value)}`` items.
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
        try:
            tree = XML.fromstring(xml_response)
        except PARSEERROR:
            # Try to filter illegal xml chars (as unicode), in case that is
            # the reason for the parse error
            # NOTE: The PARSERROR used here is a Python 2.6 compat trick in
            # our xml module. If we ever drop support for Python 2.6 it should
            # be replaced with a simple XML.ParseError and the hack in .xml
            # removed
            filtered = illegal_xml_re.sub('', xml_response.decode('utf-8'))\
                                     .encode('utf-8')
            tree = XML.fromstring(filtered)

        # Get the first child of the <Body> tag which will be
        # <{actionNameResponse}> (depends on what actionName is). Turn the
        # children of this into a {tagname, content} dict. XML unescaping
        # is carried out for us by elementree.
        action_response = tree.find(
            "{http://schemas.xmlsoap.org/soap/envelope/}Body")[0]
        return dict((i.tag, i.text or "") for i in action_response)

    def build_command(self, action, args=None):
        """Build a SOAP request.

        Args:
            action (str): the name of an action (a string as specified in the
                service description XML file) to be sent.
            args (list, optional): Relevant arguments as a list of (name,
                value) tuples.

        Returns:
            tuple: a tuple containing the POST headers (as a dict) and a
                string containing the relevant SOAP body. Does not set
                content-length, or host headers, which are completed upon
                sending.
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
        body = self.soap_body_template.format(
            arguments=arguments, action=action, service_type=self.service_type,
            version=self.version)
        soap_action_template = \
            "urn:schemas-upnp-org:service:{service_type}:{version}#{action}"
        soap_action = soap_action_template.format(
            service_type=self.service_type, version=self.version,
            action=action)
        headers = {'Content-Type': 'text/xml; charset="utf-8"',
                   'SOAPACTION': soap_action}
        # Note that although we set the charset to utf-8 here, in fact the
        # body is still unicode. It will only be converted to bytes when it
        # is set over the network
        return (headers, body)

    def send_command(self, action, args=None, cache=None, cache_timeout=None):
        """Send a command to a Sonos device.

        Args:
            action (str): the name of an action (a string as specified in the
                service description XML file) to be sent.
            args (list, optional): Relevant arguments as a list of (name,
                value) tuples.
            cache (Cache): A cache is operated so that the result will be
                stored for up to ``cache_timeout`` seconds, and a subsequent
                call with the same arguments within that period will be
                returned from the cache, saving a further network call. The
                cache may be invalidated or even primed from another thread
                (for example if a UPnP event is received to indicate that
                the state of the Sonos device has changed). If
                ``cache_timeout`` is missing or `None`, the cache will use a
                default value (which may be 0 - see `cache`). By default,
                the cache identified by the service's `cache` attribute will
                be used, but a different cache object may be specified in
                the `cache` parameter.

        Returns:
             dict: a dict of ``{argument_name, value)}`` items.

        Raises:
            `SoCoUPnPException`: if a SOAP error occurs.
            `UnknownSoCoException`: if an unknonwn UPnP error occurs.
            `requests.exceptions.HTTPError`: if an http error.

        """
        if cache is None:
            cache = self.cache
        result = cache.get(action, args)
        if result is not None:
            log.debug("Cache hit")
            return result
        # Cache miss, so go ahead and make a network call
        headers, body = self.build_command(action, args)
        log.info("Sending %s %s to %s", action, args, self.soco.ip_address)
        log.debug("Sending %s, %s", headers, prettify(body))
        # Convert the body to bytes, and send it.
        response = requests.post(
            self.base_url + self.control_url,
            headers=headers,
            data=body.encode('utf-8')
        )
        log.debug("Received %s, %s", response.headers, response.text)
        status = response.status_code
        log.info(
            "Received status %s from %s", status, self.soco.ip_address)
        if status == 200:
            # The response is good. Get the output params, and return them.
            # NB an empty dict is a valid result. It just means that no
            # params are returned. By using response.text, we rely upon
            # the requests library to convert to unicode for us.
            result = self.unwrap_arguments(response.text) or True
            # Store in the cache. There is no need to do this if there was an
            # error, since we would want to try a network call again.
            cache.put(result, action, args, timeout=cache_timeout)
            return result
        elif status == 500:
            # Internal server error. UPnP requires this to be returned if the
            # device does not like the action for some reason. The returned
            # content will be a SOAP Fault. Parse it and raise an error.
            try:
                self.handle_upnp_error(response.text)
            except Exception as exc:
                log.exception(str(exc))
                raise
        else:
            # Something else has gone wrong. Probably a network error. Let
            # Requests handle it
            response.raise_for_status()

    def handle_upnp_error(self, xml_error):
        """Disect a UPnP error, and raise an appropriate exception.

        Args:
            xml_error (str):  a unicode string containing the body of the
                UPnP/SOAP Fault response. Raises an exception containing the
                error code.
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

        # NB need to encode unicode strings before passing to ElementTree
        xml_error = xml_error.encode('utf-8')
        error = XML.fromstring(xml_error)
        log.debug("Error %s", xml_error)
        error_code = error.findtext(
            './/{urn:schemas-upnp-org:control-1-0}errorCode')
        if error_code is not None:
            description = self.UPNP_ERRORS.get(int(error_code), '')
            raise SoCoUPnPException(
                message='UPnP Error {0} received: {1} from {2}'.format(
                    error_code, description, self.soco.ip_address),
                error_code=error_code,
                error_description=description,
                error_xml=xml_error
            )
        else:
            # Unknown error, so just return the entire response
            log.error("Unknown error received from %s", self.soco.ip_address)
            raise UnknownSoCoException(xml_error)

    def subscribe(
            self, requested_timeout=None, auto_renew=False, event_queue=None):
        """Subscribe to the service's events.

        Args:
            requested_timeout (int, optional): If requested_timeout is
                provided, a subscription valid for that
                number of seconds will be requested, but not guaranteed. Check
                `Subscription.timeout` on return to find out what period of
                validity is actually allocated.
            auto_renew (bool): If auto_renew is `True`, the subscription will
                automatically be renewed just before it expires, if possible.
                Default is `False`.

            event_queue (:class:`~queue.Queue`): a thread-safe queue object on
                which received events will be put. If not specified,
                a (:class:`~queue.Queue`) will be created and used.

        Returns:
            `Subscription`: an insance of `Subscription`, representing
                the new subscription.

        To unsubscribe, call the `unsubscribe` method on the returned object.
        """
        subscription = Subscription(
            self, event_queue)
        subscription.subscribe(
            requested_timeout=requested_timeout, auto_renew=auto_renew)
        return subscription

    def _update_cache_on_event(self, event):
        """Update the cache when an event is received.

        This will be called before an event is put onto the event queue. Events
        will often indicate that the Sonos device's state has changed, so this
        opportunity is made available for the service to update its cache. The
        event will be put onto the event queue once this method returns.

        `event` is an Event namedtuple: ('sid', 'seq', 'service', 'variables')

        ..  warning:: This method will not be called from the main thread but
            by one or more threads, which handle the events as they come in.
            You *must not* access any class, instance or global variables
            without appropriate locks. Treat all parameters passed to this
            method as read only.
        """
        pass

    def iter_actions(self):
        """Yield the service's actions with their arguments.

        Yields:
            `Action`: the next action.

        Each action is an Action namedtuple, consisting of action_name
        (a string), in_args (a list of Argument namedtuples consisting of name
        and argtype), and out_args (ditto), eg::

            Action(
                name='SetFormat',
                in_args=[
                    Argument(name='DesiredTimeFormat', vartype='string'),
                    Argument(name='DesiredDateFormat', vartype='string')],
                out_args=[]
            )
        """

        # pylint: disable=too-many-locals
        # TODO: Provide for Allowed value list, Allowed value range,
        # default value
        # pylint: disable=invalid-name
        ns = '{urn:schemas-upnp-org:service-1-0}'
        # get the scpd body as bytes, and feed directly to elementtree
        # which likes to receive bytes
        scpd_body = requests.get(self.base_url + self.scpd_url).content
        tree = XML.fromstring(scpd_body)
        # parse the state variables to get the relevant variable types
        vartypes = {}
        srvStateTables = tree.findall('{0}serviceStateTable'.format(ns))
        for srvStateTable in srvStateTables:
            statevars = srvStateTable.findall('{0}stateVariable'.format(ns))
            for state in statevars:
                name = state.findtext('{0}name'.format(ns))
                vartypes[name] = state.findtext('{0}dataType'.format(ns))
        # find all the actions
        actionLists = tree.findall('{0}actionList'.format(ns))
        for actionList in actionLists:
            actions = actionList.findall('{0}action'.format(ns))
            for i in actions:
                action_name = i.findtext('{0}name'.format(ns))
                argLists = i.findall('{0}argumentList'.format(ns))
                for argList in argLists:
                    args_iter = argList.findall('{0}argument'.format(ns))
                    in_args = []
                    out_args = []
                    for arg in args_iter:
                        arg_name = arg.findtext('{0}name'.format(ns))
                        direction = arg.findtext('{0}direction'.format(ns))
                        related_variable = arg.findtext(
                            '{0}relatedStateVariable'.format(ns))
                        vartype = vartypes[related_variable]
                        if direction == "in":
                            in_args.append(Argument(arg_name, vartype))
                        else:
                            out_args.append(Argument(arg_name, vartype))
                    yield Action(action_name, in_args, out_args)

    def iter_event_vars(self):
        """Yield the services eventable variables.

        Yields:
            `tuple`: a tuple of (variable name, data type).
        """

        # pylint: disable=invalid-name
        ns = '{urn:schemas-upnp-org:service-1-0}'
        scpd_body = requests.get(self.base_url + self.scpd_url).text
        tree = XML.fromstring(scpd_body.encode('utf-8'))
        # parse the state variables to get the relevant variable types
        statevars = tree.findall('{0}stateVariable'.format(ns))
        for state in statevars:
            # We are only interested if 'sendEvents' is 'yes', i.e this
            # is an eventable variable
            if state.attrib['sendEvents'] == "yes":
                name = state.findtext('{0}name'.format(ns))
                vartype = state.findtext('{0}dataType'.format(ns))
                yield (name, vartype)


class AlarmClock(Service):

    """Sonos alarm service, for setting and getting time and alarms."""

    def __init__(self, soco):
        super(AlarmClock, self).__init__(soco)
        self.UPNP_ERRORS.update(
            {
                801: 'Already an alarm for this time',
            })


class MusicServices(Service):

    """Sonos music services service, for functions related to 3rd party music
    services."""

    def __init__(self, soco):
        super(MusicServices, self).__init__(soco)


class DeviceProperties(Service):

    """Sonos device properties service, for functions relating to zones, LED
    state, stereo pairs etc."""

    def __init__(self, soco):
        super(DeviceProperties, self).__init__(soco)


class SystemProperties(Service):

    """Sonos system properties service, for functions relating to
    authentication etc."""

    def __init__(self, soco):
        super(SystemProperties, self).__init__(soco)


class ZoneGroupTopology(Service):

    """Sonos zone group topology service, for functions relating to network
    topology, diagnostics and updates."""

    def __init__(self, soco):
        super(ZoneGroupTopology, self).__init__(soco)

    def GetZoneGroupState(self, *args, **kwargs):
        """Overrides default handling to use the global shared zone group state
        cache, unless another cache is specified."""
        kwargs['cache'] = kwargs.get('cache', zone_group_state_shared_cache)
        return self.send_command('GetZoneGroupState', *args, **kwargs)


class GroupManagement(Service):

    """Sonos group management service, for services relating to groups."""

    def __init__(self, soco):
        super(GroupManagement, self).__init__(soco)


class QPlay(Service):

    """Sonos Tencent QPlay service (a Chinese music service)"""

    def __init__(self, soco):
        super(QPlay, self).__init__(soco)


class ContentDirectory(Service):

    """UPnP standard Content Directory service, for functions relating to
    browsing, searching and listing available music."""

    def __init__(self, soco):
        super(ContentDirectory, self).__init__(soco)
        self.control_url = "/MediaServer/ContentDirectory/Control"
        self.event_subscription_url = "/MediaServer/ContentDirectory/Event"
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


class MS_ConnectionManager(Service):  # pylint: disable=invalid-name

    """UPnP standard connection manager service for the media server."""

    def __init__(self, soco):
        super(MS_ConnectionManager, self).__init__(soco)
        self.service_type = "ConnectionManager"
        self.control_url = "/MediaServer/ConnectionManager/Control"
        self.event_subscription_url = "/MediaServer/ConnectionManager/Event"


class RenderingControl(Service):

    """UPnP standard rendering control service, for functions relating to
    playback rendering, eg bass, treble, volume and EQ."""

    def __init__(self, soco):
        super(RenderingControl, self).__init__(soco)
        self.control_url = "/MediaRenderer/RenderingControl/Control"
        self.event_subscription_url = "/MediaRenderer/RenderingControl/Event"


class MR_ConnectionManager(Service):  # pylint: disable=invalid-name

    """UPnP standard connection manager service for the media renderer."""

    def __init__(self, soco):
        super(MR_ConnectionManager, self).__init__(soco)
        self.service_type = "ConnectionManager"
        self.control_url = "/MediaRenderer/ConnectionManager/Control"
        self.event_subscription_url = "/MediaRenderer/ConnectionManager/Event"


class AVTransport(Service):

    """UPnP standard AV Transport service, for functions relating to transport
    management, eg play, stop, seek, playlists etc."""

    def __init__(self, soco):
        super(AVTransport, self).__init__(soco)
        self.control_url = "/MediaRenderer/AVTransport/Control"
        self.event_subscription_url = "/MediaRenderer/AVTransport/Event"
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

    """Sonos queue service, for functions relating to queue management, saving
    queues etc."""

    def __init__(self, soco):
        super(Queue, self).__init__(soco)
        self.control_url = "/MediaRenderer/Queue/Control"
        self.event_subscription_url = "/MediaRenderer/Queue/Event"


class GroupRenderingControl(Service):

    """Sonos group rendering control service, for functions relating to group
    volume etc."""

    def __init__(self, soco):
        super(GroupRenderingControl, self).__init__(soco)
        self.control_url = "/MediaRenderer/GroupRenderingControl/Control"
        self.event_subscription_url = \
            "/MediaRenderer/GroupRenderingControl/Event"
