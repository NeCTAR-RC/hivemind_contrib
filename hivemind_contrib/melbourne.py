from fabric.api import task
from hivemind import decorators
from hivemind_contrib import keystone


@task
@decorators.verbose
def add_sut_role_to_user(project, user):
    """Add sut role to user for project"""
    keystone.add_project_roles(project, user, ['PreProdUser', 'SUT-Access'])


@task
@decorators.verbose
def remove_sut_role_from_user(project, user):
    """Remove sut role from user for project"""
    keystone.remove_project_roles(project, user, ['PreProdUser', 'SUT-Access'])


@task
@decorators.verbose
def add_uom_role_to_user(project, user):
    """Add uom role to user for project"""
    keystone.add_project_roles(project, user, ['PreProdUser', 'UoM-Access'])


@task
@decorators.verbose
def remove_uom_role_from_user(project, user):
    """Remove uom role from user for project"""
    keystone.remove_project_roles(project, user, ['PreProdUser', 'UoM-Access'])


@task
@decorators.verbose
def add_project_members_to_sut_role(project):
    """Add sut role to all users in project"""
    keystone.add_project_all_users_roles(
        project, ['PreProdUser', 'SUT-Access']
    )


@task
@decorators.verbose
def remove_project_members_from_sut_role(project):
    """Remove sut role from all users in project"""
    keystone.remove_project_all_users_roles(
        project, ['PreProdUser', 'SUT-Access']
    )


@task
@decorators.verbose
def add_project_members_to_uom_role(project):
    """Add uom role to all users in project"""
    keystone.add_project_all_users_roles(
        project, ['PreProdUser', 'UoM-Access']
    )


@task
@decorators.verbose
def remove_project_members_from_uom_role(project):
    """Remove uom role from all users in project"""
    keystone.remove_project_all_users_roles(
        project, ['PreProdUser', 'UoM-Access']
    )
