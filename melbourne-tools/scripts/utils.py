#!/usr/bin/env python
#
# Date:   05/11/2018
# Description: Utility function for using Openstack API
#
from __future__ import print_function

from keystoneauth1 import identity as keystone_identity
from keystoneauth1 import session as keystone_session
import os
import re

CONFIGDIR = '~/.config/melbourne-tools/'


class c(object):
    """Static colour definition class."""

    SUCCESS = 'green'
    FAILURE = 'red'
    INFO = 'cyan'
    DEFAULT = 'white'


def get_session(url=None, username=None, password=None,
                tenant=None, version=3):
    """Get the keystone session for Openstack clients."""
    url = os.environ.get('OS_AUTH_URL', url)
    username = os.environ.get('OS_USERNAME', username)
    user_domain_name = 'Default'
    password = os.environ.get('OS_PASSWORD', password)
    tenant = os.environ.get('OS_TENANT_NAME', tenant) or \
        os.environ.get('OS_PROJECT_NAME', tenant)
    project_domain_name = 'Default'
    assert url and username and password and tenant
    auth = keystone_identity.Password(username=username,
                                      password=password,
                                      tenant_name=tenant,
                                      auth_url=url,
                                      user_domain_name=user_domain_name,
                                      project_domain_name=project_domain_name)
    return keystone_session.Session(auth=auth)


def try_assign(method, *args, **options):
    """Try to evaluate a function and return the result.

    Otherwise, raise error message and exit.
    """
    terminate = True if ('exit' in options and options['exit'] is True) \
        else False
    options.pop('exit', None)
    try:
        return method(*args, **options)
    except Exception as error_msg:
        if terminate:
            exit(error_msg)
        else:
            print(error_msg)
            return None


# Parse the nodelist using SLURM syntax
def _parse_dash(range_str):
    """Unpack the dash syntax into a set of number."""
    hosts = range_str.split("-")
    return range(int(hosts[0]),
                 int(hosts[1]) + 1) if len(hosts) > 1 else [range_str]


def parse_nodes(nodes):
    """Parse list syntax (eg. qh2-rcc[01-10,13])."""
    # Parse qh2-rcc5,qh2-rcc6,qh2-rcc7 syntax
    nodes = re.split(r",\s*(?![^\[\]]*\])", nodes)

    if len(nodes) > 1:
        nodes = set(host for hosts in nodes for host in parse_nodes(hosts))
    else:
        # Parse qh2-rcc[112-114,115] syntax
        match = re.search(r"(.*?)\[(.*?)\](.*)", nodes[0])
        if match:
            host_ranges = [host
                           for hosts in parse_nodes(match.group(2))
                           for host in _parse_dash(hosts)]
            nodes = set("%s%s%s" % (match.group(1), host, match.group(3))
                        for host in host_ranges)
    return nodes
