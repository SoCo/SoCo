#!/usr/bin/env python

import sys
import time


from soco import SoCo
from soco import SonosDiscovery
#from zone import SonosZone


meta_template = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"><item id="R:0/0/0" parentID="R:0/0" restricted="true"><dc:title>{title}</dc:title><upnp:class>object.item.audioItem.audioBroadcast</upnp:class><desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">{service}</desc></item></DIDL-Lite>'

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

            metadata = meta_template.format(title=fave['title'], service=tunein_service)

            print mySonos.play_uri( uri, metadata)

            if (len(sys.argv) == 2):
               time.sleep( 10)



