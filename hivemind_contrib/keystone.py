import collections
import os
import random
import re
import string

from fabric.api import task

from keystoneclient import client as keystone_client
from keystoneclient.exceptions import NotFound
from prettytable import PrettyTable

from hivemind import decorators

import six.moves.urllib.parse as urlparse

try:
    from keystoneauth1 import loading
    from keystoneauth1 import session
except ImportError:
    from keystoneclient.auth import identity
    from keystoneclient import session
    loading = None


@decorators.configurable('nectar.openstack.client')
def get_session(username=None, password=None, tenant_name=None, auth_url=None):

    auth_url = os.environ.get('OS_AUTH_URL', auth_url)
    username = os.environ.get('OS_USERNAME', username)
    password = os.environ.get('OS_PASSWORD', password)
    tenant_name = os.environ.get('OS_TENANT_NAME', tenant_name)

    auth_args = {
        'auth_url': auth_url,
        'username': username,
        'password': password,
        'project_name': tenant_name,
        'user_domain_name': 'default',
        'project_domain_name': 'default',
    }

    if loading:
        loader = loading.get_plugin_loader('password')
        auth = loader.load_from_options(**auth_args)
    else:
        path = urlparse.urlparse(auth_url).path.lower()
        # Add /v3 if the URL isn't suffixed with the version
        # or keystoneclient fails with a 404
        if not re.match(r'/v\d(\.\d)?/?$', path):
            auth_args['auth_url'] = auth_url + '/v3'
        auth = identity.v3.Password(**auth_args)

    return session.Session(auth=auth)


def client(version=3):
    sess = get_session()
    return keystone_client.Client(version, session=sess)


def get_projects_module(keystone):
    if keystone.version == 'v3':
        return keystone.projects
    else:
        return keystone.tenants


def get_project(keystone, name_or_id):
    projects = get_projects_module(keystone)
    try:
        project = projects.get(name_or_id)
    except NotFound:
        project = projects.find(name=name_or_id)
    return project


def get_tenant(keystone, name_or_id):
    print("get_tenant is deprecated, use get_project instead")
    return get_project(keystone, name_or_id)


def get_user(keystone, name_or_id):
    try:
        user = keystone.users.get(name_or_id)
    except NotFound:
        user = keystone.users.find(name=name_or_id)
    return user


@task
@decorators.verbose
def set_vicnode_id(project, vicnode_id):
    """Used in RDSI reporting to determine if the allocation should appear
    in the report.
    """
    set_project_metadata(project, 'vicnode_id', vicnode_id)


@task
@decorators.verbose
def add_allocation_home(project, institute_domain):
    """Add a university/institution to the metadata list
    allocation_home for the project.
    """
    update_allocation_home(project, institute_domain)


@task
@decorators.verbose
def set_allocation_home(project, institute_domain):
    """Set the project's allocation_home to institute_domain. Clears existing
    allocation_home list in the process.
    """
    clear_project_metadata(project, 'allocation_home')
    update_allocation_home(project, institute_domain)


@task
@decorators.verbose
def clear_allocation_home(project):
    """Clears the project's allocation_home metadata
    """
    clear_project_metadata(project, 'allocation_home')


def update_allocation_home(project, institute_domain):
    keystone = client()
    proj = get_project(keystone, project)
    proj_dict = proj.to_dict()
    if 'allocation_home' in proj_dict and \
            proj_dict['allocation_home'] is not None:
        homes = proj.allocation_home.split(',')
    else:
        homes = []
    if institute_domain not in homes:
        homes.append(institute_domain)
        set_project_metadata(project,
                             'allocation_home',
                             ",".join(homes))


@task
@decorators.verbose
def set_project_metadata(project, key, value):
    """Set a key value pair on a keystone project
    """
    keystone = client()
    project = get_project(keystone, project)
    kwargs = {key: value}
    projects = get_projects_module(keystone)
    projects.update(project.id, **kwargs)


def clear_project_metadata(project, key):
    """Set a key on a keystone project to None.
    API doesn't appear to be able to delete the key
    """
    set_project_metadata(project.id, key, None)


