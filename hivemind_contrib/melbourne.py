from fabric.api import task
from hivemind import decorators
from hivemind_contrib import keystone


@task
@decorators.verbose
def add_sut_role(project, user):
    """Add sut role to user for project
    """
    keystone.add_project_roles(project, user, ['PreProdUser', 'SUT-Access'])


@task
@decorators.verbose
def add_uom_role(project, user):
    """Add uom role to user for project
    """
    keystone.add_project_roles(project, user, ['PreProdUser', 'UoM-Access'])
