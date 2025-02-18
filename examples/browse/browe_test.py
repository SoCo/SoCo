from soco import SoCo
my_zone = SoCo('192.168.1.180')

print("Player Name" + my_zone.player_name)

print(my_zone.contentDirectory.additional_headers)

r = my_zone.contentDirectory.Browse([('ObjectID', 'FV:2'),
                                    ('BrowseFlag', 'BrowseDirectChildren'),
                                    ('Filter', 'dc:title,res,dc:creator,upnp:artist,upnp:album,upnp:albumArtURI'),
                                    ('StartingIndex', '0'),
                                    ('RequestedCount', '100'),
                                    ('SortCriteria', '')])

print(r)