@task
@decorators.verbose
def set_user_metadata(user, key, value):
    """Set a key value pair on a keystone user
    """
    keystone = client()
    user = get_user(keystone, user)
    kwargs = {key: value}
    keystone.users.update(user.id, **kwargs)


@task
@decorators.verbose
def clear_user_metadata(user, key):
    """Set a key on a keystone user to None.
    API doesn't appear to be able to delete the key
    """
    set_user_metadata(user, key, None)


def print_members(keystone, project):
    table = PrettyTable(["ID", "Username", "Roles"])

    role_assignments = keystone.role_assignments.list(project=project.id,
                                                      include_names=True)
    users = {}
    for ra in role_assignments:

        if ra.user['id'] in users:
            users[ra.user['id']]['roles'].append(ra.role['name'])
        else:
            users[ra.user['id']] = {}
            users[ra.user['id']]['name'] = ra.user['name']
            users[ra.user['id']]['roles'] = [ra.role['name']]
    for user_id, attrs in users.items():
        table.add_row([user_id, attrs['name'], ", ".join(attrs['roles'])])
    print("Members of %s (%s):" % (project.name, project.id))
    print(str(table))


@task
@decorators.verbose
def list_members(project):
    """List members of a tenant"""
    keystone = client()
    project = get_project(keystone, project)
    print_members(keystone, project)


def has_role_in_project(project, user, role):
    keystone = client()
    if keystone.role_assignments.list(project=project, user=user, role=role):
        return True
    return False


def add_project_roles(project, user, roles):
    """Add role or roles to user for project
    """
    keystone = client()
    project = get_project(keystone, project)
    user = get_user(keystone, user)
    for role in roles:
        role = keystone.roles.find(name=role)
        keystone.roles.grant(user=user.id, project=project.id, role=role.id)
    print_members(keystone, project)


def remove_project_roles(project, user, roles):
    """delete role or roles from user for project
    """
    keystone = client()
    project = get_project(keystone, project)
    user = get_user(keystone, user)
    for role in roles:
        role = keystone.roles.find(name=role)
        keystone.roles.revoke(user=user.id, project=project.id, role=role.id)
    print_members(keystone, project)


@task
@decorators.verbose
def add_project_member(project, user):
    """Add Member role to user for project
    """
    add_project_roles(project, user, ['Member'])


@task
@decorators.verbose
def add_tenant_member(project, user):
    print("add_tenant member is deprecated, use add_project_member")
    add_project_member(project, user)


@task
@decorators.verbose
def remove_project_member(project, user):
    """Remove Member role to user for project
    """
    remove_project_roles(project, user, ['Member'])


@task
@decorators.verbose
def remove_tenant_member(project, user):
    print("remove_tenant member is deprecated, use remove_project_member")
    remove_project_member(project, user)


@task
@decorators.verbose
def add_tenant_manager(project, user):
    """Add TenantManager role to user for tenant
    """
    add_project_roles(project, user, ['TenantManager'])


@task
@decorators.verbose
def remove_tenant_manager(project, user):
    """Remove TenantManager role to user for tenant
    """
    remove_project_roles(project, user, ['TenantManager'])


@task
@decorators.verbose
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
    print("Projects and roles for user %s:" % user.name)
    print(str(table))


def generate_random_password(length=24):
    chars = string.letters + string.digits
    return ''.join((random.choice(chars)) for x in range(length))


@task
@decorators.verbose
def add_bot_account(project, user, suffix='bot'):
    """Create a bot account for a given project and user.

    Name of the bot will be created as <project_name>_bot, unless suffix
    is specified.
    """
    keystone = client()
    project = get_project(keystone, project)
    real_user = get_user(keystone, user)
    bot_name = "{name}_{suffix}".format(name=project.name, suffix=suffix)
    password = generate_random_password()
    new_user = keystone.users.create(bot_name, password=password, email=None,
                                     project_id=project.id, enabled=True)

    set_user_metadata(new_user, 'nectar_proxy_owner', real_user.id)

    print("Robot account details:")
    table = PrettyTable(["User ID", "Username", "Password",
                         "Proxy owner", "Proxy owner ID"])
    table.add_row([new_user.id, new_user.name, password,
                   real_user.name, real_user.id])
    print(str(table))
    add_project_roles(project, new_user, ['bot_user'])
    user_projects(new_user)