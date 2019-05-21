from fabric.api import local
from fabric.api import task

from hivemind.decorators import verbose
from hivemind import util
from hivemind_contrib import gerrit
from hivemind_contrib import gitea

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
def setup_project(
    name,                   # reponame
    org_name='NeCTAR-RC',   # NeCTAR-RC => github, internal => git.rc.nectar.org.au
    api_token=None,         # for gitea API
    url=None,               # for gitea and testing
    teamidlist="",          # a csv list of team IDs for gitea repos
    sslverify=True,         # only needed for test
    list_teams=False,       # just list the team names and ID's for an org.
    fork_from=None,
    openstack_version=None,
    team_id=338031,
    stable_ref='openstack/stable/'
    ):
    """Create a new project.

    For github integration you will need to have to following in your global

    git.config:

    [github]
    user  = <github-username>
    token = <github-api-token>

    NOTE: you need to run this command inside the directory of the git
    cloned repo.
    """

    github_user = get_github_username()
    github_token = get_github_token()
    full_name = org_name + '/' + name
    if org_name == 'internal':
        fork_repo = None
        #   get config from config.ini file
        config = gitea.get_gitea_config(url, api_token, teamidlist, sslverify)
        #   use config file values where no values passed in from CLI
        if url is None:
            url = config["url"]
        if api_token is None:
            api_token = config["token"]
        if not sslverify:
            sslverify = config["sslverify"]
        if list_teams:   # Just list the teams for the organisation
            gitea.getteamIDs(org_name, url, api_token, sslverify)
            return()
        if teamidlist =="":
            teamidlist = config["teamidlist"]
        gitea.makerepo(org_name, name, url, api_token, sslverify)
        print("Creating repo %s/%s" % (org_name, name))
        if teamidlist != "":
            for teamID in teamidlist:
                gitea.teamifyrepo(org_name, name, teamID, url, api_token, sslverify)
        print("Done!")
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
            fork_repo = None
            try:
                repo = org.get_repo(name)
            except UnknownObjectException:
                repo = org.create_repo(name)
                print("Created repo %s" % repo.name)

        team = org.get_team(team_id)
        team.add_to_repos(repo)
        print("Added %s team to repo" % team.name)

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
            local('git remote add origin git@git.melbourne.nectar.org.au:%s' %
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
    local('git commit -m "Use NeCTAR gerrit"')
    local('git review')
