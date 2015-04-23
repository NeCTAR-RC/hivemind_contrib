import collections
import os

from fabric.api import task
from prettytable import PrettyTable
from keystoneclient.v2_0 import client as keystone_client
from keystoneclient.v3 import client as keystone_client_v3
from keystoneclient.exceptions import NotFound

from hivemind.decorators import verbose, configurable


@configurable('nectar.openstack.client')
def client(url=None, username=None, password=None, tenant=None, version=2):
    url = os.environ.get('OS_AUTH_URL', url)
    username = os.environ.get('OS_USERNAME', username)
    password = os.environ.get('OS_PASSWORD', password)
    tenant = os.environ.get('OS_TENANT_NAME', tenant)
    assert url and username and password and tenant
    if version == 2:
        return keystone_client.Client(username=username,
                                      password=password,
                                      tenant_name=tenant,
                                      insecure=True,
                                      auth_url=url)
    else:
        return keystone_client_v3.Client(username=username,
                                         password=password,
                                         project_name=tenant,
                                         user_domain_id='default',
                                         auth_url=url.replace('2.0', '3'))


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
    set_project_metadata(tenant, 'vicnode_id', vicnode_id)


@task
@verbose
def set_project_metadata(project, key, value):
    """Set a key value pair on a keystone project
    """
    keystone = client()
    project = get_tenant(keystone, project)
    kwargs = {key: value}
    keystone.tenants.update(project.id, **kwargs)


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
    """
    """
    keystone = client()
    tenant = get_tenant(keystone, tenant)
    print_members(tenant)


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


@task
@verbose
def user_projects(user):
    keystone = client(version=3)
    projects = keystone.projects.list()
    projects = {project.id: project for project in projects}
    roles = keystone.roles.list()
    roles = {role.id: role for role in roles}

    try:
        user = keystone.users.get(user)
    except Exception:
        user = keystone.users.find(name=user)

    if user is None:
        print("Unknown user")
        return

    user_project_roles = collections.defaultdict(list)
    for role in keystone.role_assignments.list(user=user):
        try:
            project_id = role.scope['project']['id']
        except KeyError:
            continue
        role_id = role.role['id']
        user_project_roles[project_id].append(roles[role_id])

    table = PrettyTable(["ID", "Name", "Roles"])
    table.sortby = "Name"
    table.sort_key = lambda x: x[0].lower()
    table.align = 'l'
    for project_id, roles in user_project_roles.items():
        roles = ', '.join(sorted([role.name for role in roles]))
        project = projects[project_id]
        table.add_row([project.id, project.name, roles])
    print "Projects and roles for user %s:" % user.name
    print str(table)
