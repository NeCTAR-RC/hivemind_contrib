from fabric.api import task
from fabric.utils import warn
import json
from prettytable import PrettyTable
import requests

from hivemind.decorators import configurable
from hivemind.decorators import verbose


@configurable('gitea')
@verbose
def get_gitea_config(url, token, team_ids=None):
    head_auth_token = "token {}".format(token)
    config = {
        'url': url,
        'token': head_auth_token,
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
    url_teamlist = "https://{}/api/v1/org/{}/teams".format(url, org_name)
    teamhead = {
        "accept": "application/json",
        "Authorization": token
        }
    response = requests.get(
        url_teamlist,
        headers=teamhead
        )
    response.raise_for_status()
    teamsdict = json.loads(response.text)
    table = PrettyTable(["Team Name:", "Team ID"])
    for team in teamsdict:
        table.add_row([team['name'], team['id']])
    print(table)


@task
def create_repo(org_name, name):
    #   get config from config.ini file
    config = get_gitea_config()
    url = config["url"]
    token = config["token"]
    url_repo = "https://{}/api/v1/org/{}/repos".format(url, org_name)
    repohead = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": token
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

    print("working on https://{}/{}/{}".format(url, org_name, name))
    response = requests.post(
        url_repo,
        headers=repohead,
        json=repodata
        )
    response.raise_for_status()


@task
def add_teams_to_repo(org_name, name):
    config = get_gitea_config()
    team_ids = config["team_ids"]
    if team_ids:
        team_ids = ''.join(team_ids.split())
        team_ids = team_ids.split(",")
        # loop through teams.
        for team_id in team_ids:
            add_team_to_repo(org_name, name, team_id)
        print("done adding teams to repo {}".format(name))
    else:
        warn("no teams configured to add to repo {}".format(name))


@task
def add_team_to_repo(org_name, name, team_id):
    #   get config from config.ini file
    config = get_gitea_config()
    url = config["url"]
    token = config["token"]
    # no point trying to process team names, test for number
    try:
        int(team_id)
        url_team = ("https://{}/api/v1/teams/{}/repos/{}/{}"
                    "".format(url, team_id, org_name, name))
    except ValueError as e:
        print("Expecting team ID's to be numbers")
        print("team ID found is : {}".format(team_id))
        print("edit config file to match the desired teams below")
        list_teams(org_name)
        raise(e)
    teamhead = {
        "accept": "application/json",
        "Authorization": token
        }

    response = requests.put(
        url_team,
        headers=teamhead
    )
    if response.status_code // 100 == 2:
        print("added repo {}/{} to team ID {}".format(org_name, name, team_id))
    else:
        print("could not add repo {}/{} to team ID {}"
              "".format(org_name, name, team_id))
        response.raise_for_status()
