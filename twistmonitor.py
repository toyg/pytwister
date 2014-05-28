# -*- coding: utf-8 -*-
import pickle
from operator import attrgetter
from threading import Thread
from time import sleep
from os.path import expanduser

import feedparser

from twistscraper import TwisterScraper

__author__ = 'Giacomo Lacava'


class FeedCache:
    _shared_state = {}

    def __init__(self):
        self.__dict__ = self._shared_state
        if len(self.__dict__) == 0:
            # first instance setup
            self.cacheFile = expanduser('~/.twister/_twm_cache')
            self.cache = {}
            self._load_cache()


    def _load_cache(self):
        try:
            with open(self.cacheFile, 'rb') as f:
                self.cache = pickle.load(f)
        except FileNotFoundError:
            self.cache = {}

    def _save_cache(self):
        with open(self.cacheFile, 'wb') as f:
            pickle.dump(self.cache, f)

    def get_feed_cache(self, feedUrl):
        if feedUrl not in self.cache:
            self.cache[feedUrl] = []
        return self.cache[feedUrl]

    def add_entry(self, feedUrl, entryID):
        feed = self.get_feed_cache(feedUrl)
        feed.append(entryID)
        self._save_cache()


class TwisterMonitor(Thread):
    MESSAGE = '{repo}: {msg} - {url}'
    GITHUB_REPO_URL = 'https://github.com/{user}/{repo}'
    GITHUB_COMMIT_FEED_TEMPLATE = GITHUB_REPO_URL + '/commits/master.atom'


    def __init__(self, scraperObj, username, github_user, github_repo):
        Thread.__init__(self)
        self.ts = scraperObj
        self.cacheObj = FeedCache()
        self.username = username
        self.feed = TwisterMonitor.GITHUB_COMMIT_FEED_TEMPLATE.format(user=github_user, repo=github_repo)
        self.repo = TwisterMonitor.GITHUB_REPO_URL.format(user=github_user, repo=github_repo)
        self.github_user = github_user
        self.github_repo = github_repo
        self.cache = self.cacheObj.get_feed_cache(self.feed)


    def get_commits(self):
        print("Fetching {0}".format(self.feed))
        f = feedparser.parse(self.feed)
        if f['bozo'] == 1:
            raise Exception('Bad feed! Status: {status} - Error {err}'.format(status=f.status, err=f.bozo_exception))

        f.entries.sort(key=attrgetter('updated_parsed'))
        for entry in f.entries:
            print("Checking {0}".format(entry.id))
            if entry.id not in self.cache:
                message = TwisterMonitor.MESSAGE.format(msg=entry.title,
                                                        url=self.repo,
                                                        repo=self.github_repo)
                cut = 1
                while len(message) >= 140:
                    message = TwisterMonitor.MESSAGE.format(msg=(entry.title[:-cut] + '...'),
                                                            url=self.repo,
                                                            repo=self.github_repo)
                    cut += 1

                print("Checking last post key...")
                key = 1
                lastpost = self.ts.twister.getposts(1, [{"username": self.username}])
                if len(lastpost) == 1:
                    key = lastpost[0]['userpost']['k'] + 1
                print("Posting '{0}' with key {1}...".format(message, key))
                self.ts.twister.newpostmsg(self.username, key, message)
                print("Posted!")
                self.cacheObj.add_entry(self.feed, entry.id)
                sleep(10 * 60)


    def run(self):
        while True:
            try:
                self.get_commits()
            except Exception as e:
                print("Exception following!")
                print(e)
            sleep(60 * 60) # in seconds


if __name__ == '__main__':
    botID = 'twmonitor'
    ts = TwisterScraper(expanduser('~/.twister/_localusersdb'))
    monitor = TwisterMonitor(ts, botID, "miguelfreitas", "twister-core")
    monitor.start()
    sleep(4 * 60)
    monitor_ui = TwisterMonitor(ts, botID, "miguelfreitas", "twister-html")
    monitor_ui.start()
    sleep(6 * 60)
    monitor_seed = TwisterMonitor(ts, botID, "miguelfreitas", "twister-seeder")
    monitor_seed.start()
