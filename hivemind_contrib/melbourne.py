#
# Filename: melbourne.py
# Author: Ade
# Description: handy melbourne node tools
#
# Change Log:
#
"""melbourne node tools
"""

from hivemind_contrib import keystone
from fabric.api import task

from hivemind import decorators

@task
@decorators.verbose
def add_sut_member(project, user):
    """Add sut role to user for project
    """
    add_project_role(project, user, ['PreProdUser', 'SUT-Access'])

@task
@decorators.verbose
def add_uom_member(project, user):
    """Add uom role to user for project
    """
    add_project_role(project, user, ['PreProdUser', 'UoM-Access'])
