# -*- coding: utf-8 -*-

""" A transport for pysimplesoap that uses the requests library
"""

from __future__ import unicode_literals

from pysimplesoap import transport
import requests

# pysimplesoap cannot handle the gzipped SOAP which eg Spotify returns. But
# requests can. So we need a custom transport for pysimplesoap which uses
# requests rather than urllib2


class _requestsTransport(transport.TransportBase):

    " A transport for pysimplesoap that uses the requests library"

    def __init__(self, timeout, proxy=None, cacert=None, sessions=False):
        self.timeout = timeout
        self.proxy = proxy or {}
        self.cacert = cacert
        self.sessions = sessions

    def request(self, url, method, body, headers):
        """ Execute the desired request"""
        if method == 'POST':
            result = requests.post(url, data=body, headers=headers,
                                   timeout=self.timeout, proxies=self.proxy)
        elif method == 'GET':
            result = requests.get(url, headers=headers,
                                  timeout=self.timeout, proxies=self.proxy)
        else:
            raise Exception('Unknown request method')
        return {}, result.text.encode('ascii', 'replace')

# pylint: disable=protected-access
transport._http_connectors['requests'] = _requestsTransport
transport.set_http_wrapper('requests')
