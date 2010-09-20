import unittest
import smtplib
import minimock
from minimock import assert_same_trace, mock, Mock, TraceTracker
from StringIO import StringIO

import osc.core

import obswatch

class TestObswatch(unittest.TestCase):

    # nose knows about setUpClass, but python 2.6's unittest doesn't
    # @classmethod
    # def setUpClass(cls):
    def setUp(self):
        repo = Mock('repo')
        repo.name = 'standard'
        repo.arch = 'x86_64'

        package = Mock('package')
        package.project = 'openSUSE:11.3'
        package.name = 'osc'

        self.build = obswatch.Build(package=package, repo=repo,
                                  interested={'geeko':'geeko@opensuse.org'})
        self.package = package        
        self.tt = TraceTracker()

        obswatch.SLEEP_TIME = 0

    def tearDown(self):
        minimock.restore()
        self.tt.clear()

    def test_get_latest_packages(self):
        mock('obswatch.http_GET', tracker=self.tt,
             returns=StringIO('''<?xml version="1.0" encoding="UTF-8"?>
<latest_added>
  <package created="2010-09-09T14:03:06+02:00" name="antivir" project="home:varkoly:branches:openSUSE:11.3:NonFree"/>
  <project created="2010-09-09T14:03:05+02:00" name="home:varkoly:branches:openSUSE:11.3:NonFree"/>
  <package created="2010-09-09T13:50:37+02:00" name="test9" project="home:enzokiel:test"/>
  <package created="2010-09-09T13:12:54+02:00" name="kernel-bfs-source" project="home:jingtw"/>
  <package created="2010-09-09T13:12:08+02:00" name="getdata" project="home:christiantrippe:branches:KDE:Distro:Factory"/>
  <package created="2010-09-09T13:05:13+02:00" name="perl-String-CRC32" project="home:seife:byd"/>
  <package created="2010-09-09T13:05:04+02:00" name="autogen" project="home:psmt:branches:Base:System"/>
</latest_added>'''))
        result = obswatch.get_latest_packages(7)

        assert_same_trace(self.tt,"""Called obswatch.http_GET(
        '%sstatistics/latest_updated?limit=7')""" % obswatch.APIURL)

        for p in result:
            self.assertTrue(isinstance(p, obswatch.Package))

        self.assertEqual(result[0].name, 'antivir')
        self.assertEqual(len(result), 6) # second one is a project

    def test_get_user_email(self):
        mock('obswatch.http_GET', tracker=self.tt,
             returns=StringIO('''<person>
           <login>Geeko</login>
           <email>geeko@opensuse.org</email>
           <realname>Geeko Chameleon</realname>
           <watchlist/>
           </person>'''))

        result = obswatch.get_user_email('Geeko')

        assert_same_trace(self.tt, """Called obswatch.http_GET(
            '%sperson/Geeko')""" % obswatch.APIURL)
        self.assertEqual(result, 'geeko@opensuse.org')

    def test_users_from_url(self):
        mock('obswatch.http_GET', tracker=self.tt,
             returns=StringIO('''<?xml version="1.0" encoding="UTF-8"?>
           <project name="superkde" created="2005-01-01T00:00:02+01:00" updated="2007-01-19T10:44:45+01:00">
             <title>SuperKDE</title>
             <description>SuperKDE is a heavily tuned version of KDE.</description>
             <link project="openSUSE:11.2:Update" />
             <link project="openSUSE:11.2" />
             <person role="maintainer" userid="Geeko"/>
             <person role="maintainer" userid="BrownGeeko"/>
             <group  role="reviewer"  groupid="release_team"/>
             <build>
               <disable />
             </build>
             <repository name="kde4:factory" rebuild="transitive">
               <path project="kde4" repository="factory"/>
               <arch>i386</arch>

               <arch>x86_64</arch>
             </repository>
           </project>'''))
        mock('obswatch.get_user_email', returns='geeko@opensuse.org')

        result = obswatch.get_users_from_url('%ssource/superkde/_meta' %
                                            obswatch.APIURL)
        assert_same_trace(self.tt, """Called obswatch.http_GET(
            '%ssource/superkde/_meta')""" % obswatch.APIURL)
        self.assertEqual(len(result), 2)
        self.assertEqual(result['Geeko'], 'geeko@opensuse.org')
        self.assertEqual(result['BrownGeeko'], 'geeko@opensuse.org')        

    def test_get_builds(self):
        mock('osc.core.http_GET', tracker=self.tt,
             returns=StringIO('''<?xml version="1.0" encoding="UTF-8"?>
              <project name="superkde" created="2005-01-01T00:00:02+01:00" updated="2007-01-19T10:44:45+01:00">
              <title>SuperKDE</title>
              <description>SuperKDE is a heavily tuned version of KDE.</description>
              <link project="openSUSE:11.2:Update" />
              <link project="openSUSE:11.2" />
              <person role="maintainer" userid="ernie"/>
              <group  role="reviewer"  groupid="release_team"/>
              <build>

              <disable />
              </build>
              <useforbuild>
              <disable />
              </useforbuild>
              <repository name="kde4:factory" rebuild="transitive">
              <path project="kde4" repository="factory"/>
              <arch>i386</arch>

              <arch>x86_64</arch>
              </repository>
              <repository name="suselinux-9.3">
              <path project="suselinux-9.3" repository="standard"/>
              <arch>i386</arch>
              </repository>
              <repository name="gnomespecial" rebuild="local">
              <path project="gnome3" repository="suselinux-9.3"/>

              <path project="suselinux-9.3" repository="standard"/>
              <arch>i386</arch>
              </repository>
              </project>'''))
        # source/superkde/_meta
        # gets called by osc.core.get_repos_of_project
        mock('obswatch.get_interested',
                      returns={'Geeko': 'geeko@opensuse.org'})

        superkde = Mock('package')
        superkde.name = 'superkde'
        superkde.project = 'superkde'
        superkde.created = '2007-01-19T10:44:45+01:00'
        result = obswatch.get_builds(superkde)

        assert_same_trace(self.tt, """Called osc.core.http_GET(
            '%ssource/superkde/_meta')""" % obswatch.APIURL)

    def test_build_get_remote_status(self):
        mock('obswatch.http_GET', tracker=self.tt,
             returns=StringIO('''<status package="osc" code="disabled">
                                      <details></details>
                                    </status>'''))

        code = self.build.get_remote_status()

        assert_same_trace(self.tt, """Called obswatch.http_GET(
             '%sbuild/openSUSE:11.3/standard/x86_64/osc/_status')""" %
                          obswatch.APIURL)
        self.assertEqual(code, 'disabled')


    def test_process_same_status(self):
        self.build.get_remote_status = lambda : self.build.status
        result = obswatch.process_build(self.build)

        self.assertTrue(result)
        
    def test_process_intermediate(self):
        self.build.get_remote_status = lambda : 'building'

        result = obswatch.process_build(self.build)

        self.assertTrue(result)
        self.assertEqual(self.build.status, 'building')

    def test_process_other(self):
        self.build.get_remote_status = lambda : 'excluded'
        result = obswatch.process_build(self.build)

        self.assertFalse(result)

    def test_process_unknown(self):
        self.build.get_remote_status = lambda : 'infundibulated'

        self.assertRaises(Exception, obswatch.process_build, self.build)

    def test_process_final_not_succeeded(self):
        self.build.get_remote_status = lambda : 'failed'
        result = obswatch.process_build(self.build)

        self.assertFalse(result)

    def test_final_succeeded(self):
        self.build.get_remote_status = lambda : 'succeeded'

        mock('obswatch.Build.get_binaries', returns={'foo':'bar'})
        mock('obswatch.send_email', tracker=self.tt)
        result = obswatch.process_build(self.build)        
        self.assertFalse(result)

        expected_output = """Called obswatch.send_email(
                                 'geeko',
                                 'geeko@opensuse.org',
                                 <obswatch.Build instance at ...>,
                                 {'foo': 'bar'})"""
        assert_same_trace(self.tt, expected_output)
        
    def test_interested(self):
        mock('obswatch.get_users_from_url', returns_func=lambda url: {url: url})

        result = obswatch.get_interested(self.package)

        # both the project and package page should be checked for users
        self.assertEqual(result,
                         {'https://api.opensuse.org/source/openSUSE:11.3/_meta': 'https://api.opensuse.org/source/openSUSE:11.3/_meta',
                          'https://api.opensuse.org/source/openSUSE:11.3/osc/_meta': 'https://api.opensuse.org/source/openSUSE:11.3/osc/_meta'})


    def test_send_email(self):
        mock('smtplib.SMTP', returns=Mock('smtp_connection', tracker=self.tt),
             tracker=self.tt)

        obswatch.send_email('geeko', 'geeko@opensuse.org',
                           'yourpackage',
                            {'rpm1': 'http://opensuse.org/rpm1',
                             'rpm2': 'http://opensuse.org/rpm2'})
        expected_output = """Called smtplib.SMTP('localhost')
Called smtp_connection.sendmail(
    'osc@opensuse.org',
    ['geeko@opensuse.org'],
    'To: geeko@opensuse.org\\nFrom: osc@opensuse.org\\nSubject: (osc) build succeeded: yourpackage\\n\\nThe package yourpackage has finished building and can now be downloaded from:\\nrpm1 - http://opensuse.org/rpm1\\nrpm2 - http://opensuse.org/rpm2')
Called smtp_connection.quit()
        """
        assert_same_trace(self.tt, expected_output)

if __name__ == '__main__':
    unittest.main()
