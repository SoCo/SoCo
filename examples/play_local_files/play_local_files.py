"""A play local music files example

To use the script:

 * Make sure soco is installed
 * Drop this script into a folder that, besides python files, contains
nothing but music files
 * Choose which player to use and run the script at the command line as such:

play_local_files.py "Living Room"

NOTE: The script has been changed from the earlier version, where the
settings were written directly into the file. They now have to be
given at the command line instead. But, it should only be necessary to
supply the zone name. The local machine IP should be autodetected.

"""


from __future__ import print_function, unicode_literals

import os
import sys
import time
import socket
from threading import Thread
from random import choice

try:
    # Python 3
    from urllib.parse import quote
    from http.server import SimpleHTTPRequestHandler
    from socketserver import TCPServer

    print("Running as python 3")
except ImportError:
    # Python 2
    from urllib import quote
    from SimpleHTTPServer import SimpleHTTPRequestHandler
    from SocketServer import TCPServer

    print("Running as python 2")

from soco.discovery import by_name, discover


class HttpServer(Thread):
    """A simple HTTP Server in its own thread"""

    def __init__(self, port):
        super(HttpServer, self).__init__()
        self.daemon = True
        handler = SimpleHTTPRequestHandler
        self.httpd = TCPServer(("", port), handler)

    def run(self):
        """Start the server"""
        print("Start HTTP server")
        self.httpd.serve_forever()

    def stop(self):
        """Stop the server"""
        print("Stop HTTP server")
        self.httpd.socket.close()


def add_random_file_from_present_folder(machine_ip, port, zone):
    """Add a random non-py file from this folder and subfolders to soco"""
    # Make a list of music files, right now it is done by collection all files
    # below the current folder whose extension does not start with .py
    # This will probably need to be modded for other pusposes.
    music_files = []
    print("Looking for music files")
    for path, dirs, files in os.walk("."):
        for file_ in files:
            if not os.path.splitext(file_)[1].startswith(".py"):
                music_files.append(os.path.relpath(os.path.join(path, file_)))
                print("Found:", music_files[-1])

    random_file = choice(music_files)
    # urlencode all the path parts (but not the /'s)
    random_file = os.path.join(*[quote(part) for part in os.path.split(random_file)])
    print("\nPlaying random file:", random_file)
    netpath = "http://{}:{}/{}".format(machine_ip, port, random_file)

    number_in_queue = zone.add_uri_to_queue(netpath)
    # play_from_queue indexes are 0-based
    zone.play_from_queue(number_in_queue - 1)


def detect_ip_address():
    """Return the local ip-address"""
    # Rather hackish way to get the local ip-address, recipy from
    # https://stackoverflow.com/a/166589
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip_address = s.getsockname()[0]
    s.close()
    return ip_address


def parse_args():
    """Parse the command line arguments"""
    import argparse

    description = "Play local files with Sonos by running a local web server"
    parser = argparse.ArgumentParser(description=description)

    parser.add_argument("zone", help="The name of the zone to play from")
    parser.add_argument(
        "--port", default=8000, help="The local machine port to run the webser on"
    )
    parser.add_argument(
        "--ip",
        default=detect_ip_address(),
        help="The local IP address of this machine. By "
        "default it will attempt to autodetect it.",
    )

    return parser.parse_args()


def main():
    # Settings
    args = parse_args()
    print(
        " Will use the following settings:\n"
        " Zone: {args.zone}\n"
        " IP of this machine: {args.ip}\n"
        " Use port: {args.port}".format(args=args)
    )

    # Get the zone
    zone = by_name(args.zone)

    # Check if a zone by the given name was found
    if zone is None:
        zone_names = [zone_.player_name for zone_ in discover()]
        print(
            "No Sonos player named '{}'. Player names are {}".format(
                args.zone, zone_names
            )
        )
        sys.exit(1)

    # Check whether the zone is a coordinator (stand alone zone or
    # master of a group)
    if not zone.is_coordinator:
        print(
            "The zone '{}' is not a group master, and therefore cannot "
            "play music. Please use '{}' in stead".format(
                args.zone, zone.group.coordinator.player_name
            )
        )
        sys.exit(2)

    # Setup and start the http server
    server = HttpServer(args.port)
    server.start()

    # When the http server is setup you can really add your files in
    # any way that is desired. The source code for
    # add_random_file_from_present_folder is just an example, but it may be
    # helpful in figuring out how to format the urls
    try:
        add_random_file_from_present_folder(args.ip, args.port, zone)
        # Remember the http server runs in its own daemonized thread, so it is
        # necessary to keep the main thread alive. So sleep for 3 years.
        time.sleep(10 ** 8)
    except KeyboardInterrupt:
        server.stop()


main()
