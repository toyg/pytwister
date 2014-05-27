Twister Python scripts
======================

These are some random scripts for Twister.
Prerequisites:

* Python 3.3.x (might work with 3.2 or 2.7 but it's untested. Probably won't work with 2.6-).
* My patched [python-bitcoinrpc](https://github.com/toyg/python-bitcoinrpc) (the original by jgarzik currently fails to work with Unicode characters).
* [feedparser](https://pypi.python.org/pypi/feedparser) (`pip install feedparser` will work) -- this is for twistmonitor.py only

HELP!
=====

Feel free to contribute! 
In particular, map.html is the template for the [map of Twister users](http://static.pythonaro.com/twistmap/) 
and could do with some love. For simple tests, just replace

    var locations = [];

with

    var locations = [ 
        ['<h4>Some Location - 123</h4><small>someuser, someotheruser</small>', 34.0659329, -84.6768796],
        ['<h4>Some Other Location - 456</h4><small>somenick, someothernick</small>', 52.3702157, 4.895167900000001],
      ];
