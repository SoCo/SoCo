# -*- coding: utf-8 -*-

"""Music Library access."""

from __future__ import unicode_literals

import logging

from . import discovery
from .data_structures import (
    SearchResult,
    from_didl_string,
    DidlResource,
    DidlObject,
    DidlMusicAlbum
)
from .exceptions import SoCoUPnPException
from .utils import url_escape_path, really_unicode, camel_to_underscore

_LOG = logging.getLogger(__name__)

# pylint: disable=protected-access


class MusicLibrary(object):
    """The Music Library """

    # Key words used when performing searches
    SEARCH_TRANSLATION = {'artists': 'A:ARTIST',
                          'album_artists': 'A:ALBUMARTIST',
                          'albums': 'A:ALBUM',
                          'genres': 'A:GENRE',
                          'composers': 'A:COMPOSER',
                          'tracks': 'A:TRACKS',
                          'playlists': 'A:PLAYLISTS',
                          'share': 'S:',
                          'sonos_playlists': 'SQ:',
                          'categories': 'A:'}

    # pylint: disable=invalid-name
    def __init__(self, soco=None):
        """
         Args:
             soco (SoCo), optional: A SoCo instance to query for music library
             information. If None, or not supplied, a random SoCo will be used.
        """
        self.soco = soco if soco is not None else discovery.any_soco()
        self.contentDirectory = soco.contentDirectory

    def _build_album_art_full_uri(self, url):
        """Ensure an Album Art URI is an absolute URI.

        :param url: The album art URI
        """

        # Add on the full album art link, as the URI version
        # does not include the ipaddress
        if not url.startswith(('http:', 'https:')):
            url = 'http://' + self.soco.ip_address + ':1400' + url
        return url

    def get_artists(self, *args, **kwargs):
        """Convenience method for :py:meth:`get_music_library_information`
        with `search_type='artists'`. For details on remaining arguments refer
        to the docstring for that method.

        """
        args = tuple(['artists'] + list(args))
        return self.get_music_library_information(*args, **kwargs)

    def get_album_artists(self, *args, **kwargs):
        """Convenience method for :py:meth:`get_music_library_information`
        with `search_type='album_artists'`. For details on remaining arguments
        refer to the docstring for that method.

        """
        args = tuple(['album_artists'] + list(args))
        return self.get_music_library_information(*args, **kwargs)

    def get_albums(self, *args, **kwargs):
        """Convenience method for :py:meth:`get_music_library_information`
        with `search_type='albums'`. For details on remaining arguments refer
        to the docstring for that method.

        """
        args = tuple(['albums'] + list(args))
        return self.get_music_library_information(*args, **kwargs)

    def get_genres(self, *args, **kwargs):
        """ onvenience method for :py:meth:`get_music_library_information`
        with `search_type='genres'`. For details on remaining arguments refer
        to the docstring for that method.

        """
        args = tuple(['genres'] + list(args))
        return self.get_music_library_information(*args, **kwargs)

    def get_composers(self, *args, **kwargs):
        """Convenience method for :py:meth:`get_music_library_information`
        with `search_type='composers'`. For details on remaining arguments
        refer to the docstring for that method.

        """
        args = tuple(['composers'] + list(args))
        return self.get_music_library_information(*args, **kwargs)

    def get_tracks(self, *args, **kwargs):
        """Convenience method for :py:meth:`get_music_library_information`
        with `search_type='tracks'`. For details on remaining arguments refer
        to the docstring for that method.

        """
        args = tuple(['tracks'] + list(args))
        return self.get_music_library_information(*args, **kwargs)

    def get_playlists(self, *args, **kwargs):
        """Convenience method for :py:meth:`get_music_library_information`
        with `search_type='playlists'`. For details on remaining arguments
        refer to the docstring for that method.

        NOTE: The playlists that are referred to here are the playlist (files)
        imported from the music library, they are not the Sonos playlists.

        """
        args = tuple(['playlists'] + list(args))
        return self.get_music_library_information(*args, **kwargs)

        # pylint: disable=too-many-locals, too-many-arguments,
        # too-many-branches

    def get_music_library_information(self, search_type, start=0,
                                      max_items=100, full_album_art_uri=False,
                                      search_term=None, subcategories=None,
                                      complete_result=False):
        """Retrieve music information objects from the music library.

        This method is the main method to get music information items, like
        e.g. tracks, albums etc., from the music library with. It can be used
        in a few different ways:

        The **search_term** argument performs a fuzzy search on that string in
        the results, so e.g calling::

          get_music_library_items('artist', search_term='Metallica')

        will perform a fuzzy search for the term 'Metallica' among all the
        artists.

        Using the **subcategories** argument, will jump directly into that
        subcategory of the search and return results from there. So. e.g
        knowing that among the artist is one called 'Metallica', calling::

          get_music_library_items('artist', subcategories=['Metallica'])

        will jump directly into the 'Metallica' sub category and return the
        albums associated with Metallica and::

          get_music_library_items('artist', subcategories=['Metallica',
                                                           'Black'])

        will return the tracks of the album 'Black' by the artist 'Metallica'.
        The order of sub category types is: Genres->Artists->Albums->Tracks.
        It is also possible to combine the two, to perform a fuzzy search in a
        sub category.

        The **start**, **max_items** and **complete_result** arguments all
        has to do with paging of the results. Per default, the searches are
        always paged, because there is a limit to how many items we can get at
        a time. This paging is exposed to the user with the start and max_items
        arguments. So calling::

          get_music_library_items('artists', start=0, max_items=100)
          get_music_library_items('artists', start=100, max_items=100)

        will get the first and next 100 items, respectively. It is also
        possible to ask for all the elements at once::

          get_music_library_items('artists', complete_result=True)

        This will perform the paging internally and simply return all the
        items.

        :param search_type: The kind of information to retrieve. Can be one of:
            'artists', 'album_artists', 'albums', 'genres', 'composers',
            'tracks', 'share', 'sonos_playlists', and 'playlists', where
            playlists are the imported file based playlists from the
            music library
        :param start: Starting number of returned matches (zero based).
        :param max_items: Maximum number of returned matches. NOTE: The maximum
            may be restricted by the unit, presumably due to transfer
            size consideration, so check the returned number against the
            requested.
        :param full_album_art_uri: If the album art URI should include the
            IP address
        :param search_term: A string that will be used to perform a fuzzy
            search among the search results. If used in combination with
            subcategories, the fuzzy search will be performed in the
            subcategory
        :param subcategories: A list of strings that indicate one or more
            subcategories to dive into
        :param complete_result: Will disable paging (ignore start and
            max_items) and return all results for the search. WARNING! Getting
            e.g. all the tracks in a large collection might take some time.
        :returns: A :py:class:`~.soco.data_structures.SearchResult` object
        :raises: :py:class:`SoCoException` upon errors

        NOTE: The playlists that are returned with the 'playlists' search, are
        the playlists imported from (files in) the music library, they are not
        the Sonos playlists.

        The information about the which searches can be performed and the form
        of the query has been gathered from the Janos project:
        http://sourceforge.net/projects/janos/ Props to the authors of that
        project.

        """
        search = self.SEARCH_TRANSLATION[search_type]

        # Add sub categories
        if subcategories is not None:
            for category in subcategories:
                search += '/' + url_escape_path(really_unicode(category))
        # Add fuzzy search
        if search_term is not None:
            search += ':' + url_escape_path(really_unicode(search_term))

        item_list = []
        metadata = {'total_matches': 100000}
        while len(item_list) < metadata['total_matches']:
            # Change start and max for complete searches
            if complete_result:
                start, max_items = len(item_list), 100000

            # Try and get this batch of results
            try:
                response, metadata = \
                    self._music_lib_search(search, start, max_items)
            except SoCoUPnPException as exception:
                # 'No such object' UPnP errors
                if exception.error_code == '701':
                    return SearchResult([], search_type, 0, 0, None)
                else:
                    raise exception

            # Parse the results
            items = from_didl_string(response['Result'])
            for item in items:
                # Check if the album art URI should be fully qualified
                if full_album_art_uri:
                    self.soco._update_album_art_to_full_uri(item)
                # Append the item to the list
                item_list.append(item)

            # If we are not after the complete results, the stop after 1
            # iteration
            if not complete_result:
                break

        metadata['search_type'] = search_type
        if complete_result:
            metadata['number_returned'] = len(item_list)

        # pylint: disable=star-args
        return SearchResult(item_list, **metadata)

    def browse(self, ml_item=None, start=0, max_items=100,
               full_album_art_uri=False, search_term=None, subcategories=None):
        """Browse (get sub-elements) a music library item.

        :param ml_item: The MusicLibraryItem to browse, if left out or passed
            None, the items at the base level will be returned
        :type ml_item: MusicLibraryItem
        :param start: The starting index of the results
        :type start: int
        :param max_items: The maximum number of items to return
        :type max_items: int
        :param full_album_art_uri: If the album art URI should include the IP
            address
        :type full_album_art_uri: bool
        :param search_term: A string that will be used to perform a fuzzy
            search among the search results. If used in combination with
            subcategories, the fuzzy search will be performed on the
            subcategory. NOTE: Searching will not work if ml_item is None.
        :type search_term: str
        :param subcategories: A list of strings that indicate one or more
            subcategories to dive into. NOTE: Providing sub categories will
            not work if ml_item is None.
        :type subcategories: list
        :returns: A :py:class:`~.soco.data_structures.SearchResult` object
        :rtype: :py:class:`~.soco.data_structures.SearchResult`
        :raises: AttributeError: If ``ml_item`` has no ``item_id`` attribute
            SoCoUPnPException: With ``error_code='701'`` if the item cannot be
            browsed
        """
        if ml_item is None:
            search = 'A:'
        else:
            search = ml_item.item_id

        # Add sub categories
        if subcategories is not None:
            for category in subcategories:
                search += '/' + url_escape_path(really_unicode(category))
        # Add fuzzy search
        if search_term is not None:
            search += ':' + url_escape_path(really_unicode(search_term))

        try:
            response, metadata = \
                self._music_lib_search(search, start, max_items)
        except SoCoUPnPException as exception:
            # 'No such object' UPnP errors
            if exception.error_code == '701':
                return SearchResult([], 'browse', 0, 0, None)
            else:
                raise exception
        metadata['search_type'] = 'browse'

        # Parse the results
        containers = from_didl_string(response['Result'])
        item_list = []
        for container in containers:
            # Check if the album art URI should be fully qualified
            if full_album_art_uri:
                self.soco._update_album_art_to_full_uri(container)
            item_list.append(container)

        # pylint: disable=star-args
        return SearchResult(item_list, **metadata)

        # pylint: disable=too-many-arguments

    def browse_by_idstring(self, search_type, idstring, start=0,
                           max_items=100, full_album_art_uri=False):
        """Browse (get sub-elements) a given type.

        :param search_type: The kind of information to retrieve. Can be one of:
            'artists', 'album_artists', 'albums', 'genres', 'composers',
            'tracks', 'share', 'sonos_playlists', and 'playlists', where
            playlists are the imported file based playlists from the
            music library
        :param idstring: String ID to search for
        :param start: Starting number of returned matches
        :param max_items: Maximum number of returned matches. NOTE: The maximum
            may be restricted by the unit, presumably due to transfer
            size consideration, so check the returned number against the
            requested.
        :param full_album_art_uri: If the album art URI should include the
                IP address
        :returns: A dictionary with metadata for the search, with the
            keys 'number_returned', 'update_id', 'total_matches' and an
            'item_list' list with the search results.
        """
        search = self.SEARCH_TRANSLATION[search_type]

        # Check if the string ID already has the type, if so we do not want to
        # add one also Imported playlist have a full path to them, so they do
        # not require the A:PLAYLISTS part first
        if idstring.startswith(search) or (search_type == 'playlists'):
            search = ""

        search_item_id = search + idstring
        search_uri = "#" + search_item_id
        # Not sure about the res protocol. But this seems to work
        res = [DidlResource(
            uri=search_uri, protocol_info="x-rincon-playlist:*:*:*")]
        search_item = DidlObject(
            resources=res, title='', parent_id='',
            item_id=search_item_id)

        # Call the base version
        return self.browse(search_item, start, max_items, full_album_art_uri)

    def _music_lib_search(self, search, start, max_items):
        """Perform a music library search and extract search numbers.

        You can get an overview of all the relevant search prefixes (like
        'A:') and their meaning with the request:

        .. code ::

         response = device.contentDirectory.Browse([
             ('ObjectID', '0'),
             ('BrowseFlag', 'BrowseDirectChildren'),
             ('Filter', '*'),
             ('StartingIndex', 0),
             ('RequestedCount', 100),
             ('SortCriteria', '')
         ])

        Args:
            search (str): The ID to search
            start: The index of the forst item to return
            max_items: The maximum number of items to return

        Returns:
            tuple: (response, metadata) where response is the returned metadata
                and metadata is a dict with the 'number_returned',
                'total_matches' and 'update_id' integers
        """
        response = self.contentDirectory.Browse([
            ('ObjectID', search),
            ('BrowseFlag', 'BrowseDirectChildren'),
            ('Filter', '*'),
            ('StartingIndex', start),
            ('RequestedCount', max_items),
            ('SortCriteria', '')
        ])

        # Get result information
        metadata = {}
        for tag in ['NumberReturned', 'TotalMatches', 'UpdateID']:
            metadata[camel_to_underscore(tag)] = int(response[tag])
        return response, metadata

    @property
    def library_updating(self):
        """True if the music library is in the process of being updated.

        :returns: True if the music library is in the process of being updated
        :rtype: bool
        """
        result = self.contentDirectory.GetShareIndexInProgress()
        return result['IsIndexing'] != '0'

    def start_library_update(self, album_artist_display_option=''):
        """Start an update of the music library.

        If specified, album_artist_display_option changes the album
        artist compilation setting (see also album_artist_display_option).
        """
        return self.contentDirectory.RefreshShareIndex([
            ('AlbumArtistDisplayOption', album_artist_display_option),
        ])

    def search_track(self, artist, album=None, track=None,
                     full_album_art_uri=False):
        """Search for an artist, artist's albums, or specific track.

        :param artist: Artist name
        :type artist: str
        :param album: Album name
        :type album: str
        :param track: Track name
        :type track: str
        :param full_album_art_uri: If the album art URI should include the
            IP address
        :type full_album_art_uri: bool
        :returns: A :py:class:`~.soco.data_structures.SearchResult` object.
        :rtype: :py:class:`~.soco.data_structures.SearchResult`

        """
        subcategories = [artist]
        subcategories.append(album or '')

        # Perform the search
        result = self.get_album_artists(
            full_album_art_uri=full_album_art_uri,
            subcategories=subcategories, search_term=track,
            complete_result=True)
        result._metadata['search_type'] = 'search_track'
        return result

    def get_albums_for_artist(self, artist, full_album_art_uri=False):
        """Get albums for an artist.

        :param artist: Artist name
        :type artist: str
        :param full_album_art_uri: If the album art URI should include the
            IP address
        :type full_album_art_uri: bool
        :returns: A :py:class:`~.soco.data_structures.SearchResult` object.
        :rtype: :py:class:`~.soco.data_structures.SearchResult`

        """
        subcategories = [artist]
        result = self.get_album_artists(
            full_album_art_uri=full_album_art_uri,
            subcategories=subcategories,
            complete_result=True)

        reduced = [item for item in result if item.__class__ == DidlMusicAlbum]
        # It is necessary to update the list of items in two places, due to
        # a bug in SearchResult
        result[:] = reduced
        result._metadata.update({
            'item_list': reduced,
            'search_type': 'albums_for_artist',
            'number_returned': len(reduced),
            'total_matches': len(reduced)
        })
        return result

    def get_tracks_for_album(self, artist, album, full_album_art_uri=False):
        """Get tracks for an artist's album.

        :param artist: Artist name
        :type artist: str
        :param album: Album name
        :type album: str
        :param full_album_art_uri: If the album art URI should include the
            IP address
        :type full_album_art_uri: bool
        :returns: A :py:class:`~.soco.data_structures.SearchResult` object.
        :rtype: :py:class:`~.soco.data_structures.SearchResult`

        """
        subcategories = [artist, album]
        result = self.get_album_artists(
            full_album_art_uri=full_album_art_uri,
            subcategories=subcategories,
            complete_result=True)
        result._metadata['search_type'] = 'tracks_for_album'
        return result

    @property
    def album_artist_display_option(self):
        """Return the current value of the album artist compilation
        setting (see
        http://www.sonos.com/support/help/3.4/en/sonos_user_guide/
        Chap07_new/Compilation_albums.htm)

        This is a string. Possible values:

        * "WMP" - Use Album Artists
        * "ITUNES" - Use iTunes® Compilations
        * "NONE" - Do not group compilations

        To change the current setting, call `start_library_update` and
        pass the new setting.
        """
        result = self.contentDirectory.GetAlbumArtistDisplayOption()
        return result['AlbumArtistDisplayOption']
