from fabric.api import task

import os_client_config

from hivemind_contrib import keystone


def murano_client(url=None, username=None, password=None, tenant=None):
    return os_client_config.make_client('application-catalog', auth_url=url,
                                        username=username, password=password,
                                        project_name=tenant)


def is_in_project(tenant, user):
    return any([u == user for u in tenant.list_users()])


@task
def private_package(package_id, dry_run=True):
    """ Make a Murano package private """

    if dry_run:
        print("Running in dry-run mode")

    m = os_client_config.make_client('application-catalog')

    package = m.packages.get(package_id)
    tenant_id = package.owner_id

    ks_client = keystone.client('3')
    tenant = keystone.get_tenant(ks_client, tenant_id)
    tenant_admin_role = ks_client.roles.find(name='Admin')
    admin_user = keystone.get_user(ks_client, ks_client.user_id)

    if not is_in_project(tenant, admin_user):
        print("Adding user to project %s (%s)" % (tenant.name, tenant.id))
        tenant.add_user(admin_user, tenant_admin_role)

    if package.is_public:
        if dry_run:
            print("Would remove public flag for package %s" % package_id)
        else:
            print("Removing public flag for package %s for %s" %
                  (package_id, tenant_id))
            m = os_client_config.make_client('application-catalog',
                                             tenant_name=tenant.name)
            m.packages.toggle_public(package_id)
    else:
        print("Package is not public")

    if is_in_project(tenant, admin_user):
        print("Removing user from project %s (%s)" % (tenant.name, tenant.id))
        tenant.remove_user(admin_user, tenant_admin_role)
