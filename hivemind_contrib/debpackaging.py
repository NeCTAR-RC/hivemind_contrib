"""
Help building packages.

Examples:

Uploading
sixpack uploadpackage:./packaging/cpuset_1.5.6-3.1~nectar0_amd64.changes

"""
import email
import os
import re

from debian import deb822
from fabric.api import execute
from fabric.api import hosts
from fabric.api import local
from fabric.api import run
from fabric.api import settings
from fabric.api import task

from hivemind.decorators import verbose
from hivemind import git

from hivemind_contrib import pbuilder
from hivemind_contrib import repo


def debian_branch(version):
    return "debian/{major}.{minor}".format(**version)


def split_branch(branch):
    # Openstack style
    release = branch.split("/")
    if len(release) > 1:
        return release[1]

    # Nectar style
    release = branch.split("_")
    if len(release) > 1:
        return release[1]


def parse_openstack_release(branch):
    release = split_branch(branch)
    if release in pbuilder.OPENSTACK_RELEASES:
        return release
    elif release in pbuilder.UBUNTU_RELEASES:
        return release
    return pbuilder.STABLE_RELEASE


GIT_DESCRIBE_VERSION_REGEX = re.compile(
    r"""
    ^v?(?P<major>\d+)\.
    (?P<minor>\d+)
    (?:\.(?P<patch>\d+(\.\w+){0,1})){0,1}
    (?:-(?P<commits>\d+)
    -g(?P<revision>[0-9a-f]+)){0,1}$""",
    re.VERBOSE)


def git_version():
    version = git.describe()
    match = GIT_DESCRIBE_VERSION_REGEX.search(version)
    if not match:
        raise Exception("Unable to parse version %s" % version)
    return match.groupdict()


def debian_version(old_version, version):
    """Convert a git version to a debian one."""
    new_version = version.copy()
    deb_version = ""
    if ":" in old_version:  # version has epoc.
        epoc = old_version.split(":")[0] + ":"
        deb_version += epoc
    deb_version += "{major}.{minor}"
    if new_version['patch'] is not None:
        deb_version += ".{patch}"
    else:
        deb_version += ".0"
    if new_version['revision'] is not None:
        deb_version += ".{commits}.g{revision}"
    deb_version += "+{distribution}-{debian}"
    return deb_version.format(**new_version)


def backport_version(version, revision=1):
    return "%s+nectar%s" % (version, revision)


def version_without_epoc(version):
    if ":" in version:
        return version.split(":")[1]
    return version


def dpkg_parsechangelog():
    res = local("dpkg-parsechangelog", capture=True)
    return email.message_from_string(res)


def package_filepath(source_package, extension):
    return "{0}/{1}/{2}_{3}_{4}.{5}".format(
        pbuilder.package_export_dir(),
        source_package["Distribution"],
        source_package["Source"],
        version_without_epoc(source_package["Version"]),
        pbuilder.ARCH,
        extension)


def changes_filepath(source_package):
    return package_filepath(source_package, 'changes')


def upload_filepath(source_package):
    return package_filepath(source_package, 'upload')


def pbuilder_buildpackage(release, name=None):
    with pbuilder.pbuilder_env(release, name):
        local("git-pbuilder -sa")


def git_buildpackage(current_branch, upstream_tree, release,
                     ubuntu_release=None, name=None):
    with pbuilder.pbuilder_env(release, name, ubuntu_release):
        local("gbp buildpackage -sa --git-debian-branch={0} "
              "--git-upstream-tree={1} --git-no-pristine-tar "
              "--git-force-create".format(current_branch, upstream_tree))


@task
@verbose
@hosts("repo@download.rc.nectar.org.au")
def uploadpackage(changes, delete_existing=False):
    """Upload a package to the repository, using the changes file."""
    if delete_existing:
        data = open(changes).read()
        source_package = deb822.Changes(data)
        # Delete .upload file so dupload always refreshes the files.
        upload = upload_filepath(source_package)
        local("rm -f {0}".format(upload))
    local("dupload {0}".format(changes))
    if delete_existing:
        # Remove previous package from repository.
        distribution = "{0}-testing".format(source_package["Distribution"])
        execute(repo.rm_packages, distribution, source_package["Source"])
    # Import new packages into repository.
    run("import-new-debs.sh")


def get_debian_commit_number():
    upstream_date = local("git log -1 --pretty='%ci' ORIG_HEAD",
                          capture=True)
    command = "git log --oneline --no-merges --since='{0}' | wc -l".format(
        upstream_date)
    return local(command, capture=True)


