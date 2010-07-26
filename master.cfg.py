# -*- python -*-
# ex: set syntax=python:

from buildbot.buildslave import BuildSlave
from buildbot.changes.svnpoller import SVNPoller
from buildbot.process import factory
from buildbot.process.properties import WithProperties
from buildbot.scheduler import Scheduler, Dependent
from buildbot.status import html, mail
from buildbot.steps.source import SVN
from buildbot.steps.shell import Compile, ShellCommand, Test
from buildbot.steps.transfer import FileUpload
from buildbot.steps.python_twisted import Trial

import clementine_passwords

DEBVERSION = "0.4.90"
SVNURL     = "http://clementine-player.googlecode.com/svn/trunk/"
UPLOADBASE = "/var/www/clementine-player.org/builds"
WORKDIR    = "build/bin"
CMAKE_ENV  = {'BUILDBOT_REVISION': WithProperties("%(revision)s")}
SVN_ARGS   = {"svnurl": SVNURL, "extra_args": ['--accept', 'theirs-full']}


# Basic config
c = BuildmasterConfig = {
  'projectName':  "Clementine",
  'projectURL':   "http://www.clementine-player.org/",
  'buildbotURL':  "http://buildbot.clementine-player.org/",
  'slavePortnum': clementine_passwords.PORT,
  'slaves': [
    BuildSlave("zaphod",    clementine_passwords.ZAPHOD),
    BuildSlave("Chopstick", clementine_passwords.CHOPSTICK),
  ],
  'sources': [
    SVNPoller(
      svnurl=SVNURL,
      pollinterval=60*60, # seconds
      histmax=10,
      svnbin='/usr/bin/svn',
    ),
  ],
  'status': [
    html.WebStatus(
      http_port="tcp:8010:interface=127.0.0.1",
      allowForce=False
    ),
    mail.MailNotifier(
      fromaddr="buildmaster@zaphod.purplehatstands.com",
      lookup="gmail.com",
      mode="failing",
    ),
  ],
}


# Schedulers
sched_linux = Scheduler(name="linux", branch=None, treeStableTimer=2*60, builderNames=[
  "Linux Debug",
  "Linux Release",
])

sched_winmac = Scheduler(name="winmac", branch=None, treeStableTimer=2*60, builderNames=[
  "MinGW Debug",
  "MinGW Release",
  "Mac Release",
])

sched_deb = Dependent(name="deb", upstream=sched_linux, builderNames=[
  "Deb Lucid 64-bit",
  "Deb Lucid 32-bit",
])

sched_ppa = Dependent(name="ppa", upstream=sched_deb, builderNames=[
  "PPA Lucid",
])

c['schedulers'] = [
  sched_linux,
  sched_winmac,
  sched_deb,
  sched_ppa,
]


# Builders
def MakeLinuxBuilder(type):
  f = factory.BuildFactory()
  f.addStep(SVN(**SVN_ARGS))
  f.addStep(ShellCommand(workdir=WORKDIR, command=[
      "cmake", "..",
      "-DQT_LCONVERT_EXECUTABLE=/home/buildbot/qtsdk-2010.02/qt/bin/lconvert",
      "-DCMAKE_BUILD_TYPE=" + type,
  ]))
  f.addStep(Compile(workdir=WORKDIR, command=["make"]))
  f.addStep(Test(workdir=WORKDIR, command=[
      "xvfb-run",
      "-a",
      "-n", "10",
      "make", "test"
  ]))
  return f

def MakeDebBuilder(arch, chroot=None):
  schroot_cmd = []
  if chroot is not None:
    schroot_cmd = ["schroot", "-p", "-c", chroot, "--"]

  cmake_cmd = schroot_cmd + ["cmake", ".."]
  dpkg_cmd  = schroot_cmd + ["dpkg-buildpackage", "-b", "-uc", "-us"]

  f = factory.BuildFactory()
  f.addStep(SVN(**SVN_ARGS))
  f.addStep(ShellCommand(command=cmake_cmd, workdir=WORKDIR))
  f.addStep(ShellCommand(command=dpkg_cmd, env=CMAKE_ENV))
  f.addStep(FileUpload(
      mode=0644,
      slavesrc="../clementine_%s_%s.deb" % (DEBVERSION, arch),
      masterdest=WithProperties(UPLOADBASE +
        "/ubuntu-lucid/clementine_r%(got_revision)s_" + arch + ".deb")))
  return f

