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
    config = {
        'url': url,
        'token': "token {}".format(token),
        'team_ids': team_ids
        }
    return config


@task
def list_teams(org_name):
    #   get config from config.ini file
    config = get_gitea_config()
    url_teamlist = "{}/orgs/{}/teams".format(config["url"], org_name)
    teamhead = {
        "accept": "application/json",
        "Authorization": config["token"]
        }
    response = requests.get(
        url_teamlist,
        headers=teamhead
        )
    response.raise_for_status()
    teamsdict = json.loads(response.text)
    table = PrettyTable(["Team ID:", "Team name"])
    for team in teamsdict:
        table.add_row([team['id'], team['name']])
    print(table)


@task
def create_repo(org_name, name):
    #   get config from config.ini file
    config = get_gitea_config()
    url_repo = "{}/org/{}/repos".format(config["url"], org_name)
    repohead = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": config["token"]
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

    response = requests.post(
        url_repo,
        headers=repohead,
        json=repodata
        )
    response.raise_for_status()
    print("Repo {}/{} has been created".format(org_name, name))


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
        print("Done adding teams to repo {}".format(name))
    else:
        warn("No teams configured to add to repo {}".format(name))


@task
def add_team_to_repo(org_name, name, team_id):
    #   get config from config.ini file
    config = get_gitea_config()
    # no point trying to process team names, test for number
    try:
        int(team_id)
        url_team = ("{}/teams/{}/repos/{}/{}"
                    "".format(config["url"], team_id, org_name, name))
    except ValueError as e:
        print("Expecting team ID's to be numbers")
        print("Team ID found is : {}".format(team_id))
        print("Edit config file to match the desired teams below")
        list_teams(org_name)
        raise(e)
    teamhead = {
        "accept": "application/json",
        "Authorization": config["token"]
        }

    response = requests.put(
        url_team,
        headers=teamhead
    )
    response.raise_for_status()
    print("Added repo {}/{} to team ID {}".format(org_name, name, team_id))
