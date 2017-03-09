from fabric.api import task

from hivemind.decorators import configurable
from hivemind_contrib import keystone

import muranoclient.client as murano


@configurable('nectar.openstack.client')
def get_murano_client(version='1', project_name=None):
    sess = keystone.get_session(tenant_name=project_name)
    return murano.Client(version, session=sess,
                         service_type='application-catalog')


def is_in_project(kc, project, user, role):
    if kc.role_assignments.list(project=project, user=user, role=role):
        return True
    return False


def _package_set(package_id, set_public, dry_run):
    """Set package state"""

    if set_public:
        state = 'public'
    else:
        state = 'private'

    mc = get_murano_client()
    package = mc.packages.get(package_id)
    project_id = package.owner_id

    ks_client = keystone.client()
    project = ks_client.projects.get(project_id)
    project_admin_role = ks_client.roles.find(name='Admin')
    admin_user = ks_client.users.get(ks_client.session.get_user_id())

    if not is_in_project(ks_client, project, admin_user, project_admin_role):
        print("Adding admin user to project %s (%s)" % (project.name,
                                                        project.id))
        ks_client.roles.grant(user=admin_user, project=project,
                              role=project_admin_role)


    if package.is_public != set_public:
        mc = get_murano_client(project_name=project.name)

        if dry_run:
            print("Would set %s flag for package %s (%s)" %
                (state, package.name, package_id))
        else:
            print("Setting %s flag for package %s for %s" %
                (state, package_id, project_id))
            mc.packages.toggle_public(package_id)
    else:
        print("Package is already %s" % state)

    if is_in_project(ks_client, project, admin_user, project_admin_role):
        print("Removing admin user from project %s (%s)" % (project.name,
                                                      project.id))
        ks_client.roles.revoke(user=admin_user, project=project,
                               role=project_admin_role)


@task
def private(package_id, dry_run=True):
    """Set a package to private"""
    _package_set(package_id, False, dry_run)

@task
def public(package_id, dry_run=True):
    """Set a package to public"""
    _package_set(package_id, True, dry_run)
