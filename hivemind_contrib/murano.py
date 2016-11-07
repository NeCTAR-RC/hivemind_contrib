from fabric.api import task

from keystoneclient.v2_0 import client as keystone_client
from muranoclient.v1 import client as murano_client

from hivemind_contrib import keystone


def is_in_project(tenant, user):
    return any([u == user for u in tenant.list_users()])


@task
def private_package(package_id, dry_run=True):
    """ Make a Murano package private """

    if dry_run:
        print("Running in dry-run mode")

    ks_client = keystone.client()
    m = murano_client.Client(endpoint='https://murano.rc.nectar.org.au:8082/',
                             token=ks_client.auth_token)

    package = m.packages.get(package_id)
    # Except HTTPNotFound
    tenant_id = package.owner_id

    tenant = keystone.get_tenant(ks_client, tenant_id)
    tenant_admin_role = ks_client.roles.find(name='Admin')
    admin_user = keystone.get_user(ks_client, ks_client.user_id)

    if not is_in_project(tenant, admin_user):
        print("Adding user to project %s" % tenant)
        tenant.add_user(admin_user, tenant_admin_role)

    if package.is_public:
        if dry_run:
            print("Would toggle public flag for package %s" % package_id)
        else:
            ks_unpriv = keystone_client.Client(username=ks_client.username,
                                               password=ks_client.password,
                                               tenant_name=tenant.name,
                                               insecure=True,
                                               auth_url=ks_client.auth_url)

            print("Toggling public flag for package %s for %s" %
                  (package_id, ks_unpriv.project_id))
            m_unpriv = murano_client.Client(
                endpoint='https://murano.rc.nectar.org.au:8082/',
                token=ks_unpriv.auth_token)
            m_unpriv.packages.toggle_public(package_id)

    if is_in_project(tenant, admin_user):
        print("Removing user from project %s" % tenant_id)
        tenant.remove_user(admin_user, tenant_admin_role)
