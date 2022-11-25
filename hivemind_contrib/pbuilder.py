"""
Build a package
"""
import ConfigParser
import os
from os.path import expanduser
import tempfile

from fabric.api import local
from fabric.api import shell_env
from fabric.api import task
import requests

from hivemind.decorators import verbose
from hivemind import git

ARCH = "amd64"

STABLE_RELEASE = "ussuri"
OPENSTACK_RELEASES = ['zed', 'yoga', 'xena', 'wallaby', 'victoria', 'ussuri',
                      'train', 'stein', 'rocky', 'queens', 'pike', 'ocata',
                      'newton', 'mitaka', 'liberty', 'kilo']
UBUNTU_RELEASES = ['trusty', 'xenial', 'bionic', 'focal', 'jammy']
DEFAULT_UBUNTU = 'focal'
NECTAR_REPO = 'http://download.rc.nectar.org.au/nectar-ubuntu/'
CLOUD_ARCHIVE = 'http://download.rc.nectar.org.au/ubuntu-cloud/ubuntu/'
UBUNTU_MIRROR = 'http://download.rc.nectar.org.au/ubuntu-archive/ubuntu/'


def dist_from_release(release):
    if release in UBUNTU_RELEASES:
        return release
    elif release in ['kilo', 'liberty']:
        return 'trusty'
    elif release in ['pike', 'ocata', 'newton', 'mitaka']:
        return 'xenial'
    elif release in ['train', 'stein', 'rocky', 'queens']:
        return 'bionic'
    elif release in ['xena', 'wallaby', 'victoria', 'ussuri']:
        return 'focal'
    elif release in ['zed', 'yoga']:
        return 'jammy'
    else:
        return DEFAULT_UBUNTU


def get_build_env(os_release, ubuntu_release=None):
    if os_release in UBUNTU_RELEASES:
        return os_release
    if not ubuntu_release:
        ubuntu_release = dist_from_release(os_release)
    return "%s-%s" % (ubuntu_release, os_release)


def apt_key_recv_key(key_id, keyring):
    local("apt-key --keyring %s adv "
          "--keyserver keyserver.ubuntu.com "
          "--recv-keys %s" % (keyring, key_id))


def build_trusted():
    db = "~/.trusted.gpg"
    local("touch {0}".format(db))
    apt_key_recv_key("5EDB1B62EC4926EA", db)
    apt_key_recv_key("40976EAF437D05B5", db)
    apt_key_recv_key("3B4FE6ACC0B21F32", db)
    apt_key_recv_key("871920D1991BC93C", db)
    with tempfile.NamedTemporaryFile() as tmp_gpg:
        response = requests.get(NECTAR_REPO + "nectar-custom.gpg")
        tmp_gpg.write(response.content)
        tmp_gpg.flush()
        local("gpg --no-default-keyring --keyring %s --export "
              "| gpg --no-default-keyring --keyring %s --import"
              % (tmp_gpg.name, db))
    with tempfile.NamedTemporaryFile() as tmp_gpg:
        response = requests.get(NECTAR_REPO + "nectar-archive-key-2016.gpg")
        tmp_gpg.write(response.content)
        tmp_gpg.flush()
        local("gpg --no-default-keyring --keyring %s --export "
              "| gpg --no-default-keyring --keyring %s --import"
              % (tmp_gpg.name, db))


