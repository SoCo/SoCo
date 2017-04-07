import soco

from soco.utils import prettify
from soco.xml import XML
from soco import didl_lite
from soco.didl_lite import Element

import logging

logging.basicConfig()
l = logging.getLogger('soco.didl_lite')
l.setLevel(logging.DEBUG)

# pick a device
device = list(soco.discover())[0]


# Get all top level items - use ObjectID=0
response = device.contentDirectory.Browse([
    ('ObjectID', '0'),
    ('BrowseFlag', 'BrowseDirectChildren'),
    ('Filter', '*'),
    ('StartingIndex', 0),
    ('RequestedCount', 100),
    ('SortCriteria', '')
    ])
result = response['Result']

o = Element.from_string(result)
for item in o.get_items():
    print item.title + ": " + item.object_id


print "\nTRACKS"
# Get all the tracks from the current queue
response = device.contentDirectory.Browse([
    ('ObjectID', 'Q:0'),
    ('BrowseFlag', 'BrowseDirectChildren'),
    ('Filter', '*'),
    ('StartingIndex', 0),
    ('RequestedCount', 100),
    ('SortCriteria', '')
    ])
result = response['Result']

print prettify(result) # <-- uncomment this to print returned DIDL
o = Element.from_string(result)
for item in o.get_items():
    print item.creator
    print item.title + ": " + item.albums[0]
    print item.uri


# Now do the same for Shares

response = device.contentDirectory.Browse([
    ('ObjectID', 'S:'),
    ('BrowseFlag', 'BrowseDirectChildren'),
    ('Filter', '*'),
    ('StartingIndex', 0),
    ('RequestedCount', 100),
    ('SortCriteria', '')
    ])
result = response['Result']

print "\nSHARES"
o = Element.from_string(result)
for item in o.get_items():
    print str(item)
    print item.title
