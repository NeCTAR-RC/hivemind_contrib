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
    if token is None or token == "":
        error("No API token specified - API calls will fail - aborting")
    # and warn for other values
    if team_ids == "":
        warn("No teams specified in config.ini "
             + "New repos won't be assigned to any teams.")
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
    token_string = "token " + token
    teamhead = {
        "accept": "application/json",
        "Authorization": token_string
        }

    try:
        response = requests.get(
            url_teamlist,
            headers=teamhead
            )
        if response.status_code == requests.codes.ok:
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

@task
def create_repo(org_name, repo_name):
    #   get config from config.ini file
    config = get_gitea_config()
    url = config["url"]
    token = config["token"]
    token_string = "token " + token
    url_repo = "https://" + url + "/api/v1/org/" + org_name + "/repos"
    repohead = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": token_string
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
    response = requests.post(
        url_repo,
        headers=repohead,
        json=repodata
        )
    if response.status_code // 100 == 2:
        return(response)
    else:
        print("http error %s" % response.status_code)
        response.raise_for_status()


@task
def add_teams_to_repo(org_name, repo_name):
    config = get_gitea_config()
    team_ids = config["team_ids"]
    # loop through teams.
    if team_ids != "":
        for team_id in team_ids:
            try:
                add_team_to_repo(org_name, repo_name, team_id)
            except ValueError as e:
                print(e)
                print("skipping this misconfigured ID")
                pass  # try the next one
            except requests.exceptions.HTTPError as e:
                print(e)
                print("that team ID doesn't seem to exist")
                pass  # try the next one
        print("done adding teams to repo %s" % repo_name)
    else:
        print("no teams configured to add to repo %s" % repo_name)


@task
def add_team_to_repo(org_name, repo_name, team_id):
    #   get config from config.ini file
    config = get_gitea_config()
    url = config["url"]
    token = config["token"]
    token_string = "token " + token
    # no point trying to process team names, test for number
    try:
        int(team_id)
        url_team = ("https://" + url + "/api/v1/teams/" + team_id
                    + "/repos/" + org_name + "/" + repo_name)
    except ValueError:
        print("Expecting team ID's to be numbers")
        print("team ID found is : %s" % team_id)
        print("edit config file to match the desired teams below")
        list_teams(org_name)
        error(ValueError)
    teamhead = {
        "accept": "application/json",
        "Authorization": token_string
        }

    response = requests.put(
        url_team,
        headers=teamhead
    )
    if response.status_code // 100 == 2:
        print("added repo %s/%s to team ID %s" %
              (org_name, repo_name, team_id))
    else:
        print("could not add repo %s/%s to team ID %s" %
              (org_name, repo_name, team_id))
        response.raise_for_status()
