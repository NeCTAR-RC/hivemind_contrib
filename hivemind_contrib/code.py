from fabric.api import local
from fabric.api import task
import github
from github.GithubException import UnknownObjectException
import json
import requests

from hivemind.decorators import verbose
from hivemind import util
from hivemind_contrib import gerrit
from hivemind_contrib import gitea


def get_github_username():
    with util.hide_and_ignore():
        username = local('git config --get github.user', capture=True)
    return username


def get_github_token():
    with util.hide_and_ignore():
        token = local('git config --get github.token', capture=True)
    return token


def setup_gitea(org_name, name):
    try:
        gitea.create_repo(org_name, name)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 409:
            print(json.loads(e.response.text)['message'])
            pass
        else:
            raise e
    gitea.add_teams_to_repo(org_name, name)


def setup_github(org_name, name, team_id, fork_from):
    fork_repo = None
    github_user = get_github_username()
    github_token = get_github_token()
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
        fork_repo = None
        try:
            repo = org.get_repo(name)
        except UnknownObjectException:
            repo = org.create_repo(name)
            print("Created repo %s" % repo.name)

    team = org.get_team(team_id)
    team.add_to_repos(repo)
    print("Added %s team to repo" % team.name)
    return fork_repo


@task
@verbose
def setup_project(name, org_name='NeCTAR-RC', fork_from=None,
                  openstack_version=None, team_id=338031,
                  stable_ref='openstack/stable/'):
    """Create a new project.

    org_name:
        NeCTAR-RC implies github
        internal implies git.rc.nectar.org.au

    For github integration you will need to have to following in your global
    git.config:

    [github]
    user  = <github-username>
    token = <github-api-token>

    NOTE: you need to run this command inside the directory of the git
    cloned repo.

    """

    full_name = org_name + '/' + name

    if org_name == 'internal':
        print("adding repo to Gitea")
        setup_gitea(org_name, name)
        fork_repo = None

    if org_name == 'NeCTAR-RC':
        print("adding repo to GitHub")
        fork_repo = setup_github(org_name, name, team_id, fork_from)

    if org_name == 'NeCTAR-RC':
        parent = 'Public-Projects'
    else:
        parent = 'CoreServices-Projects'

    try:
        gerrit.create(full_name, parent=parent)
        print("Added gerrit project %s" % full_name)
    except:  # noqa
        pass

    gerrit_user = gerrit.gitreview_username()
    try:
        local('git remote rm origin')
    except:  # noqa
        pass

    if fork_repo:
        try:
            local('git remote add openstack %s' % fork_repo.clone_url)
        except:  # noqa
            pass

    if openstack_version:
        default_branch = "nectar/%s" % openstack_version
    else:
        default_branch = 'master'

    if org_name == 'internal':
        try:
            local('git remote add origin git@git.rc.nectar.org.au:%s' %
                  full_name)
        except:  # noqa
            pass
    else:
        try:
            local('git remote add nectar https://github.com/%s.git' %
                  full_name)
        except:  # noqa
            pass

    local('git fetch --all')
    if openstack_version:
        local('git checkout -b nectar/%s %s%s' % (openstack_version,
                                                  stable_ref,
                                                  openstack_version))

    local('git push ssh://%s@review.rc.nectar.org.au:29418/%s %s' % (
        gerrit_user, full_name, default_branch))

    gerrit_config = """[gerrit]
host=review.rc.nectar.org.au
port=29418
project=%(org_name)s/%(name)s.git
defaultbranch=%(default_branch)s
""" % {'name': name, 'org_name': org_name, 'default_branch': default_branch}
    gerrit_config_file = open('.gitreview', 'w')
    gerrit_config_file.write(gerrit_config)
    gerrit_config_file.close()
    local('git add .gitreview')
    local('git commit -m "Use Nectar gerrit"')
    local('git review')
