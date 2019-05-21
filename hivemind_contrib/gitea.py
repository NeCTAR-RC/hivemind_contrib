from fabric.api import task
from fabric.utils import error
from fabric.utils import warn
from hivemind.decorators import configurable
from hivemind.decorators import verbose
import json
import requests


@configurable('gitea')
@verbose
def get_gitea_config(url=None, token=None, team_ids=""):
    if url is None:
        error("Repo URL is empty - expecting a bare url"
              + " e.g. \"git.rc.nectar.org.au\"")
    # and warn for other values
    if token is None:
        warn("No API token specified - may be that the API call will fail")
    if team_ids == "":
        warn("No teams specified - new repos won't be assigned to any teams.")
    else:
        team_ids = ''.join(team_ids.split())
        team_ids = team_ids.split(",")
    config = {
        'url': url,
        'token': token,
        'team_ids': team_ids
        }
    return config


@task
def print_teamids(org_name, url=None, token=None):
    #   get config from config.ini file
    config = get_gitea_config()
    url = config["url"]
    token = config["token"]
    #   set up request values
    tokenstring = "token " + token
    url_teamlist = "https://" + url + "/api/v1/orgs/" + org_name + "/teams"
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
    print("Team Name:   \tTeam ID")
    for team in teamsdict:
        print(team['name'] + ": \t" + str(team['id']))


@task
def create_repo(org_name, name):
    #   get config from config.ini file
    config = get_gitea_config()
    url = config["url"]
    token = config["token"]
    url_repo = "https://" + url + "/api/v1/org/" + org_name + "/repos"
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
        "name": name,
        "private": True,
        "readme": ""
        }
    print('working on https://%s/%s/%s' % (url, org_name, name))
    try:
        response = requests.post(
            url_repo,
            headers=repohead,
            json=repodata
            )
        # Consider any status other than 2xx an error
        if not response.status_code // 100 == 2:
            return "Error: Unexpected response {}".format(response)
    except requests.exceptions.RequestException as e:
        # A serious problem happened, like an SSLError or InvalidURL
        return "Error: {}".format(e)
    print("success!")
    team_ids = config["team_ids"]
    if team_ids != "":
        for team_id in team_ids:
            teamify_repo(org_name, name, team_id, url, token)
    print("Done!")


@task
def teamify_repo(org_name, name, team_id, url=None, token=None):
    #   get config from config.ini file
    config = get_gitea_config()
    url = config["url"]
    token = config["token"]
    url_team = ("https://" + url + "/api/v1/teams/" + team_id
                + "/repos/" + org_name + "/" + name)
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
            headers=teamhead
        )
        # Consider any status other than 2xx an error
        if not response.status_code // 100 == 2:
            return "Error: Unexpected response {}".format(response)
        print("added repo %s/%s to team ID %s" % (org_name, name, team_id))
    except requests.exceptions.RequestException as e:
        # A serious problem happened, like an SSLError or InvalidURL
        return "Error: {}".format(e)
