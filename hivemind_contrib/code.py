import os
from fabric.api import (env, task, local)

from hivemind.decorators import verbose
from hivemind import util, git
from hivemind_contrib import gerrit

import github
from github.GithubException import UnknownObjectException


def get_github_username():
    with util.hide_and_ignore():
        username = local('git config --get github.user', capture=True)
    return username


def get_github_token():
    with util.hide_and_ignore():
        token = local('git config --get github.token', capture=True)
    return token


@task
@verbose
def setup_project(name, org_name='NeCTAR-RC', fork_from=None,
                  openstack_version=None, team_id=338031,
                  stable_ref='openstack/stable/'):
    """Create a new project.

    Fir github integration you will need to have to following in your global
    git.config:

    [github]
    user  = <github-username>
    token = <github-api-token>

    Currently you need to run this command inside the directory of the git
    cloned repo.
    """

    github_user = get_github_username()
    github_token = get_github_token()
    full_name = org_name + '/' + name

    if org_name == 'internal':
        pass
    else:
        g = github.Github(github_user, github_token)
        org = g.get_organization(org_name)

        if fork_from:
            fork_repo = g.get_repo(fork_from)
            try:
                repo = org.get_repo(name)
            except UnknownObjectException:
                repo = None
            if not repo:
                repo = org.create_fork(fork_repo)
                print("Created fork %s" % repo.name)
        else:
            try:
                repo = org.get_repo(name)
            except UnknownObjectException:
                repo = org.create_repo(name)
                print("Created repo %s" % repo.name)

        team = org.get_team(team_id)
        team.add_to_repos(repo)
        print("Added %s team to repo" % team.name)

    try:
        gerrit.create(full_name, parent='Public-Projects')
        print("Added gerrit project %s" % full_name)
    except:
        pass
    
    gerrit_user = gerrit.gitreview_username()
    try:
        local('git remote rm origin')
    except:
        pass

    try:
        local('git remote add openstack %s' % fork_repo.clone_url)
    except:
        pass
    try:
        local('git remote add nectar https://github.com/%s/%s.git' % (org_name,
                                                                      name))
    except:
        pass
    local('git fetch --all')
    local('git checkout -b nectar/%s %s%s' % (openstack_version,
                                              stable_ref,
                                              openstack_version))
    local('git push ssh://%s@review.rc.nectar.org.au:29418/%s nectar/%s' % (
        gerrit_user, full_name, openstack_version))

    gerrit_config = """[gerrit]
host=review.rc.nectar.org.au
port=29418
project=%(org_name)s/%(name)s.git
defaultbranch=nectar/%(openstack_version)s
""" % {'name': name, 'org_name': org_name, 'openstack_version': openstack_version}
    gerrit_config_file = open('.gitreview', 'w')
    gerrit_config_file.write(gerrit_config)
    gerrit_config_file.close()
    local('git add .gitreview')
    local('git commit -m "Use NeCTAR gerrit"')
    local('git review')
