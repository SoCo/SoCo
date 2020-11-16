# SoCo Web App
This example demonstrates a basic web-based Sonos controller built with SoCo.

![Screenshot of web app](https://github.com/SoCo/SoCo/raw/master/examples/webapp/screenshot.png)

## Set up
This example depends on several external libraries. The easiest way to install everything is by running the following command:

`pip install -r requirements.txt`

Once all dependencies have been installed, rename `settings.py.example` to `settings.py` and edit the file.

### Album Art
In order to show album art, this example makes use of the [Rovi API](http://developer.rovicorp.com). If you'd like to have album art, you'll need to sign up for your own (free) API key. You can do so by going to their [Developer Portal](http://developer.rovicorp.com) and clicking on "Register" at the top right of the page. API keys are issued automatically, but Album Art must be manually enabled for accounts. Simply send an e-mail to [apisupport@rovicorp.com](apisupport@rovicorp.com) and ask that it be enabled for your account.

## Basic Usage
Run `python index.py` to start the application. Then open up a web browser and visit [http://127.0.0.1:5000](http://127.0.0.1:5000).

## License
Copyright (C) 2012 Rahim Sonawalla ([rsonawalla@gmail.com](mailto:rsonawalla@gmail.com) / [@rahims](http://twitter.com/rahims)).

Released under the [MIT license](http://www.opensource.org/licenses/mit-license.php).
