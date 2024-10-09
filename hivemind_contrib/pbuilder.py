"""
Build a package
"""
import configparser
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
OPENSTACK_RELEASES = ['2024.1', '2023.2', '2023.1', 'zed', 'yoga', 'xena',
                      'wallaby', 'victoria', 'ussuri']
UBUNTU_RELEASES = ['focal', 'jammy', 'noble']
DEFAULT_UBUNTU = 'jammy'
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
    elif release in ['2023.2', '2023.1', 'zed', 'yoga']:
        return 'jammy'
    elif release in ['2024.1']:
        return 'noble'
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
    'noble': [
        "deb " + NECTAR_REPO + " noble main",
        "deb " + NECTAR_REPO + " noble-testing main",
        "deb " + NECTAR_REPO + " noble-caracal main",
        "deb " + NECTAR_REPO + " noble-caracal-testing main",
        "deb " + UBUNTU_MIRROR + " noble-updates main universe"],
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
    'jammy-2023.1': [
        "deb " + CLOUD_ARCHIVE + " jammy-updates/antelope main",
        "deb " + NECTAR_REPO + " jammy main",
        "deb " + NECTAR_REPO + " jammy-antelope main",
        "deb " + NECTAR_REPO + " jammy-antelope-testing main",
        "deb " + NECTAR_REPO + " jammy-testing main",
        "deb " + UBUNTU_MIRROR + " jammy-updates main universe"],
    'jammy-2023.2': [
        "deb " + CLOUD_ARCHIVE + " jammy-updates/bobcat main",
        "deb " + NECTAR_REPO + " jammy main",
        "deb " + NECTAR_REPO + " jammy-bobcat main",
        "deb " + NECTAR_REPO + " jammy-bobcat-testing main",
        "deb " + NECTAR_REPO + " jammy-testing main",
        "deb " + UBUNTU_MIRROR + " jammy-updates main universe"],
    'noble-2024.1': [
        "deb " + NECTAR_REPO + " noble main",
        "deb " + NECTAR_REPO + " noble-caracal main",
        "deb " + NECTAR_REPO + " noble-caracal-testing main",
        "deb " + NECTAR_REPO + " noble-testing main",
        "deb " + UBUNTU_MIRROR + " noble-updates main universe"],
}

ubuntu_mirrors = {
    'focal': 'http://download.rc.nectar.org.au/ubuntu-archive/ubuntu/',
    'jammy': 'http://download.rc.nectar.org.au/ubuntu-archive/ubuntu/',
    'noble': 'http://download.rc.nectar.org.au/ubuntu-archive/ubuntu/',
}


def package_export_dir():
    config = configparser.ConfigParser()
    config.read(os.path.expanduser('~/.gbp.conf'))
    try:
        return os.path.abspath(config.get('git-buildpackage', 'export-dir'))
    except configparser.NoSectionError:
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
