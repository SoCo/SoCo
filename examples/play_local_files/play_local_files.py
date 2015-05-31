"""A play local music files example

To use the script:

 * Make sure soco is installed
 * Drop this script into a folder that, besides python files, contains
nothing but music files
 * Adjust the settings on the first three lines of the main function
 * Run the script

"""


from __future__ import print_function, unicode_literals

import os
import time
from threading import Thread
from random import choice
try:
    # Python 3
    from urllib.parse import quote
    from http.server import SimpleHTTPRequestHandler
    from socketserver import TCPServer
    print('Running as python 3')
except ImportError:
    # Python 2
    from urllib import quote
    from SimpleHTTPServer import SimpleHTTPRequestHandler
    from SocketServer import TCPServer
    print('Running as python 2')

import soco


class HttpServer(Thread):
    """A simple HTTP Server in its own thread"""

    def __init__(self, port):
        super(HttpServer, self).__init__()
        self.daemon = True
        handler = SimpleHTTPRequestHandler
        self.httpd = TCPServer(("", port), handler)

    def run(self):
        """Start the server"""
        print('Start HTTP server')
        self.httpd.serve_forever()

    def stop(self):
        """Stop the server"""
        print('Stop HTTP server')
        self.httpd.socket.close()


def add_random_file_from_present_folder(machine_ip, port, zone_name):
    """Add a random non-py file from this folder and subfolders to soco"""
    # Make a list of music files, right now it is done by collection all files
    # below the current folder whose extension does not start with .py
    # This will probably need to be modded for other pusposes.
    music_files = []
    print('Looking for music files')
    for path, dirs, files in os.walk('.'):
        for file_ in files:
            if not os.path.splitext(file_)[1].startswith('.py'):
                music_files.append(os.path.relpath(os.path.join(path, file_)))
                print('Found:', music_files[-1])

    random_file = choice(music_files)
    # urlencode all the path parts (but not the /'s)
    random_file = os.path.join(
        *[quote(part) for part in os.path.split(random_file)]
    )
    print('\nPlaying random file:', random_file)
    netpath = 'http://{}:{}/{}'.format(machine_ip, port, random_file)

    for zone in soco.discover():
        if zone.player_name == zone_name:
            break

    number_in_queue = zone.add_uri_to_queue(netpath)    
    zone.play_from_queue(number_in_queue)


def main():
    # Settings
    machine_ip = '192.168.0.25'
    port = 8000
    zone_name = 'Stue'  # Danish for living room
    # Setup and start the http server
    server = HttpServer(port)
    server.start()

    # When the http server is setup you can really add your files in
    # any way that is desired. The source code for
    # add_random_file_from_present_folder is just an example, but it may be
    # helpful in figuring out how to format the urls
    try:
        add_random_file_from_present_folder(machine_ip, port, zone_name)
        # Remember the http server runs in its own daemonized thread, so it is
        # necessary to keep the main thread alive. So sleep for 3 years.
        time.sleep(10**8)
    except KeyboardInterrupt:
        server.stop()
    
main()
