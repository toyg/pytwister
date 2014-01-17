# -*- coding: utf-8 -*-
from datetime import datetime
from string import Template

from os.path import expanduser


__author__ = 'Giacomo Lacava'

from twistscraper import TwisterScraper

TEMPLATE = None
with open("map.html", "rb") as mapTemplate:
    TEMPLATE = Template(mapTemplate.read())


def generate_map(userdb):
    ts = TwisterScraper(userdb)
    loc_users = [u for u in ts.db.users.values() if u.location != '']
    noLoc_user_num = len(ts.db.users) - len(loc_users)
    loc_users_fake_num = 0
    locDb = {}

    for u in loc_users:
        if u.location in locDb:
            locDb[u.location]['users'].append(u.username)
        else:
            locData = u.locate()
            if locData is not None:
                locDb[u.location] = {}
                locDb[u.location]['coordinates'] = locData
                locDb[u.location]['users'] = [u.username]
            else:
                loc_users_fake_num += 1
        # second pass to aggregate misspellings
    done = []
    newLocDb = {}
    for loc, locDict in locDb.items():
        # find all elements with same coordinates
        sameCoord = [(l, lObj['users']) for l, lObj in locDb.items() if lObj['coordinates'] == locDict['coordinates']]
        if len(sameCoord) == 1:
            # if only one element, copy it straight to the new dict
            newLocDb[loc] = locDict

        elif len(sameCoord) > 1:
            # if we're here, multiple locations have the same name

            # find the most popular name
            locMax = max(sameCoord, key=lambda x: len(x[1]))
            location = locMax[0]
            coordHash = '/'.join([str(locDict['coordinates']['lat']), str(locDict['coordinates']['lng'])])
            # if we haven't seen this set of coordinates yet...
            if coordHash not in done:

                # ... collect all users ...
                users = []
                for l, us in sameCoord:
                    for u in us:
                        users.append(u)
                users.sort()

                # ... and add the aggregated result
                if location not in newLocDb:
                    newLocDb[location] = {}
                newLocDb[location]['users'] = users
                newLocDb[location]['coordinates'] = locDict['coordinates']
                done.append(coordHash)

    locStrings = []
    for k in newLocDb.keys():
        locStrings.append("['<h4>{name} - {numusers}</h4><small>{users}</small>', {lat}, {lng}]".format(
            name=k.replace("'", "&apos;"),
            lat=newLocDb[k]['coordinates']['lat'],
            lng=newLocDb[k]['coordinates']['lng'],
            users=',<br />'.join(newLocDb[k]['users']),
            numusers=len(newLocDb[k]['users'])))
    locStrings.sort()
    return TEMPLATE.substitute(locations=',\n'.join(locStrings),
                               users_real_loc=len(loc_users),
                               users_fake_loc=loc_users_fake_num,
                               users_no_loc=noLoc_user_num,
                               timestamp=datetime.now().isoformat())


if __name__ == '__main__':
    html = generate_map(expanduser('~/.twister/_localusersdb'))
    with open(expanduser('~/twistermap.html'), 'wb') as tmf:
        tmf.write(html.encode('utf-8'))