def discover_debian_branch(current_branch, version, os_release):
    if os.path.exists(os.path.join(git.root_dir(), 'debian/')):
        deb_branch = current_branch
    else:
        deb_branch = debian_branch(version)
        if not git.branch_exists(deb_branch):
            deb_branch = "debian/{0}".format(os_release)
        if not git.branch_exists(deb_branch):
            deb_branch = 'debian'
        assert git.branch_exists(deb_branch), \
            "Debian branch %s doesn't exist" % deb_branch
    return deb_branch


@task
@verbose
def buildpackage(os_release=None, name=None, upload=True, ubuntu_release=None):
    """Build a package for the current repository."""
    git.assert_in_repository()
    dbus_address = os.environ.pop('DBUS_SESSION_BUS_ADDRESS', None)
    version = git_version()
    current_branch = git.current_branch()
    if os_release is None:
        os_release = parse_openstack_release(current_branch)
    deb_branch = discover_debian_branch(current_branch, version, os_release)
    with git.temporary_merge(deb_branch) as merge:
        source_package = dpkg_parsechangelog()
        current_version = source_package["Version"]
        version['debian'] = get_debian_commit_number()
        if ubuntu_release:
            dist = ubuntu_release
        else:
            dist = pbuilder.dist_from_release(os_release)
        dist_release = pbuilder.get_build_env(os_release, ubuntu_release)
        version['distribution'] = dist
        release_version = debian_version(current_version, version)
        local("dch -v {0} -D {1} --force-distribution 'Released'"
              .format(release_version, dist_release))
        local("git add debian/changelog")
        local("git commit -m \"{0}\"".format("Updated Changelog"))
        git_buildpackage(current_branch, upstream_tree=merge.old_head,
                         release=os_release, name=name,
                         ubuntu_release=ubuntu_release)
        # Regenerate the source package information since it's changed
        # since we updated the changelog.
        source_package = dpkg_parsechangelog()
        changes = changes_filepath(source_package)
    if upload:
        execute(uploadpackage, changes)
    if dbus_address:
        os.environ['DBUS_SESSION_BUS_ADDRESS'] = dbus_address


@task
@verbose
def buildbackport(os_release=None, name=None, revision=1, upload=True):
    """Build a package from a downloaded deb source."""
    assert os.path.exists('debian/'), "can't find debian directory."
    source_package = dpkg_parsechangelog()
    current_version = source_package["Version"]
    if not os_release:
        os_release = pbuilder.STABLE_RELEASE
    dist = pbuilder.dist_from_release(os_release)
    release_version = backport_version(current_version, revision)
    if 'nectar' not in current_version:
        local("dch -v {0} -D {1}-{2} --force-distribution 'Backported'"
              .format(release_version, dist, os_release))
    pbuilder_buildpackage(release=os_release, name=name)
    if upload:
        # Regenerate the source package information since it's changed
        # since we updated the changelog.
        source_package = dpkg_parsechangelog()
        changes = changes_filepath(source_package)
        execute(uploadpackage, changes)


@task
@verbose
def promote(package_name,
            release='%s-%s' % (
                pbuilder.dist_from_release(pbuilder.STABLE_RELEASE),
                pbuilder.STABLE_RELEASE)):
    execute(repo.cp_package, package_name, release + '-testing', release)


@task
@verbose
def create_deb_branch(branch_name, source_debian_dir):
    """Create a debian branch from a source debian directory."""
    # Make sure the repo is clean, since we run git clean later
    # without confirmation.
    git.assert_clean_repository()
    local("git symbolic-ref HEAD refs/heads/{0}".format(branch_name))
    local("rm .git/index")
    local("git clean -fdx")
    local("cp -r {0} debian".format(source_debian_dir))
    local(r"""sed -i "/export DH_VERBOSE/ a\
           export OSLO_PACKAGE_VERSION=\$(shell dpkg-parsechangelog """
           """| sed -n -e 's/^Version: //p')" debian/rules""")
    local("git add debian")
    local('git commit -m "Initial import of debian package"')


@task
@verbose
def refresh_patches():
    git.assert_clean_repository()
    current_branch = git.current_branch()
    os_release = parse_openstack_release(current_branch)
    version = git_version()
    deb_branch = discover_debian_branch(current_branch, version, os_release)
    with settings(warn_only=True):
        local("git checkout %s -- debian" % deb_branch)
        more_patches = True
        while more_patches:
            rv = local("quilt push && quilt refresh")
            more_patches = rv.return_code == 0
        local("quilt pop -a")
        local("git checkout %s" % deb_branch)
        local("git add -u")
        local('git commit -m "Refreshed patches"')
        local("git checkout %s" % current_branch)
        local("git clean -fdx")
