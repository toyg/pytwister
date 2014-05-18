# -*- coding: utf-8 -*-
import json
from http.client import HTTPException
from urllib.parse import urlencode
from urllib.request import urlopen
from genericpath import exists
from os.path import expanduser

__author__ = 'Giacomo Lacava'

import time, datetime
import pickle
import sys

cacheTimeout = 24 * 3600

try:
    from bitcoinrpc.authproxy import AuthServiceProxy
except ImportError as exc:
    sys.stderr.write("Error: install python-bitcoinrpc (https://github.com/jgarzik/python-bitcoinrpc)\n")
    sys.exit(-1)


class GeoLocationService:
    CACHEFILE = expanduser('~/.twister/_localusers_geolocation.db')
    _GMAP_URL = "https://maps.googleapis.com/maps/api/geocode/json?sensor=false&{query}"

    def __init__(self):
        self.db = {}
        if exists(GeoLocationService.CACHEFILE):
            with open(GeoLocationService.CACHEFILE, 'rb') as gcache:
                self.db = pickle.load(gcache)

    def locate(self, location):
        """
        Query Google API and save coordinates. Should work until we start having more than 50 new locatable
                users per hour.
        :return: dict with coordinates { 'lat':12345, 'lng':13245 }
        """

        # if in cache, return that
        if location in self.db:
            return self.db[location]
            # ok, let's look it up
        loc = urlencode({'address': location})
        urldoc = urlopen(GeoLocationService._GMAP_URL.format(query=loc))
        jsObj = json.loads(urldoc.readall().decode('utf-8'))
        if len(jsObj['results']) > 0:
            # discard commercial results
            locTypes = jsObj['results'][0]['address_components'][0]['types']
            if not 'premise' in locTypes and not 'route' in locTypes and not 'establishment' in locTypes and not 'subpremise' in locTypes:
                coords = jsObj['results'][0]['geometry']['location']
                # let's cache it and save db
                self.db[location] = coords
                self.saveDb()
                return coords
                # still here? it's all rubbish
        return None

    def saveDb(self):
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
        if self.location == '':
            return None
        if self.coords is not None:
            return self.coords

        self.coords = self.locService.locate(self.location)
        return self.coords


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
        #if self.db.lastBlockHash is not None and len(self.db.users) != 0:
        #    nextHash = self.db.lastBlockHash
        #else:
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
                self.db.users[user.username] = user
                self.saveDb()
                print("({line} of {total}) Fetched {user} ...".format(user=u, line=n, total=total_to_fetch))
            except HTTPException as e:
                print("Connection error retrieving user {0}: {1}".format(u, str(e)))

    def saveDb(self):
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

