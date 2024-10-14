import os

from fabric.api import local
from fabric.api import task

from hivemind.decorators import verbose
from hivemind import git
from hivemind import util


def gitreview_username():
    with util.hide_and_ignore():
        username = local('git config --get gitreview.username', capture=True)
    return username or os.environ['USER']


# Gerrit doesn't allow shell access, so run() doesn't work here.
def gerrit(command):
    cmd('gerrit', command)


def cmd(*args):
    user = gitreview_username()
    command = ' '.join(args)
    local(f'ssh -p 29418 {user}@review.rc.nectar.org.au {command}')


@task
@verbose
def ls():
    """List projects in gerrit."""
    gerrit('ls-projects')


@task
@verbose
def create(name, parent='All-Projects'):
    """Create a new project in gerrit."""
    gerrit(f'create-project {name} -p {parent}')


@task
@verbose
def clone(project_name):
    """Clone a repository from gerrit.

    :param str project_name: The name of the repository you wish to
      clone. (e.g NeCTAR-RC/puppet-openstack)

    """
    user = gitreview_username()
    project = project_name.split('/')[-1]
    local(
        f'git clone ssh://{user}@review.rc.nectar.org.au:29418/{project_name} {project}'
    )


@task
@verbose
def checkout_config(remote='gerrit'):
    """Checkout a projects configuration branch."""
    git.assert_in_repository()
    local(
        f'git fetch {remote} '
        f'refs/meta/config:refs/remotes/{remote}/meta/config'
    )
    local('git checkout meta/config')


@task
@verbose
def push_config(remote='gerrit'):
    """Push a projects configuration branch."""
    git.assert_in_repository()
    local(f'git push {remote} meta/config:refs/meta/config')


@task
@verbose
def push_without_review(project_name, branch):
    """Push the given git branch to a remote gerrit repo."""
    git.assert_in_repository()
    user = gitreview_username()
    local(
        f'git push ssh://{user}@review.rc.nectar.org.au:29418/{project_name} '
        f'{branch}:refs/heads/{branch}'
    )


@task
@verbose
def replicate(url=None):
    """Replicate projects to external repositories.

    Replicates all project by default.
    Use --url to restrict by target repository URL substring.
    """
    if url is None:
        arg = '--all'
    else:
        arg = f'--url {url}'
    cmd('replication start', arg)


@task
@verbose
def sql():
    cmd('gerrit gsql')
