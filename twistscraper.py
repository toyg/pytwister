# -*- coding: utf-8 -*-
from http.client import HTTPException
from urllib.parse import urlencode
from urllib.request import urlopen, Request
import datetime
import json
import pickle
import time
import sys

from os.path import expanduser, exists


cacheTimeout = 24 * 3600

try:
    from bitcoinrpc.authproxy import AuthServiceProxy
except ImportError as exc:
    sys.stderr.write("Error: install python-bitcoinrpc (https://github.com/jgarzik/python-bitcoinrpc)\n")
    sys.exit(-1)


class MaxGeoRequestsException(Exception):
    def __init__(self, since):
        super(Exception, self).__init__()
        self.lastReset = since
        print(self.__str__())

    def __str__(self):
        return "Reached max amounts of requests per hour ({} since {})".format(GeoLocationService.MAXREQUESTS,
                                                                               self.lastReset.isoformat())


class Borg:
    _shared_state = {}

    def __init__(self):
        self.__dict__ = self._shared_state


class GeoLocationService(Borg):
    MAXREQUESTS = 60 * 60 # 1 req per second
    CACHEFILE = expanduser('~/.twister/_localusers_geolocation.db')
    NOMINATIM_URL = "http://nominatim.openstreetmap.org/search?format=jsonv2&{query}"

    def __init__(self):
        super(GeoLocationService, self).__init__()
        if len(self.__dict__) == 0: # set up only if it's the first instance
            self.db = {}
            self._counter = 0
            self._lastCounterReset = None
            self._resetCounter()

            if exists(GeoLocationService.CACHEFILE):
                with open(GeoLocationService.CACHEFILE, 'rb') as gcache:
                    self.db = pickle.load(gcache)

    def _resetCounter(self):
        self._counter = 0
        self._lastCounterReset = datetime.datetime.now()

    def canWeAsk(self):
        """ Check if we can make a lookup.

        :return: boolean
        """
        if self._counter <= (GeoLocationService.MAXREQUESTS - 1):
            return True
        now = datetime.datetime.now()
        delta = now - self._lastCounterReset
        if delta.total_seconds() > (60 * 60):
            self._resetCounter()
            return True
        return False

    def locate(self, location):
        """
        Query Google API and save coordinates. Max 50 requests per hour
        :return: dict with coordinates { 'lat':12345, 'lng':13245 }
        :raises: MaxGeoRequestsException when geolocation threshold has been reached
        """

        # if in cache, return that
        if location in self.db:
            # this harmonization is due to old data
            if type(self.db[location]) == dict:
                coordTuple = (self.db[location]['lat'], self.db[location]['lng'])
                self.db[location] = coordTuple
            return self.db[location]

        # not in cache? ok, let's look it up

        if not self.canWeAsk():
            # sorry, can't do it now
            raise MaxGeoRequestsException(self._lastCounterReset)

        print("Looking up \"{}\"".format(location))
        loc = urlencode({'q': location})
        print(GeoLocationService.NOMINATIM_URL.format(query=loc))
        request = Request(GeoLocationService.NOMINATIM_URL.format(query=loc))
        request.add_header('User-Agent', 'Twister User-Mapper script http://static.pythonaro.com/twistmap/')
        urldoc = urlopen(request)
        self._counter += 1
        jsonText = urldoc.readall().decode('utf-8')
        jsObj = json.loads(jsonText)
        if len(jsObj) > 0:
            coords = jsObj[0]['lat'], jsObj[0]['lon']
            # let's cache it and save db
            self.db[location] = coords
            self.saveDb()
            time.sleep(1) # to follow nominatim usage policy: http://wiki.openstreetmap.org/wiki/Nominatim_usage_policy
            return coords

        # still here? it's all rubbish
        return None

    def saveDb(self):
        """ Save db to file """
        with open(GeoLocationService.CACHEFILE, 'wb') as gfile:
            pickle.dump(self.db, gfile)


class User:
    def __init__(self):
        self.locService = GeoLocationService()
        self.username = ""
        self.avatar = ""
        self.fullname = ""
        self.location = ""
        self.coords = None
        self.bio = ""
        self.url = ""
        self.updateTime = 0
        self.following = []


    def locate(self):
        # OO wrapper for GeoLocationService.locate()
        if hasattr(self, 'location') and self.location == '':
            return None
        if hasattr(self, 'coords') and self.coords is not None:
            return self.coords

        if not hasattr(self, 'locService'):
            self.__dict__['locService'] = GeoLocationService()

        self.coords = self.locService.locate(self.location)
        return self.coords

    def __setstate__(self, data):
        """ Custom unpickling function to re-instantiate the location service
        :param data: dictionary passed by pickle.load()
        """
        self.__dict__ = data
        self.locService = GeoLocationService()

    def __getstate__(self):
        """ Custom pickler to drop references to the location service
        :return: dict containing the object state
        """
        self.locService = None
        return self.__dict__