mirrors = {
    'xenial': [
        "deb " + CLOUD_ARCHIVE + " xenial-updates/queens main",
        "deb " + NECTAR_REPO + " xenial main",
        "deb " + NECTAR_REPO + " xenial-queens main",
        "deb " + NECTAR_REPO + " xenial-queens-testing main",
        "deb " + NECTAR_REPO + " xenial-testing main",
        "deb " + UBUNTU_MIRROR + " xenial-updates main universe"],
    'bionic': [
        "deb " + NECTAR_REPO + " bionic main",
        "deb " + NECTAR_REPO + " bionic-queens main",
        "deb " + NECTAR_REPO + " bionic-queens-testing main",
        "deb " + NECTAR_REPO + " bionic-testing main",
        "deb " + UBUNTU_MIRROR + " bionic-updates main universe"],
    'focal': [
        "deb " + NECTAR_REPO + " focal main",
        "deb " + NECTAR_REPO + " focal-testing main",
        "deb " + NECTAR_REPO + " focal-ussuri main",
        "deb " + NECTAR_REPO + " focal-ussuri-testing main",
        "deb " + UBUNTU_MIRROR + " focal-updates main universe"],
    'jammy': [
        "deb " + NECTAR_REPO + " jammy main",
        "deb " + NECTAR_REPO + " jammy-testing main",
        "deb " + NECTAR_REPO + " jammy-yoga main",
        "deb " + NECTAR_REPO + " jammy-yoga-testing main",
        "deb " + UBUNTU_MIRROR + " jammy-updates main universe"],
    'trusty-kilo': [
        "deb " + CLOUD_ARCHIVE + " trusty-updates/kilo main",
        "deb " + NECTAR_REPO + " trusty main",
        "deb " + NECTAR_REPO + " trusty-kilo main",
        "deb " + NECTAR_REPO + " trusty-kilo-testing main",
        "deb " + NECTAR_REPO + " trusty-testing main",
        "deb " + UBUNTU_MIRROR + " trusty-updates main universe"],
    'trusty-liberty': [
        "deb " + CLOUD_ARCHIVE + " trusty-updates/liberty main",
        "deb " + NECTAR_REPO + " trusty main",
        "deb " + NECTAR_REPO + " trusty-liberty main",
        "deb " + NECTAR_REPO + " trusty-liberty-testing main",
        "deb " + NECTAR_REPO + " trusty-testing main",
        "deb " + UBUNTU_MIRROR + " trusty-updates main universe"],
    'trusty-mitaka': [
        "deb " + CLOUD_ARCHIVE + " trusty-updates/mitaka main",
        "deb " + NECTAR_REPO + " trusty main",
        "deb " + NECTAR_REPO + " trusty-mitaka main",
        "deb " + NECTAR_REPO + " trusty-mitaka-testing main",
        "deb " + NECTAR_REPO + " trusty-testing main",
        "deb " + UBUNTU_MIRROR + " trusty-updates main universe"],
    'xenial-mitaka': [
        "deb " + NECTAR_REPO + " xenial main",
        "deb " + NECTAR_REPO + " xenial-mitaka main",
        "deb " + NECTAR_REPO + " xenial-mitaka-testing main",
        "deb " + NECTAR_REPO + " xenial-testing main",
        "deb " + UBUNTU_MIRROR + " xenial-updates main universe"],
    'xenial-newton': [
        "deb " + CLOUD_ARCHIVE + " xenial-updates/newton main",
        "deb " + NECTAR_REPO + " xenial main",
        "deb " + NECTAR_REPO + " xenial-newton main",
        "deb " + NECTAR_REPO + " xenial-newton-testing main",
        "deb " + NECTAR_REPO + " xenial-testing main",
        "deb " + UBUNTU_MIRROR + " xenial-updates main universe"],
    'xenial-ocata': [
        "deb " + CLOUD_ARCHIVE + " xenial-updates/ocata main",
        "deb " + NECTAR_REPO + " xenial main",
        "deb " + NECTAR_REPO + " xenial-ocata main",
        "deb " + NECTAR_REPO + " xenial-ocata-testing main",
        "deb " + NECTAR_REPO + " xenial-testing main",
        "deb " + UBUNTU_MIRROR + " xenial-updates main universe"],
    'xenial-pike': [
        "deb " + CLOUD_ARCHIVE + " xenial-updates/pike main",
        "deb " + NECTAR_REPO + " xenial main",
        "deb " + NECTAR_REPO + " xenial-pike main",
        "deb " + NECTAR_REPO + " xenial-pike-testing main",
        "deb " + NECTAR_REPO + " xenial-testing main",
        "deb " + UBUNTU_MIRROR + " xenial-updates main universe"],
    'xenial-queens': [
        "deb " + CLOUD_ARCHIVE + " xenial-updates/queens main",
        "deb " + NECTAR_REPO + " xenial main",
        "deb " + NECTAR_REPO + " xenial-queens main",
        "deb " + NECTAR_REPO + " xenial-queens-testing main",
        "deb " + NECTAR_REPO + " xenial-testing main",
        "deb " + UBUNTU_MIRROR + " xenial-updates main universe"],
    'bionic-queens': [
        "deb " + NECTAR_REPO + " bionic main",
        "deb " + NECTAR_REPO + " bionic-queens main",
        "deb " + NECTAR_REPO + " bionic-queens-testing main",
        "deb " + NECTAR_REPO + " bionic-testing main",
        "deb " + UBUNTU_MIRROR + " bionic-updates main universe"],
    'bionic-rocky': [
        "deb " + CLOUD_ARCHIVE + " bionic-updates/rocky main",
        "deb " + NECTAR_REPO + " bionic main",
        "deb " + NECTAR_REPO + " bionic-rocky main",
        "deb " + NECTAR_REPO + " bionic-rocky-testing main",
        "deb " + NECTAR_REPO + " bionic-testing main",
        "deb " + UBUNTU_MIRROR + " bionic-updates main universe"],
    'bionic-stein': [
        "deb " + CLOUD_ARCHIVE + " bionic-updates/stein main",
        "deb " + NECTAR_REPO + " bionic main",
        "deb " + NECTAR_REPO + " bionic-stein main",
        "deb " + NECTAR_REPO + " bionic-stein-testing main",
        "deb " + NECTAR_REPO + " bionic-testing main",
        "deb " + UBUNTU_MIRROR + " bionic-updates main universe"],
    'bionic-train': [
        "deb " + CLOUD_ARCHIVE + " bionic-updates/train main",
        "deb " + NECTAR_REPO + " bionic main",
        "deb " + NECTAR_REPO + " bionic-train main",
        "deb " + NECTAR_REPO + " bionic-train-testing main",
        "deb " + NECTAR_REPO + " bionic-testing main",
        "deb " + UBUNTU_MIRROR + " bionic-updates main universe"],
    'bionic-ussuri': [
        "deb " + CLOUD_ARCHIVE + " bionic-updates/ussuri main",
        "deb " + NECTAR_REPO + " bionic main",
        "deb " + NECTAR_REPO + " bionic-ussuri main",
        "deb " + NECTAR_REPO + " bionic-ussuri-testing main",
        "deb " + NECTAR_REPO + " bionic-testing main",
        "deb " + UBUNTU_MIRROR + " bionic-updates main universe"],
    'focal-ussuri': [
        "deb " + NECTAR_REPO + " focal main",
        "deb " + NECTAR_REPO + " focal-ussuri main",
        "deb " + NECTAR_REPO + " focal-ussuri-testing main",
        "deb " + NECTAR_REPO + " focal-testing main",
        "deb " + UBUNTU_MIRROR + " focal-updates main universe"],
    'focal-victoria': [
        "deb " + CLOUD_ARCHIVE + " focal-updates/victoria main",
        "deb " + NECTAR_REPO + " focal main",
        "deb " + NECTAR_REPO + " focal-victoria main",
        "deb " + NECTAR_REPO + " focal-victoria-testing main",
        "deb " + NECTAR_REPO + " focal-testing main",
        "deb " + UBUNTU_MIRROR + " focal-updates main universe"],
    'focal-wallaby': [
        "deb " + CLOUD_ARCHIVE + " focal-updates/wallaby main",
        "deb " + NECTAR_REPO + " focal main",
        "deb " + NECTAR_REPO + " focal-wallaby main",
        "deb " + NECTAR_REPO + " focal-wallaby-testing main",
        "deb " + NECTAR_REPO + " focal-testing main",
        "deb " + UBUNTU_MIRROR + " focal-updates main universe"],
    'focal-xena': [
        "deb " + CLOUD_ARCHIVE + " focal-updates/xena main",
        "deb " + NECTAR_REPO + " focal main",
        "deb " + NECTAR_REPO + " focal-xena main",
        "deb " + NECTAR_REPO + " focal-xena-testing main",
        "deb " + NECTAR_REPO + " focal-testing main",
        "deb " + UBUNTU_MIRROR + " focal-updates main universe"],
    'focal-yoga': [
        "deb " + CLOUD_ARCHIVE + " focal-updates/yoga main",
        "deb " + NECTAR_REPO + " focal main",
        "deb " + NECTAR_REPO + " focal-yoga main",
        "deb " + NECTAR_REPO + " focal-yoga-testing main",
        "deb " + NECTAR_REPO + " focal-testing main",
        "deb " + UBUNTU_MIRROR + " focal-updates main universe"],
    'jammy-yoga': [
        "deb " + NECTAR_REPO + " jammy main",
        "deb " + NECTAR_REPO + " jammy-yoga main",
        "deb " + NECTAR_REPO + " jammy-yoga-testing main",
        "deb " + NECTAR_REPO + " jammy-testing main",
        "deb " + UBUNTU_MIRROR + " jammy-updates main universe"],
    'jammy-zed': [
        "deb " + CLOUD_ARCHIVE + " jammy-updates/zed main",
        "deb " + NECTAR_REPO + " jammy main",
        "deb " + NECTAR_REPO + " jammy-zed main",
        "deb " + NECTAR_REPO + " jammy-zed-testing main",
        "deb " + NECTAR_REPO + " jammy-testing main",
        "deb " + UBUNTU_MIRROR + " jammy-updates main universe"],
}

