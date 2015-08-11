"""
Build a package
"""
import ConfigParser
import os
from os.path import expanduser
import tempfile

from fabric.api import task, local, shell_env
import requests

from hivemind.decorators import verbose
from hivemind import git

ARCH = "amd64"

STABLE_RELEASE = "juno"
OPENSTACK_RELEASES = ['kilo', 'juno', 'icehouse', 'havana', 'grizzly']
NECTAR_REPO = 'http://download.rc.nectar.org.au/nectar-ubuntu/'
CLOUD_ARCHIVE = 'http://mirrors.melbourne.nectar.org.au/ubuntu-cloud/ubuntu/'
UBUNTU_MIRROR = 'http://mirrors.melbourne.nectar.org.au/ubuntu-archive/ubuntu/'


def dist_from_release(release):
    if release == 'havana':
        return 'precise'
    return 'trusty'


def apt_key_recv_key(key_id, keyring):
    local("apt-key --keyring %s adv "
          "--keyserver keyserver.ubuntu.com "
          "--recv-keys %s" % (keyring, key_id))


def build_trusted():
    db = "~/.trusted.gpg"
    local("touch {0}".format(db))
    apt_key_recv_key("5EDB1B62EC4926EA", db)
    apt_key_recv_key("40976EAF437D05B5", db)
    with tempfile.NamedTemporaryFile() as tmp_gpg:
        response = requests.get(NECTAR_REPO + "nectar-custom.gpg")
        tmp_gpg.write(response.content)
        tmp_gpg.flush()
        local("gpg --no-default-keyring --keyring %s --export "
              "| gpg --no-default-keyring --keyring %s --import"
              % (tmp_gpg.name, db))


mirrors = {
    'grizzly': ["deb " + CLOUD_ARCHIVE + " precise-updates/grizzly main",
                "deb " + NECTAR_REPO + " precise main",
                "deb " + NECTAR_REPO + " precise-grizzly main",
                "deb " + NECTAR_REPO + " precise-grizzly-testing main",
                "deb " + NECTAR_REPO + " precise-testing main",
                "deb " + UBUNTU_MIRROR + " precise-updates main universe"],
    'havana': ["deb " + CLOUD_ARCHIVE + " precise-updates/havana main",
               "deb " + NECTAR_REPO + " precise main",
               "deb " + NECTAR_REPO + " precise-havana main",
               "deb " + NECTAR_REPO + " precise-havana-testing main",
               "deb " + NECTAR_REPO + " precise-testing main",
               "deb " + UBUNTU_MIRROR + " precise-updates main universe"],
    'icehouse': [
        "deb " + NECTAR_REPO + " trusty main",
        "deb " + NECTAR_REPO + " trusty-icehouse main",
        "deb " + NECTAR_REPO + " trusty-icehouse-testing main",
        "deb " + NECTAR_REPO + " trusty-testing main",
        "deb " + UBUNTU_MIRROR + " trusty-updates main universe"],
    'juno': [
        "deb " + CLOUD_ARCHIVE + " trusty-updates/juno main",
        "deb " + NECTAR_REPO + " trusty main",
        "deb " + NECTAR_REPO + " trusty-juno main",
        "deb " + NECTAR_REPO + " trusty-juno-testing main",
        "deb " + NECTAR_REPO + " trusty-testing main",
        "deb " + UBUNTU_MIRROR + " trusty-updates main universe"],
    'kilo': [
        "deb " + CLOUD_ARCHIVE + " trusty-updates/kilo main",
        "deb " + NECTAR_REPO + " trusty main",
        "deb " + NECTAR_REPO + " trusty-kilo main",
        "deb " + NECTAR_REPO + " trusty-kilo-testing main",
        "deb " + NECTAR_REPO + " trusty-testing main",
        "deb " + UBUNTU_MIRROR + " trusty-updates main universe"],
}

ubuntu_mirrors = {
    'precise': 'http://mirrors.melbourne.nectar.org.au/ubuntu-archive/ubuntu/',
    'trusty': 'http://mirrors.melbourne.nectar.org.au/ubuntu-archive/ubuntu/',
}


def package_export_dir():
    config = ConfigParser.ConfigParser()
    config.read(os.path.expanduser('~/.gbp.conf'))
    return os.path.abspath(config.get('git-buildpackage', 'export-dir'))


def pbuilder_env(os_release):
    dist = dist_from_release(os_release)
    dist_release = '{0}-{1}'.format(dist, os_release)
    output_dir = os.path.join(package_export_dir(), dist_release)
    return shell_env(ARCH=ARCH, DIST=dist_release,
                     GIT_PBUILDER_OUTPUT_DIR=output_dir)


def get_os_release_from_current_branch():
    from hivemind_contrib.packaging import parse_openstack_release
    current_branch = git.current_branch()
    return parse_openstack_release(current_branch)


@task
@verbose
def create(os_release=None):
    """Create an environment for building packages."""
    if os_release is None:
        os_release = get_os_release_from_current_branch()
    dist = dist_from_release(os_release)
    path = '/var/cache/pbuilder/base-{dist}-{os_release}-{arch}.cow'.format(
        arch=ARCH, dist=dist, os_release=os_release)

    if os.path.exists(path):
        raise Exception('PBuilder base image already exists at %s' % path)

    build_trusted()
    keyring = expanduser("~/.trusted.gpg")

    mirror = ubuntu_mirrors[dist]
    other_mirrors = mirrors[os_release]
    components = "main universe"

    with shell_env(ARCH=ARCH, DIST=dist):
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
def shell(os_release=None):
    """Open a shell in the packaging environment."""
    if os_release is None:
        os_release = get_os_release_from_current_branch()
    with pbuilder_env(os_release):
        local("git-pbuilder login")


@task
@verbose
def update(os_release=None):
    """Update the packaging environment."""
    if os_release is None:
        os_release = get_os_release_from_current_branch()
    with pbuilder_env(os_release):
        local("git-pbuilder update")
