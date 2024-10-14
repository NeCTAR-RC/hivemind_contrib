from fabric.api import task
from hivemind import decorators
from hivemind_contrib import keystone

ROLE = 'reporting-api-auth'


@task
@decorators.verbose
def grant_access(user):
    """Grant the user access to reports.rc.nectar.org.au."""
    ksclient = keystone.client()
    user = keystone.get_user(ksclient, user)
    keystone.add_project_roles(user.default_project_id, user.id, [ROLE])
    keystone.print_members(ksclient, user.default_project_id)


@task
@decorators.verbose
def revoke_access(user):
    """Revoke access to reports.rc.nectar.org.au for the user."""
    ksclient = keystone.client()
    user = keystone.get_user(ksclient, user)
    keystone.remove_project_roles(user.default_project_id, user.id, [ROLE])
    keystone.print_members(ksclient, user.default_project_id)