ubuntu_mirrors = {
    'trusty': 'http://download.rc.nectar.org.au/ubuntu-archive/ubuntu/',
    'xenial': 'http://download.rc.nectar.org.au/ubuntu-archive/ubuntu/',
    'bionic': 'http://download.rc.nectar.org.au/ubuntu-archive/ubuntu/',
    'focal': 'http://download.rc.nectar.org.au/ubuntu-archive/ubuntu/',
    'jammy': 'http://download.rc.nectar.org.au/ubuntu-archive/ubuntu/',
}


def package_export_dir():
    config = ConfigParser.ConfigParser()
    config.read(os.path.expanduser('~/.gbp.conf'))
    try:
        return os.path.abspath(config.get('git-buildpackage', 'export-dir'))
    except ConfigParser.NoSectionError:
        return os.path.abspath(config.get('buildpackage', 'export-dir'))


def pbuilder_env(os_release, name=None, ubuntu_release=None):
    dist_release = get_build_env(os_release, ubuntu_release)
    if name:
        dist_release = '{0}-{1}'.format(dist_release, name)
    output_dir = os.path.join(package_export_dir(), dist_release)
    return shell_env(ARCH=ARCH, DIST=dist_release,
                     GIT_PBUILDER_OUTPUT_DIR=output_dir)


