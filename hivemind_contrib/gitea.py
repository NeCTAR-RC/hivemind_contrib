import json
import requests
from hivemind.decorators import verbose, configurable
from fabric.utils import error, warn
from fabric.api import task


#  see https://git.test.rc.nectar.org.au/api/swagger


@configurable('gitea')
@verbose
def get_gitea_config(url, token, teamidlist="", sslverify=True):
    '''
    #   expecting config.ini contant like the following:
    #
    #   [cfg:hivemind.gitea]
    #    @doc = create a repo on git.rc.nectar.org.au
    #    @command = code.setup_project
    #    url = git.test.rc.nectar.org.au
    #    SSLverify = true
    #    token = abcdefghijklmnopqurstuvwxyz1234567890abc
    #    teamidlist = "13, 19, 10"
    #
    #   for prod:
    #    Owners: 4
    #    CI: 19
    #    CoreServices: 10
    #    Gerrit: 13
    #
    #   remember - this is for internal git repo config so gerrit
    #   can manage the resource
    #   minimum config items we need to actually care about
    #   without these there is no action possible.
    '''
    print(type(teamidlist))
    if url is None:
        error("Repo URL is empty - expecting a bare url e.g. \"git.test.rc.nectar.org.au\"")
    # and warn for other projvalues
    if token is None:
        warn("No API token specified - likely that the API call will fail")
    if teamidlist =="":
        warn("No teams specified - new repos won't be assigned to any teams. \nThis is probably OK depending on what you are doing.")
    else:
        teamidlist = ''.join(teamidlist.split())     # remove white space
        teamidlist = teamidlist.split(",")  # seperate into individual values at commas
    config = {
        'url': url,
        'sslverify': sslverify,
        'token': token,
        'teamidlist': teamidlist
        }
    return config

@task
def getteamIDs(orgname, url=None, token=None, sslverify=True):
    #   get config from config.ini file
    config = get_gitea_config(url, token, "", sslverify)
    #   use config file values where no values passed in from CLI
    if url is None:
        url = config["url"]
    if token is None:
        token = config["token"]
    if not sslverify:
        sslverify = config["sslverify"]
    #   set up request values
    tokenstring = "token " + token
    url_teamlist = "https://" + url + "/api/v1/orgs/" + orgname + "/teams"
    parameters = {
        "token": token,
        "access_token": token
    }
    teamhead = {
        "accept": "application/json",
        "Authorization": tokenstring
        }
    try:
        response = requests.get(
            url_teamlist,
            verify=sslverify,
            params=parameters,
            headers=teamhead,
            )
        # Consider any status other than 2xx an error
        if not response.status_code // 100 == 2:
            print("Error: Unexpected response {}".format(response))
    except requests.exceptions.RequestException as e:
        # A serious problem happened, like an SSLError or InvalidURL
        print("Error: {}".format(e))
    teamsdict = json.loads(response.text)
    print("Team Name:   Team ID")
    for team in teamsdict:
        print(team['name'] + ": " + str(team['id']))


@task
def makerepo(orgname, reponame, url=None, token=None, sslverify=True):
    #   get config from config.ini file
    config = get_gitea_config(url, token, "", sslverify)
    #   use config file values where no values passed in from CLI
    if url is None:
        url = config["url"]
    if token is None:
        token = config["token"]
    if not sslverify:
        sslverify = config["sslverify"]
    url_repo = "https://" + url + "/api/v1/org/" + orgname + "/repos"
    tokenstring = "token " + token
    repohead = {
        "accept": "application/json",
        "Authorization": tokenstring,
        "Content-Type": "application/json"
        }
    repodata = {
        "auto_init": False,
        "description": "",
        "gitignores": "",
        "license": "",
        "name": reponame,
        "private": True,
        "readme": ""
        }

    try:
        response = requests.post(
            url_repo,
            verify=sslverify,
            headers=repohead,
            json=repodata
            )
        # Consider any status other than 2xx an error
        if not response.status_code // 100 == 2:
            return "Error: Unexpected response {}".format(response)
    except requests.exceptions.RequestException as e:
        # A serious problem happened, like an SSLError or InvalidURL
        return "Error: {}".format(e)


@task
def teamifyrepo(orgname, reponame, ID, url=None, token=None, sslverify=True):
    config = get_gitea_config(url, token, "", sslverify)
    #   use config file values where no values passed in from CLI
    if url is None:
        url = config["url"]
    if token is None:
        token = config["token"]
    if not sslverify:
        sslverify = config["sslverify"]
    url_team = "https://" + url + "/api/v1/teams/" + ID + "/repos/" + orgname + "/" + reponame
    tokenstring = "token " + token
    parameters = {
        "token": token,
        "access_token": token
        }
    teamhead = {
        "accept": "application/json",
        "Authorization": tokenstring
        }
    try:
        response = requests.put(
            url_team,
            params=parameters,
            verify=sslverify,
            headers=teamhead
        )
        # Consider any status other than 2xx an error
        if not response.status_code // 100 == 2:
            return "Error: Unexpected response {}".format(response)
        print("added repo %s/%s to team ID %s" % (orgname, reponame, ID))
        return response
    except requests.exceptions.RequestException as e:
        # A serious problem happened, like an SSLError or InvalidURL
        return "Error: {}".format(e)