class TwisterDb:
    def __init__(self):
        self.lastBlockHash = None
        self.users = {}


class TwisterScraper:
    CACHE_MAX_DURATION = datetime.timedelta(7)  # ([days [, seconds [,microseconds]]])

    def __init__(self, dbPath, server='localhost', port=28332, user='user', password='pwd', protocol='http'):
        self.serverUrl = '{protocol}://{user}:{passwd}@{server}:{port}'.format(protocol=protocol,
                                                                               server=server,
                                                                               port=port,
                                                                               user=user,
                                                                               passwd=password)
        self.twister = AuthServiceProxy(self.serverUrl)
        self.dbFile = dbPath
        self.locService = GeoLocationService()

        try:
            with open(self.dbFile, 'rb') as dbFile:
                self.db = pickle.load(dbFile)
        except FileNotFoundError:
            self.db = TwisterDb()
            self.saveDb()

    def get_user(self, username):
        if username in self.db.users:
            return self.db.users[username]
        else:
            return None

    def scrape_users(self):
        nextHash = 0
        nextHash = self.twister.getblockhash(0)

        usernames = set()
        index = 0
        while True:
            block = self.twister.getblock(nextHash)
            self.db.lastBlockHash = block['hash']
            usernames = usernames.union(set(block['usernames']))
            if len(usernames) > index:
                index = len(usernames)
                print('Found {0} usernames'.format(index))
            if "nextblockhash" in block:
                nextHash = block["nextblockhash"]
            else:
                break

        if len(self.db.users) == 0:
            # first run
            for u in usernames:
                blankUser = User()
                blankUser.username = u
                blankUser.updateTime = datetime.datetime.now() - self.CACHE_MAX_DURATION
            self.saveDb()

        now = datetime.datetime.now()
        old_users = self.db.users.keys()
        need_refresh = [u for u in old_users if (self.db.users[u].updateTime + self.CACHE_MAX_DURATION) < now]
        new_users = usernames.difference(set(old_users))
        to_fetch = new_users.union(set(need_refresh))

        total_to_fetch = len(to_fetch)
        for n, u in enumerate(to_fetch):
            try:
                user = self._fetch_user_details(u)
                if hasattr(u, 'location'):
                    try:
                        u.locate()
                    except MaxGeoRequestsException:
                        print("Could not locate '' because of max request limit reached")
                self.db.users[user.username] = user
                if n % 5 == 0:
                    self.saveDb()
                print("({line} of {total}) Fetched {user} ...".format(user=u, line=n, total=total_to_fetch))
            except HTTPException as e:
                print("Connection error retrieving user {0}: {1}".format(u, str(e)))

    def saveDb(self):
        print("Saving db")
        try:
            with open(self.dbFile, 'wb') as dbFile:
                pickle.dump(self.db, dbFile)
        except (KeyboardInterrupt, Exception):
            print("Closing db before quitting...")
            if dbFile:
                # close the hung descriptor and re-try the dumping
                try:
                    dbFile.close()
                except Exception:
                    pass
                with open(self.dbFile, 'wb') as dbFile:
                    pickle.dump(self.db, dbFile)
                    # once clean, re-raise
                raise

    def get_posts_since(self, username, dateObj, maxNum=1000):
        since_epoch = time.mktime(dateObj.timetuple())
        all_posts = self.twister.getposts(1000, [{'username': username}])
        all_posts = sorted(all_posts, key=lambda x: x['userpost']['time'])
        index = int(len(all_posts) / 2)

        def _post_time(i):
            return all_posts[i]['userpost']['time']

        while 0 > index > len(all_posts):
            if _post_time(index - 1) < since_epoch < _post_time(index + 1):
                if _post_time(index) < since_epoch:
                    index += 1
                break
            elif _post_time(index) > since_epoch:
                index = int(index / 2)
            elif _post_time(index) < since_epoch:
                index = int(index + index / 2)

        return all_posts[index:]

    def _fetch_user_details(self, username):
        user = User()
        user.username = username

        avatarData = self.twister.dhtget(username, "avatar", "s")
        if len(avatarData) == 1:
            if 'p' in avatarData[0]:
                if 'v' in avatarData[0]['p']:
                    user.avatar = avatarData[0]['p']['v']

        profileData = self.twister.dhtget(username, 'profile', 's')
        if len(profileData) == 1:
            if 'p' in profileData[0]:
                if 'v' in profileData[0]['p']:
                    profile = profileData[0]['p']['v']
                    for key in ['location', 'url', 'bio', 'fullname']:
                        if key in profile:
                            setattr(user, key, profile[key])

        user.following = self.twister.getfollowing(username)

        user.updateTime = datetime.datetime.now()
        return user


if __name__ == '__main__':
    ts = TwisterScraper(expanduser('~/.twister/_localusersdb'), 'localhost')
    ts.scrape_users()
    print("Total users in db: {0}".format(len(ts.db.users)))

