# -*- coding: utf-8 -*-
#
# Copyright 2010 Ionuț Arțăriși <mapleoin@lavabit.com>
#
# This file is part of obswatch.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import smtplib
import time
import urllib2
import xml.etree.ElementTree as etree

import osc.core
import osc.conf
from osc.core import makeurl, http_GET

# init
logging.basicConfig(level=logging.INFO)
osc.conf.get_config()
APIURL = 'https://api.opensuse.org/'
PKG_STATUSES = {
    'final': ['succeeded', 'failed', 'unresolvable', 'broken', 'blocked'],
    'intermediate': ['dispatching', 'scheduled', 'building', 'signing',
                  'finished'],
    # put 'unknown' in 'other' instead of 'intermediate'
    # since it seems a bit buggy
    'other': ['excluded', 'disabled', 'unknown'],
    }
SLEEP_TIME = 1

class Package:
    def __init__(self, pkg_xml):
        self.name = pkg_xml.get('name')
        self.project = pkg_xml.get('project')
        self.created = pkg_xml.get('created')
    
def get_latest_packages(limit=None):
    """Returns a Package object list of the 'limit' latest updated packages

    """
    url = makeurl(APIURL, ['statistics', 'latest_updated'],
                  query={'limit':limit})
    pkg_tree = etree.parse(http_GET(url))
    return [Package(pkg_xml) for pkg_xml in pkg_tree.findall('package')]

def send_email(user, to_addr, package, downloads):
    """Send an email informing the user that the package was built

    """
    from_addr = 'osc@opensuse.org'
    conn = smtplib.SMTP('localhost')
    downstring = '\n'.join(['%s - %s' % (build, url)
                            for build, url in downloads.items()])
    body = ('The package %(package)s has finished building and can now '
            'be downloaded from:\n%(downloads)s' % {'package':package,
                                                    'downloads': downstring})
    msg = ('To: %(to_addr)s\n'
           'From: %(from_addr)s\n'
           'Subject: (osc) build succeeded: %(package)s\n\n'
           '%(body)s' %
           {'to_addr': to_addr,
            'from_addr': from_addr,
            'package': package,
            'body': body})
    conn.sendmail(from_addr, [to_addr], msg)
    conn.quit()

class Build:
    def __init__(self, package, repo, interested):
        '''
        :arg package: a Package object
        :arg repo: a Repo object
        :arg interested: a dict of username: email pairs
        '''
        self.package = package
        self.repo = repo
        self.interested = interested
        self.url = makeurl(APIURL, ['build', package.project,
                                           repo.name, repo.arch,
                                           package.name])
        self.status = 'new-to-watchlist'

    def get_binaries(self):
        """Return a dictionary of binary-name: binary-url pairs"""
        tree = etree.parse(http_GET(self.url))
        binaries = [b.get('filename') for b in tree.findall('binary')]
        bindict = {}
        for b in binaries:
            bindict[b] = '%s/%s' % (self.url, b)
        return bindict
        
    def __str__(self):
        return '%s in repository %s.%s of project %s' % (
            self.package.name, self.repo.name, self.repo.arch,

            self.package.project)

    def get_remote_status(self):
        """Return the current status in the buildservice"""
        try:
            tree = etree.parse(http_GET('%s/_status' % self.url))
        except urllib2.HTTPError:
            logging.error('Not Found: %s/_status' % self.url)
            return 'notfound'
        else:
            return tree.getroot().get('code')

def get_interested(package):
    """Return a list of people interested in the package.

    :package: a Package object

    Returns a dict of userid, email pairs.

    """
    interested = {}

    # Search for interested parties at the package and project level
    package_meta = makeurl(APIURL,
                           ['source', package.project, package.name, '_meta'])
    project_meta = makeurl(APIURL,
                           ['source', package.project, '_meta'])
    for url in [package_meta, project_meta]:
        interested.update(get_users_from_url(url))

    return interested
    
def get_users_from_url(url):
    """Get multiple users information from a url

    :arg url: an API URL that contains <person> xml objects

    Returns a dictionary of users and their emails.

    """
    tree = etree.parse(http_GET(url))

    users = {}
    for person in tree.findall('person'):
        userid = person.get('userid')
        users[userid] = get_user_email(userid)
    return users

def get_user_email(username):
    """Return an user's email based on their username

    :arg username: string username

    """
    url = makeurl(APIURL, ['person', username])
    tree = etree.parse(http_GET(url))
    return tree.findtext('email')

def get_builds(package):
    """Returns a list of the Build objects of a Package.

    :arg package: a Package object

    """
    # get the list of people interested at this point since they're the same
    # for all the builds of this package
    interested = get_interested(package)
    repos = osc.core.get_repos_of_project(APIURL, package.project)
    watchlist = []
    for repo in repos:
        build = Build(package, repo, interested)
        watchlist.append(build)
    return watchlist

def process_build(build):
    """Process a build taking different actions depending on its status

    Build states are contained in the PKG_STATUSES dictionary.

    If the build's state has not changed since last check, return True.

    If the build's state has changed, then if:
     - build is in a 'final' state, email the concerned parties and
    return False,
     - build is in an 'intermediate' state, update it's status and
     return True,
     - build is in a state we don't care about 'other', return False

    :arg build: a Build object

    """
    time.sleep(SLEEP_TIME) # don't abuse the remote API
    current_status = build.get_remote_status()
    if build.status != current_status:
        logging.info("The status of package %(package)s in repository "
              "%(repository)s was %(old_status)s and is now: "
              "%(status)s." %
              {'package': build.package.name,
               'repository': build.repo.name+'.'+build.repo.arch,
               'old_status': build.status,
               'status': current_status})

        if current_status in PKG_STATUSES['final']:
            # Stop watching
            # email only if succeeded
            if current_status == 'succeeded':
                for user in build.interested:
                    logging.info('Emailing %s at %s for %s' % (
                        user, build.interested[user], build))
                    send_email(user, build.interested[user], build,
                               build.get_binaries())
            else:
                logging.info('No longer watching package %s - %s.' %
                             (build, current_status))
            return False

        elif current_status in PKG_STATUSES['other']:
            # don't care what happens to those packages
            logging.info('No longer watching package %s - %s' %
                         (build, current_status))
            return False

        elif current_status in PKG_STATUSES['intermediate']:
            # since this is a transient state, we'll keep watching
            # for a change
            build.status = current_status
            return True
        else:
            raise Exception, ('This build is in an unknown state: %s.'
                              % build)
    else:
        return True
