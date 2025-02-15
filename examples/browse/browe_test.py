from soco import SoCo
my_zone = SoCo('192.168.50.180')

print("Player Name" + my_zone.player_name)

print(my_zone.contentDirectory.additional_headers)

my_zone.contentDirectory.additional_headers = {
    "X-Sonos-Api-Key" : "api_key",
    "X-Sonos-Corr-Id" : "corr_id",
    "X-SONOS-TARGET-UDN" : "udn"
}

r = my_zone.contentDirectory.Browse([('ObjectID', 'FV:2'),
                                    ('BrowseFlag', 'BrowseDirectChildren'),
                                    ('Filter', 'dc:title,res,dc:creator,upnp:artist,upnp:album,upnp:albumArtURI'),
                                    ('StartingIndex', '0'),
                                    ('RequestedCount', '100'),
                                    ('SortCriteria', '')])

print(r)
