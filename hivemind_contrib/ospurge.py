import os
import subprocess
import sys

from distutils import spawn
from fabric.api import task
from fabric.utils import error
from hivemind.decorators import verbose, configurable
from hivemind_contrib import keystone
from keystoneclient import exceptions as api_exceptions


def run(command):
    popen = subprocess.Popen(command, shell=True)
    streamdata = popen.wait()
    return popen


@configurable('creds')
def get_creds(username=None, password=None):
    msg = " ".join(("No ospurge credentials.", "Please set username",
                    "and password for the ospurge user in",
                    "[cfg:hivemind_contrib.ospurge.creds]"))
    if username is None or password is None:
        error(msg)
    return username, password


def is_in_project(tenant, user):
    return any([u == user for u in tenant.list_users()])


@task
def purge_project(tenant_name, dry_run=True):
    """ Purge all resources (inc. user-roles) from a given project. """
    if not spawn.find_executable('ospurge'):
        error('ospurge not found in path. Please ensure it is installed.')
    username, password = get_creds()

    ks_client = keystone.client()
    tenant = keystone.get_tenant(ks_client, tenant_name)
    tenant_member_role = ks_client.roles.find(name='Member')
    ospurge_user = keystone.get_user(ks_client, username)

    if not is_in_project(tenant, ospurge_user):
        print("Adding ospurge to project")
        tenant.add_user(ospurge_user, tenant_member_role)

    if dry_run:
        run_opt = '--dry-run'
    else:
        run_opt = '--verbose'

    cmd = ("ospurge --dont-delete-project --own-project --username {username} "
               "--password {password} --admin-project {tenant} {run_opt}"
               "".format(username=username, password=password,
               tenant=tenant_name, run_opt=run_opt))
    print("Running: {}".format(cmd.replace(password, 'xxxx')))
    run(cmd)

    if is_in_project(tenant, ospurge_user):
        print("Removing ospurge user from project")
        tenant.remove_user(ospurge_user, tenant_member_role)
