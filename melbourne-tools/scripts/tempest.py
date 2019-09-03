#!/usr/bin/env python
#
# PREREQUISITE:
# pip install tenacity
# export JENKINS_USERNAME=<jenkins username>
# export JENKINS_TOKEN=<jenkins token>


import argparse
import click
import json
import os
import pprint
import re
import requests
import sys
import tenacity
from textwrap import dedent
from utils import c


class RetryTimeout(Exception):
    """Define a custom timeout exception."""

    pass


def _get_auth(debug):
    """Return basic HTTP token needed to for requests."""
    username = os.environ.get('JENKINS_USERNAME')
    token = os.environ.get('JENKINS_TOKEN')

    if username is None or token is None:
        err_msg = """   JENKINS_USERNAME/TOKEN not found.
        Have you set your environment?
        export JENKINS_USERNAME=<jenkins username>
        export JENKINS_TOKEN=<jenkins API token>"""
        raise EnvironmentError(dedent(err_msg))

    if debug:
        sys.stdout.write("Login as: %s:%s\n" % (username, token))
        sys.stdout.flush()
    return (username, token)


def host_check_build(debug, az, auth, jurl, host=None, cloud=None):
    """Build jenkins compute host with the describe parameters."""
    # Request.utils.quote escape the string for URL encoding
    params = ["AVAILABILITY_ZONE=%s" % requests.utils.quote(az)]
    if host is not None:
        params.append("HOST=%s" % requests.utils.quote(host))
    if cloud is not None:
        params.append("CLOUD=%s" % requests.utils.quote(cloud))

    url = "%s/buildWithParameters?%s" % (jurl, "&".join(params))

    if debug:
        sys.stdout.write("POST to: %s\n" % url)
        sys.stdout.flush()

    # Submit the job and get the responding Jenkins queue URL from the headers
    return requests.post(url, auth=auth)


def get_queue_json(debug, auth, build_response):
    """Return the queue JSON."""
    queue_url = "%sapi/json" % build_response.headers["Location"]
    queue_response = requests.get(queue_url, auth=auth)
    if debug:
        sys.stdout.write("Queue response:=======================\n")
        pp.pprint(queue_response)
        sys.stdout.write("======================================\n")
        sys.stdout.flush()
    return queue_response.json()


def host_check_submitted(debug, auth, build_response):
    """Print out the confirmation of the submitted Jenkins."""
    response = get_queue_json(debug, auth, build_response)
    queue_url = "%sapi/json" % build_response.headers["Location"]

    # Get and format the submitted parameters
    params = response[u"params"][response[u"params"].find("AVAILABILITY"):]
    params = " ".join(param.split("=")[1] for param in params.split("\n"))
    result = "%s submitted: %s\n" % (params, queue_url)

    sys.stdout.write(result)


@tenacity.retry(wait=tenacity.wait_exponential(multiplier=1, max=15),
                stop=tenacity.stop_after_delay(600),
                retry=tenacity.retry_if_exception_type(RetryTimeout))
def host_check_wait(debug, auth, build_response):
    """Wait and return the job URL.

    Stop after 10 minutes. Retry exponential from 1 second up to 15 seconds
    then 15 seconds afterward.
    """
    response = get_queue_json(debug, auth, build_response)

    if u"Queue$LeftItem" not in response[u"_class"]:
        err_msg = """    Waiting timeout after 600 seconds.
        Jenkins is very busy, please check API later.
        """
        raise RetryTimeout(dedent(err_msg))

    if debug:
        sys.stdout.write("Success response:=======================\n")
        pp.pprint(response)
        sys.stdout.write("========================================\n")
        sys.stdout.flush()

    job_url = response[u"executable"][u"url"]

    # Get and format the submitted parameters
    params = response[u"params"][response[u"params"].find("AVAILABILITY"):]
    params = " ".join(param.split("=")[1] for param in params.split("\n"))

    # Result
    result = "%s started: %s\n" % (params, job_url)
    sys.stdout.write(result)
    sys.stdout.flush()

    return job_url


@tenacity.retry(wait=tenacity.wait_fixed(15),
                stop=tenacity.stop_after_delay(600),
                retry=tenacity.retry_if_exception_type(RetryTimeout))