def MakeMingwBuilder(type, suffix, strip):
  test_env = dict(CMAKE_ENV)
  test_env.update({'GTEST_FILTER': '-Formats/FileformatsTest.GstCanDecode/5:Formats/FileformatsTest.GstCanDecode/6'})

  f = factory.BuildFactory()
  f.addStep(SVN(**SVN_ARGS))
  f.addStep(ShellCommand(workdir=WORKDIR, env=CMAKE_ENV, command=[
      "cmake", "..",
      "-DCMAKE_TOOLCHAIN_FILE=/home/buildbot/Toolchain-mingw32.cmake",
      "-DQT_MOC_EXECUTABLE=/home/buildbot/qtsdk-2010.02/qt/bin/moc",
      "-DQT_UIC_EXECUTABLE=/home/buildbot/qtsdk-2010.02/qt/bin/uic",
      "-DCMAKE_BUILD_TYPE=" + type
  ]))
  f.addStep(Compile(command=["make"], workdir=WORKDIR, env=CMAKE_ENV))
  f.addStep(Test(workdir=WORKDIR, env=test_env, command=[
      "xvfb-run",
      "-a",
      "-n", "30",
      "make", "test"
  ]))
  f.addStep(ShellCommand(command=["makensis", "clementine.nsi"], workdir="build/dist/windows"))
  f.addStep(FileUpload(
      mode=0644,
      slavesrc="dist/windows/ClementineSetup.exe",
      masterdest=WithProperties(UPLOADBASE + "/win32/ClementineSetup-r%(got_revision)s-" + suffix + ".exe")))
  return f

def MakeMacBuilder():
  f = factory.BuildFactory()
  f.addStep(SVN(**SVN_ARGS))
  f.addStep(ShellCommand(
      workdir=WORKDIR,
      env={'PKG_CONFIG_PATH': '/usr/local/lib/pkgconfig'},
      command=[
        "cmake", "..",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_OSX_ARCHITECTURES=i386",
        "-DQT_QMAKE_EXECUTABLE=/usr/local/Trolltech/Qt-4.7.0/bin/qmake",
        "-DCMAKE_OSX_SYSROOT=/Developer/SDKs/MacOSX10.6.sdk",
        "-DCMAKE_OSX_DEPLOYMENT_TARGET=10.6",
      ],
  ))
  f.addStep(Compile(command=["make", "-j2"], workdir=WORKDIR))
  f.addStep(Test(
      command=["make", "test", "-j2"],
      workdir=WORKDIR,
      env={'DYLD_FRAMEWORK_PATH': '/usr/local/Trolltech/Qt-4.7.0/lib',
          'GTEST_FILTER': '-Formats/FileformatsTest.GstCanDecode*:SongLoaderTest.LoadRemote*'}))
  f.addStep(ShellCommand(command=["make", "install"], workdir=WORKDIR))
  f.addStep(ShellCommand(command=["make", "bundle"], workdir=WORKDIR))
  f.addStep(ShellCommand(command=["make", "dmg"], workdir=WORKDIR))
  f.addStep(FileUpload(
      mode=0644,
      slavesrc="bin/clementine.dmg",
      masterdest=WithProperties(UPLOADBASE + "/mac/clementine-r%(got_revision)s-rel.dmg")))
  return f

def MakePPABuilder():
  f = factory.BuildFactory()
  f.addStep(ShellCommand(command=["/home/buildbot/uploadtoppa.sh"],
    env=CMAKE_ENV,
    workdir="build",
  ))
  return f

def BuilderDef(name, dir, factory, slave="zaphod"):
  return {
    'name': name,
    'builddir': dir,
    'factory': factory,
    'slavename': slave,
  }

c['builders'] = [
  BuilderDef("Linux Debug",      "clementine_linux_debug",   MakeLinuxBuilder('Debug')),
  BuilderDef("Linux Release",    "clementine_linux_release", MakeLinuxBuilder('Release')),
  BuilderDef("Deb Lucid 64-bit", "clementine_deb_lucid_64",  MakeDebBuilder('amd64')),
  BuilderDef("Deb Lucid 32-bit", "clementine_deb_lucid_32",  MakeDebBuilder('i386', chroot='lucid-32')),
  BuilderDef("PPA Lucid",        "clementine_ppa",           MakePPABuilder()),
  BuilderDef("MinGW Debug",      "clementine_mingw_debug",   MakeMingwBuilder('Debug', 'dbg', strip=False)),
  BuilderDef("MinGW Release",    "clementine_mingw_release", MakeMingwBuilder('Release', 'rel', strip=True)),
  BuilderDef("Mac Release",      "clementine_mac_release",   MakeMacBuilder(), slave="Chopstick"),
]
