import datetime
import shutil
import subprocess

from fabric.api import task
from fabric.utils import error
from hivemind.decorators import configurable

from hivemind_contrib import keystone


def run(command):
    popen = subprocess.Popen(command, shell=True)
    popen.wait()
    return popen


@configurable('creds')
def get_creds(username=None, password=None):
    msg = " ".join(
        (
            "No ospurge credentials.",
            "Please set username",
            "and password for the ospurge user in",
            "[cfg:hivemind_contrib.ospurge.creds]",
        )
    )
    if username is None or password is None:
        error(msg)
    return username, password


def is_in_project(tenant, user):
    return any([u == user for u in tenant.list_users()])


@task
def purge_project(tenant_name, dry_run=True):
    """Purge resources and disable a given project"""
    if not shutil.which('ospurge'):
        error('ospurge not found in path. Please ensure it is installed.')
    username, password = get_creds()

    if dry_run:
        print("Running in dry-run mode")

    ks_client = keystone.client()
    tenant = keystone.get_tenant(ks_client, tenant_name)
    tenant_member_role = ks_client.roles.find(name='Member')
    ospurge_user = keystone.get_user(ks_client, username)

    if not tenant.enabled:
        print("Enabling project for purge")
        tenant.update(enabled=True)

    if not is_in_project(tenant, ospurge_user):
        print("Adding ospurge user to project")
        tenant.add_user(ospurge_user, tenant_member_role)

    if dry_run:
        run_opt = '--dry-run'
    else:
        run_opt = '--verbose'

    cmd = (
        f"ospurge --dont-delete-project --own-project --username {username} "
        f"--password {password} --admin-project {tenant.name} {run_opt}"
    )
    print("Running: {}".format(cmd.replace(password, 'xxxx')))
    run(cmd)

    if is_in_project(tenant, ospurge_user):
        print("Removing ospurge user from project")
        tenant.remove_user(ospurge_user, tenant_member_role)

    if tenant.enabled:
        if dry_run and tenant.enabled:
            print("Not disabling project due to dry-run")
        else:
            print("Disabling project")
            tenant.update(enabled=False)
            keystone.set_project_metadata(
                tenant_name, 'ospurge_date', str(datetime.datetime.now())
            )