def host_check_show_result(debug, auth, job_url):
    """Check and show the result of the build.

    Stop after 15 minutes. Wait 15 seconds between retries.
     """
    response = requests.get("%s/api/json" % job_url, auth=auth).json()

    if debug:
        sys.stdout.write("Success response:=======================\n")
        pp.pprint(response)
        sys.stdout.write("========================================\n")
        sys.stdout.flush()

    if response[u"result"] is None:
        err_msg = """    Timeout after 900 seconds.
        Please manually check tempest job to see result.
        """
        raise RetryTimeout(dedent(err_msg))

    result = None
    # Fetch the relevant consoleText section
    failureText = re.compile(r'=+\nFailed.+', flags=re.DOTALL)
    successText = re.compile(r'=+\nTotal.+', flags=re.DOTALL)
    SOCK_PATTERN = r'^.*unclosed <socket.socket.*\n.*self._sock = None.*\n'
    unclosedSocketPattern = re.compile(SOCK_PATTERN,
                                       flags=re.MULTILINE)

    consoleText = requests.get("%sconsoleText" % job_url, auth=auth)

    if debug:
        sys.stdout.write("Fetching consoleText:=======================\n")
        pp.pprint(consoleText.text)
        sys.stdout.write("============================================\n")
        sys.stdout.flush()

    if response[u"result"] in u"FAILURE":
        result = re.search(failureText, consoleText.text).group(0)
        # Filter out Work Balance section
        result = result.split("==============\nWorker Balance")[0]
        # Filter out all Python 3.5 unclosed socket error
        result = re.sub(unclosedSocketPattern, '', result)
    if response[u"result"] in u"SUCCESS":
        result = re.search(successText, consoleText.text).group(0)
        # Filter out Work Balance section
        result = result.split("==============\nWorker Balance")[0]

    # Get and format the submitted parameters
    params = response[u"actions"][0][u"parameters"]
    params = "%s %s" % (params[1][u"value"], params[2][u"value"])

    # Result
    final_result = "%s tempest result: %s\n %s" % (params, job_url, result)
    sys.stdout.write(final_result)
    sys.stdout.flush()


def host_check(debug, jurl, cloud, az, hosts, wait):
    """Run the Jenkins job with the above parameters."""
    if debug:
        global pp
        pp = pprint.PrettyPrinter(indent=2)
    auth = _get_auth(debug)

    responses = []
    if hosts:
        responses = [host_check_build(debug,
                                      az,
                                      auth,
                                      jurl,
                                      host=host,
                                      cloud=cloud)
                     for host in hosts]
    else:
        responses = [host_check_build(debug,
                                      az,
                                      auth,
                                      jurl,
                                      cloud=cloud)]

    jobs = []
    for resp in responses:
        if wait:
            try:
                jobs.append(host_check_wait(debug, auth, resp))
            except RetryTimeout as ex:
                sys.stdout.write("Queue error: %s\n" % ex)
                sys.stdout.flush()
                host_check_submitted(debug, auth, resp)
        else:
            host_check_submitted(debug, auth, resp)

    if wait:
        sys.stdout.write("%s BUILD RESULT BELOW %s\n" % ('='*24, '='*24))
        sys.stdout.flush()
        for job in jobs:
            try:
                host_check_show_result(debug, auth, job)
            except RetryTimeout as ex:
                sys.stdout.write("Queue error: %s\n" % ex)
                sys.stdout.flush()


@click.group()
def cli():
    """Run Jenkins job in terminal."""
    pass


@cli.group()
def compute():
    """Compute host check."""
    pass


@cli.group()
def scenario():
    """Scenario host check."""
    pass


@compute.command(name='check')
@click.argument('availability_zone')
@click.option('-h', '--host', multiple=True,
              help="""Nova hosts to test. You can add multiple hosts.
              Eg: -s qh2-rcc10 -s qh2-rcc11
              Host must be in AVAILABILITY_ZONE;
              nova will return a 'No Valid Host' error otherwise.
              Leave blank to let scheduler choose a host.""")
@click.option('-c', '--cloud',
              help="""Cloud to run tempest on: production, testing, development.
              Default to production.""")
@click.option('--nowait', is_flag=True, default=False,
              help="""Return the queue url immediately.""")
@click.option('--debug', is_flag=True,
              help="""Debug mode.""")
def compute_check(availability_zone, host, cloud, nowait, debug):
    """Run a tempest compute host check with the given availability_zone."""
    jurl = 'https://jenkins.rc.nectar.org.au/job/tempest-compute-host-check'
    wait = not nowait
    host_check(debug, jurl, cloud, availability_zone, host, wait)


@scenario.command(name='check')
@click.argument('availability_zone')
@click.option('-h', '--host', multiple=True,
              help="""Nova hosts to test. You can add multiple hosts.
              Eg: -s qh2-rcc10 -s qh2-rcc11
              Host must be in AVAILABILITY_ZONE;
              nova will return a 'No Valid Host' error otherwise.
              Leave blank to let scheduler choose a host.""")
@click.option('-c', '--cloud',
              help="""Cloud to run tempest on: production, testing, development.
              Default to production.""")
@click.option('--nowait', is_flag=True, default=False,
              help="""Return the queue url immediately.""")
@click.option('--debug', default=False,
              help="""Debug mode.""")
def scenario_check(availability_zone, host, cloud, nowait, debug):
    """Run a tempest scenario check with the given availability_zone."""
    jurl = 'https://jenkins.rc.nectar.org.au/job/tempest-scenario-check'
    wait = not nowait
    host_check(debug, jurl, cloud, availability_zone, host, wait)
