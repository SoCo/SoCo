# -*- coding: utf-8 -*-

"""The Spotify plugin has been DEPRECATED

The Spotify Plugin has been immediately deprecated (August 2016),
because the API it was based on (The Spotify Metadata API) has been
ended. Since this rendered the plug-in broken, there was no need to
forewarn of the deprecation.

Please consider moving to the new general music services code (in
soco.music_services.music_service), that makes it possible to
retrived information about the available media from all music
services. A short intro for how to use the new code is available
in the API documentation:

 * http://docs.python-soco.com/en/latest/api/\
soco.music_services.music_service.html

and for some information about how to add items from the music
services to the queue, see this gist:

 * https://gist.github.com/lawrenceakka/2d21dca590b4fa7e3af2"

This deprecation notification will be deleted for the second release
after 0.12.

"""

import sys
import os
# Only raise this import error if we are not building the docs
if not (os.environ.get('READTHEDOCS', None) == 'True' or
        'sphinx' in sys.modules):
    raise RuntimeError(__doc__)
