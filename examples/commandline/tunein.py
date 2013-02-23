#!/usr/bin/env python

import sys
import time


from soco import SoCo
from soco import SonosDiscovery
#from zone import SonosZone


meta_template = '&lt;DIDL-Lite xmlns:dc=&quot;http://purl.org/dc/elements/1.1/&quot; xmlns:upnp=&quot;urn:schemas-upnp-org:metadata-1-0/upnp/&quot; xmlns:r=&quot;urn:schemas-rinconnetworks-com:metadata-1-0/&quot; xmlns=&quot;urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/&quot;&gt;&lt;item id=&quot;R:0/0/0&quot; parentID=&quot;R:0/0&quot; restricted=&quot;true&quot;&gt;&lt;dc:title&gt;{title}&lt;/dc:title&gt;&lt;upnp:class&gt;object.item.audioItem.audioBroadcast&lt;/upnp:class&gt;&lt;desc id=&quot;cdudn&quot; nameSpace=&quot;urn:schemas-rinconnetworks-com:metadata-1-0/&quot;&gt;{service}&lt;/desc&gt;&lt;/item&gt;&lt;/DIDL-Lite&gt;'

tunein_service = 'SA_RINCON65031_'

if __name__ == '__main__':

    if (len(sys.argv) > 1):
      speaker_ip = sys.argv[1]

    if (len(sys.argv) == 3):
      preset = int(sys.argv[2]) - 1
      limit = 1
    else:
      preset = 0
      limit = 12

    mySonos = SoCo(speaker_ip)

    if mySonos:
        stations = mySonos.get_favorite_radio_stations( preset, limit)
        print 'returned %s of a possible %s radio stations:' % (stations['returned'], stations['total'])
	for fave in stations['favorites']:    
	    print fave['title']

            uri = fave['uri']
            # TODO seems at least & needs to be escaped - should move this to play_uri and maybe escape other chars.
            uri = uri.replace('&', '&amp;')

            metadata = meta_template.format(title='', service=tunein_service)

            print mySonos.play_uri( uri, metadata)

            if (len(sys.argv) == 2):
               time.sleep( 10)



