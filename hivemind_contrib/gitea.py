from fabric.api import task
from fabric.utils import error
from fabric.utils import warn
import json
from prettytable import PrettyTable
import requests

from hivemind.decorators import configurable
from hivemind.decorators import verbose


@configurable('gitea')
@verbose
def get_gitea_config(url=None, token=None, team_ids=""):
    if url is None or url == '':
        error("Repo URL is empty - expecting a bare url"
              + " e.g. \"git.rc.nectar.org.au\"")
    # and warn for other values
    if token is None or token == "":
        warn("No API token specified - may be that the API call will fail")
    if team_ids == "":
        warn("No teams specified in config.ini "
             + "- new repos won't be assigned to any teams.")
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
def list_teams(org_name):
    #   get config from config.ini file
    config = get_gitea_config()
    url = config["url"]
    token = config["token"]
    #   set up request values
    url_teamlist = "https://" + url + "/api/v1/orgs/" + org_name + "/teams"
    parameters = {"token": token}
    teamhead = {"accept": "application/json"}

    try:
        response = requests.get(
            url_teamlist,
            params=parameters,
            headers=teamhead
            )
        if response.codes.ok:
            teamsdict = json.loads(response.text)
            table = PrettyTable(["Team Name:", "Team ID"])
            for team in teamsdict:
                table.add_row([team['name'], team['id']])
            print(table)
        else:
            response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(e)
    return()


def create_repo(org_name, repo_name):
    #   get config from config.ini file
    config = get_gitea_config()
    url = config["url"]
    token = config["token"]
    url_repo = "https://" + url + "/api/v1/org/" + org_name + "/repos"
    parameters = {"token": token}
    repohead = {
        "accept": "application/json",
        "Content-Type": "application/json"
        }
    repodata = {
        "auto_init": False,
        "description": "",
        "gitignores": "",
        "license": "",
        "name": repo_name,
        "private": True,
        "readme": ""
        }
    print('working on https://%s/%s/%s' % (url, org_name, repo_name))
    # try:
    response = requests.post(
        url_repo,
        params=parameters,
        headers=repohead,
        json=repodata
        )
    if response.codes.ok:
        team_ids = config["team_ids"]
        if team_ids != "":
            for team_id in team_ids:
                add_team_to_repo(org_name, repo_name, team_id, url, token)
            print("Done adding teams to the repo %s/%s/%s" %
                  (url, org_name, repo_name))
        return(response)
    else:
        response.raise_for_status()


def add_team_to_repo(org_name, repo_name, team_id):
    #   get config from config.ini file
    config = get_gitea_config()
    url = config["url"]
    token = config["token"]
    url_team = ("https://" + url + "/api/v1/teams/" + team_id
                + "/repos/" + org_name + "/" + repo_name)
    parameters = {"token": token}
    teamhead = {"accept": "application/json"}
    response = requests.put(
        url_team,
        params=parameters,
        headers=teamhead
    )
    if response.codes.ok:
        print("added repo %s/%s to team ID %s" %
              (org_name, repo_name, team_id))
    else:
        print("could not add repo %s/%s to team ID %s" %
              (org_name, repo_name, team_id))
        response.raise_for_status()
