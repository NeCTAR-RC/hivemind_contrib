import os

from fabric.api import task
from prettytable import PrettyTable
from keystoneclient.v2_0 import client as keystone_client
from keystoneclient.exceptions import NotFound

from hivemind.decorators import verbose, configurable


@configurable('nectar.openstack.client')
def client(url=None, username=None, password=None, tenant=None):
    url = os.environ.get('OS_AUTH_URL', url)
    username = os.environ.get('OS_USERNAME', username)
    password = os.environ.get('OS_PASSWORD', password)
    tenant = os.environ.get('OS_TENANT_NAME', tenant)
    assert url and username and password and tenant
    return keystone_client.Client(username=username,
                                  password=password,
                                  tenant_name=tenant,
                                  insecure=True,
                                  auth_url=url)


def get_tenant(keystone, name_or_id):
    try:
        tenant = keystone.tenants.get(name_or_id)
    except NotFound:
        tenant = keystone.tenants.find(name=name_or_id)
    return tenant


def get_user(keystone, name_or_id):
    try:
        tenant = keystone.users.get(name_or_id)
    except NotFound:
        tenant = keystone.users.find(name=name_or_id)
    return tenant


@task
@verbose
def set_vicnode_id(tenant, vicnode_id):
    """Used in RDSI reporting to determine if the allocation should appear
    in the report.

    """
    keystone = client()
    tenant = get_tenant(keystone, tenant)
    keystone.tenants.update(tenant.id, vicnode_id=vicnode_id)


def print_members(tenant):
    users = PrettyTable(["ID", "Email", "Roles"])
    for user in tenant.list_users():
        roles = ', '.join([r.name for r in user.list_roles(tenant)])
        users.add_row([user.id, user.email, roles])
    print "Members of %s:" % tenant.name
    print str(users)


@task
@verbose
def list_members(tenant):
    """List the members of a project and their roles
    """
    keystone = client()
    tenant = get_tenant(keystone, tenant)
    print_members(tenant)


def print_memberships(user):
    tenants = PrettyTable(["ID", "Tenant", "Roles"])
    keystone = client()
    for tenant in keystone.tenants.list():
        for t_user in tenant.list_users():
            if t_user.id == user.id:
                roles = ', '.join([r.name for r in user.list_roles(tenant)])
                tenants.add_row([tenant.id, tenant.name, roles])
    print "Memberships of %s:" % user.name
    print str(tenants)


@task
@verbose
def list_memberships(tenant):
    """List the project that a user is a member of and their role.

    """
    keystone = client()
    user = get_user(keystone, tenant)
    print_memberships(user)


@task
@verbose
def add_tenant_member(tenant, user):
    """
    """
    keystone = client()
    tenant = get_tenant(keystone, tenant)
    tenant_manager = get_user(keystone, user)
    tenant_manager_role = keystone.roles.find(name='Member')
    tenant.add_user(tenant_manager, tenant_manager_role)
    print_members(tenant)


@task
@verbose
def remove_tenant_member(tenant, user):
    """
    """
    keystone = client()
    tenant = get_tenant(keystone, tenant)
    tenant_manager = get_user(keystone, user)
    for role in tenant_manager.list_roles(tenant):
        tenant.remove_user(tenant_manager, role)
    print_members(tenant)


@task
@verbose
def add_tenant_manager(tenant, user):
    """
    """
    keystone = client()
    tenant = get_tenant(keystone, tenant)
    tenant_manager = get_user(keystone, user)
    tenant_manager_role = keystone.roles.find(name='TenantManager')
    tenant.add_user(tenant_manager, tenant_manager_role)
    print_members(tenant)


@task
@verbose
def remove_tenant_manager(tenant, user):
    """
    """
    keystone = client()
    tenant = get_tenant(keystone, tenant)
    tenant_manager = get_user(keystone, user)
    tenant_manager_role = keystone.roles.find(name='TenantManager')
    tenant.remove_user(tenant_manager, tenant_manager_role)
    print_members(tenant)
