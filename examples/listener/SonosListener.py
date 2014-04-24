import gevent
import soco
import lxml.etree
import HTMLParser
import sys

def callback(data):
    p = HTMLParser.HTMLParser()
    datastr = p.unescape(data)
    root = lxml.etree.fromstring(datastr)
    r = root.xpath('//d:TransportState',
                   namespaces={'d':"urn:schemas-upnp-org:metadata-1-0/AVT/"})
    stat = r[0].get('val')
    if stat == 'PLAYING':
        print('zone is playing')
    elif (stat == 'STOPPED') or (stat == 'PAUSED_PLAYBACK'):
        print('zone is stopped or at least paused')


if __name__ == '__main__':
    # find the rooms
    ips = soco.SonosDiscovery().get_speaker_ips()
    zone_names = {}
    for ip in ips:
        x = soco.SoCo(ip)
        zone_names[ip] = x.get_speaker_info()['zone_name']

    # identify the room to listen to
    if len(sys.argv) < 2:
        print('specify which zone to listen to')
        for k, v in zone_names.iteritems():
            print(k, v)
    else:
        print(str(sys.argv))
        s = soco.Events(sys.argv[1]) # Sonos IP of interest
        s.subscribe(callback)
        s.start()
        # Keep the program running listen for notifications (via callback).
        gevent.wait()
        s.stop()
        print 'Shutting down = we should have never got here...'
