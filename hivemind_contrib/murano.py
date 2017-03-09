from fabric.api import task
from fabric.utils import error

from hivemind.decorators import configurable
from hivemind_contrib import keystone

import muranoclient.client as murano


@configurable('nectar.openstack.client')
def client(version='1', project_name=None):
    sess = keystone.get_session(tenant_name=project_name)
    return murano.Client(version, session=sess,
                         service_type='application-catalog')


def _package_set(package_id, state, dry_run):
    """Set package state"""

    if state == 'public':
        set_public = True
    elif state == 'private':
        set_public = False
    else:
        error('Invalid state: {0}'.format(state))

    mc = client()
    package = mc.packages.get(package_id)
    project_id = package.owner_id

    ks_client = keystone.client()
    project = ks_client.projects.get(project_id)
    project_admin_role = ks_client.roles.find(name='Admin')
    admin_user = ks_client.users.get(ks_client.session.get_user_id())

    if not keystone.has_role_in_project(project, admin_user,
                                        project_admin_role):
        print("Adding admin user to project %s (%s)" % (project.name,
                                                        project.id))
        ks_client.roles.grant(user=admin_user, project=project,
                              role=project_admin_role)

    if package.is_public != set_public:
        mc = client(project_name=project.name)

        if dry_run:
            print("Would set %s flag for package %s (%s)" %
                (state, package.name, package_id))
        else:
            print("Setting %s flag for package %s for %s" %
                (state, package_id, project_id))
            mc.packages.toggle_public(package_id)
    else:
        print("Package is already %s" % state)

    if keystone.has_role_in_project(project, admin_user,
                                    project_admin_role):
        print("Removing admin user from project %s (%s)" % (project.name,
                                                      project.id))
        ks_client.roles.revoke(user=admin_user, project=project,
                               role=project_admin_role)


@task
def set_private(package_id, dry_run=True):
    """Set a package to private"""
    _package_set(package_id, 'private', dry_run)


@task
def set_public(package_id, dry_run=True):
    """Set a package to public"""
    _package_set(package_id, 'public', dry_run)