def get_os_release_from_current_branch():
    from hivemind_contrib.debpackaging import parse_openstack_release
    current_branch = git.current_branch()
    return parse_openstack_release(current_branch)


@task
@verbose
def create(os_release=None, extra_mirror=None, name=None, ubuntu_release=None):
    """Create an environment for building packages."""
    if os_release is None:
        os_release = get_os_release_from_current_branch()
    dist_release = get_build_env(os_release, ubuntu_release)
    path = '/var/cache/pbuilder/base-{dist_release}'.format(
        dist_release=dist_release)
    if name:
        path = '{path}-{name}'.format(path=path, name=name)
    path = '{path}-{arch}.cow'.format(path=path, arch=ARCH)

    if os.path.exists(path):
        raise Exception('PBuilder base image already exists at %s' % path)

    build_trusted()
    keyring = expanduser("~/.trusted.gpg")

    ubuntu_version = dist_release.split('-')[0]
    mirror = ubuntu_mirrors[ubuntu_version]
    other_mirrors = mirrors[dist_release]
    components = "main universe"

    if extra_mirror:
        other_mirrors.append(extra_mirror)

    with shell_env(ARCH=ARCH, DIST=ubuntu_version):
        local('git-pbuilder create --basepath {basepath}'
              ' --mirror {mirror}'
              ' --components "{components}"'
              ' --othermirror "{mirrors}"'
              ' --keyring {keyring}'
              ' --debootstrapopts'
              ' --keyring={keyring}'.format(
                  mirror=mirror,
                  components=components,
                  mirrors="|".join(other_mirrors),
                  keyring=keyring,
                  basepath=path))


@task
@verbose
def shell(os_release=None, name=None, ubuntu_release=None):
    """Open a shell in the packaging environment."""
    if os_release is None:
        os_release = get_os_release_from_current_branch()
    with pbuilder_env(os_release, name, ubuntu_release):
        local("git-pbuilder login")


@task
@verbose
def update(os_release=None, name=None, ubuntu_release=None):
    """Update the packaging environment."""
    if os_release is None:
        os_release = get_os_release_from_current_branch()
    with pbuilder_env(os_release, name, ubuntu_release):
        local("git-pbuilder update")
