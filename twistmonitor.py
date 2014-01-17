# -*- coding: utf-8 -*-
import pickle
from operator import attrgetter
from threading import Thread
from time import sleep
from os.path import expanduser

import feedparser

from twistscraper import TwisterScraper

__author__ = 'Giacomo Lacava'

GITHUB_REPO_URL = 'https://github.com/{user}/{repo}'
GITHUB_COMMIT_FEED_TEMPLATE = GITHUB_REPO_URL + '/commits/master.atom'

CORE_COMMIT_FEED = GITHUB_COMMIT_FEED_TEMPLATE.format(user='miguelfreitas', repo='twister-core')
HTML_COMMIT_FEED = GITHUB_COMMIT_FEED_TEMPLATE.format(user='miguelfreitas', repo='twister-html')
SEED_COMMIT_FEED = GITHUB_COMMIT_FEED_TEMPLATE.format(user='miguelfreitas', repo='twister-seeder')
CORE_REPO_URL = GITHUB_REPO_URL.format(user='miguelfreitas', repo='twister-core')
HTML_REPO_URL = GITHUB_REPO_URL.format(user='miguelfreitas', repo='twister-html')
SEED_REPO_URL = GITHUB_REPO_URL.format(user='miguelfreitas', repo='twister-seeder')


class TwisterMonitor(Thread):
    MESSAGE = 'Twister update: {msg} - Pull it now: {url}'

    def __init__(self, twister_monitor, username, repo_feed=CORE_COMMIT_FEED, repo_url=CORE_REPO_URL):
        Thread.__init__(self)
        self.ts = twister_monitor
        self.cacheFile = expanduser('~/.twister/_twm_cache')
        self.cache = {}
        self.username = username
        self.feed = repo_feed
        self.repo = repo_url
        self.loadCache()

    def loadCache(self):
        try:
            with open(self.cacheFile, 'rb') as f:
                self.cache = pickle.load(f)
        except FileNotFoundError:
            self.cache = {}

    def get_commits(self):
        print("Fetching {0}".format(self.feed))
        f = feedparser.parse(self.feed)
        if f['bozo'] == 1:
            raise Exception('Bad feed! Status: {status} - Error {err}'.format(status=f.status, err=f.bozo_exception))

        if self.feed not in self.cache:
            self.cache[self.feed] = []

        f.entries.sort(key=attrgetter('updated_parsed'))
        for entry in f.entries:
            print("Checking {0}".format(entry.id))
            if entry.id not in self.cache[self.feed]:
                message = TwisterMonitor.MESSAGE.format(msg=entry.title, url=self.repo)
                cut = 1
                while len(message) >= 140:
                    message = TwisterMonitor.MESSAGE.format(msg=(entry.title[:-cut] + '...'), url=self.repo)
                    cut += 1

                print("Checking last post key...")
                key = 1
                lastpost = self.ts.twister.getposts(1, [{"username": self.username}])
                if len(lastpost) == 1:
                    key = lastpost[0]['userpost']['k'] + 1
                print("Posting '{0}' with key {1}...".format(message, key))
                self.ts.twister.newpostmsg(self.username, key, message)
                print("Posted!")
                self.cache[self.feed].append(entry.id)
                self.saveCache()
                sleep(10 * 60)

    def saveCache(self):
        with open(self.cacheFile, 'wb') as f:
            pickle.dump(self.cache, f)

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
    monitor = TwisterMonitor(ts, botID, CORE_COMMIT_FEED, CORE_REPO_URL)
    monitor.start()
    sleep(4 * 60)
    monitor_ui = TwisterMonitor(ts, botID, HTML_COMMIT_FEED, HTML_REPO_URL)
    monitor_ui.start()
    sleep(6 * 60)
    monitor_seed = TwisterMonitor(ts, botID, SEED_COMMIT_FEED, SEED_REPO_URL)
    monitor_seed.start()
