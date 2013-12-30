import time
import hashlib

import requests
import simplejson as json

from flask import Flask, render_template, url_for

from soco import SoCo

import settings

app = Flask(__name__)

app.config.from_pyfile('settings.py')

sonos = SoCo(app.config['SPEAKER_IP'])

def gen_sig():
    return hashlib.md5(app.config['ROVI_API_KEY'] + app.config['ROVI_SHARED_SECRET'] + repr(int(time.time()))).hexdigest()

def get_track_image(artist, album):
    if 'ROVI_SHARED_SECRET' not in app.config:
        return None
    elif 'ROVI_API_KEY' not in app.config:
        return None


    headers = {
        "Accept-Encoding": "gzip"
    }

    r = requests.get('http://api.rovicorp.com/recognition/v2.1/music/match/album?apikey=' + app.config['ROVI_API_KEY'] + '&sig=' + gen_sig() + '&name= ' + album + '&performername=' + artist + '&include=images&size=1', headers=headers)

    d = json.loads(r.content)

    image = url_for('static', filename='img/blank.jpg')

    if d['matchResponse']['results'] != None:
        if d['matchResponse']['results'][0]['album']['images'] != None:
            image = d['matchResponse']['results'][0]['album']['images'][0]['front'][3]['url']
        else:
            image = url_for('static', filename='img/blank.jpg')

    return image

@app.route("/play")
def play():
    sonos.play()

    return 'Ok'

@app.route("/pause")
def pause():
    sonos.pause()

    return 'Ok'

@app.route("/next")
def next():
    sonos.next()

    return 'Ok'

@app.route("/previous")
def previous():
    sonos.previous()

    return 'Ok'

@app.route("/info-light")
def info_light():
    track = sonos.get_current_track_info()

    return json.dumps(track)

@app.route("/info")
def info():
    track = sonos.get_current_track_info()

    track['image'] = get_track_image(track['artist'], track['album'])

    return json.dumps(track)

@app.route("/")
def index():
    track = sonos.get_current_track_info()

    track['image'] = get_track_image(track['artist'], track['album'])

    return render_template('index.html', track=track)

if __name__ == '__main__':
    app.run(debug=True)
