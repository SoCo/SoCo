# SoCo
SoCo (Sonos Controller) is a simple Python class that allows you to programmatically control [Sonos speakers](http://www.sonos.com/system/). It was created at [Music Hack Day Sydney](http://sydney.musichackday.org/2012/), so there is still much room for improvement, however the basic control functionality is there and works well. I've tested it with both a Play:3 and a Play:5.

For more background on this project, please see my [related blog post](http://www.hirahim.com/blog/2012/04/29/dissecting-the-sonos-controller/).

## Set up
SoCo depends on the [Requests](http://docs.python-requests.org/) HTTP library. The easiest way to install it is through pip:

`pip install requests`

Since this was created at a weekend hackathon, I didn't have time to code up dynamic discovery of Sonos devices (done through [SSDP](http://en.wikipedia.org/wiki/Simple_Service_Discovery_Protocol)). In order to use this class, you'll need to pass in the IP address of the Sonos speaker you'd like to control. A simple way to determine the IP address of your Sonos speaker is to launch the official Sonos application and click on "About My Sonos System" from the menu. From there, you'll see an output similar to the one below:

```
Associated ZP: 10.0.0.103
---------------------------------
BRIDGE: BRIDGE
Serial Number: 00-0E-58-4F-87-AC:F
Version: 3.7 (build 17551200)
Hardware Version: 1.5.0.0-2
IP Address: 10.0.0.100
---------------------------------
PLAY:5: HACK CHILL ROOM1
Serial Number: 00-0E-58-5D-15-32:E
Version: 3.7 (build 17551200e)
Hardware Version: 1.16.4.1-2
IP Address: 10.0.0.102
OTP: 1.1.1(1-16-4-zp5s-0.5)
---------------------------------
```

To be clear, you only need the official Sonos application to get the IP address of the speaker. This class does not depend on the official Sonos application in any way.

## Basic Usage
```python
#!/usr/bin/env python
from soco import SoCo

if __name__ == '__main__':
    sonos = SoCo('10.0.0.102') # Pass in the IP of your Sonos speaker

    # Pass in a URI to a media file to have it streamed through the Sonos speaker
    sonos.play('http://archive.org/download/TenD2005-07-16.flac16/TenD2005-07-16t10Wonderboy_64kb.mp3')

    track = sonos.get_current_track_info()

    print track['title']

    sonos.pause()

    # Pass in no arguments to play a stopped or paused track
    sonos.play()
```

## Example Applications
To show off what can be made with SoCo, a basic commandline application and a simple web application are included in the `examples` folder.

![Screenshot of web app](https://github.com/rahims/SoCo/raw/master/examples/webapp/screenshot.png)

## Features
SoCo currently supports the following basic controls:

* Play
* Pause
* Stop
* Next track
* Previous track
* Get information about the currently playing track
    * Track title
    * Artist
    * Album
    * Album Art (if available)
    * Track length
    * Duration played (for example, 30 seconds into a 3 minute song)
    * Playlist position (for example, item 5 in the playlist)
    * Track URI
* Mute (or unmute) the speaker
* Get or set the speaker volume
* Get or set the speaker's bass EQ
* Get or set the speaker's treble EQ
* Toggle the speaker's loudness compensation
* Turn on (or off) the white status light on the unit
* Switch the speaker's source to line-in (doesn't work on the Play:3 since it doesn't have a line-in)
* Get the speaker's information
    * Zone Name
    * Zone Icon
    * UID (usually something like RINCON_XXXXXXXXXXXXXXXXX)
    * Serial Number
    * Software version
    * Hardware version
    * MAC Address

## To-Do
Want to contribute to SoCo? Here's what needs to be done:

* SSDP for dynamic discovery of Sonos devices
* playlist management
* better error checking

## License
Copyright (C) 2012 Rahim Sonawalla ([rsonawalla@gmail.com](mailto:rsonawalla@gmail.com) / [@rahims](http://twitter.com/rahims)).

Released under the [MIT license](http://www.opensource.org/licenses/mit-license.php).
