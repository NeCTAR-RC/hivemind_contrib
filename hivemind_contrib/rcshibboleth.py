from __future__ import print_function

from fabric.api import task


def deprecated_use_manuka():
    print("""This command has been removed, please use manukaclient
https://pypi.org/project/manukaclient/""")


@task
def search(display_name=None, email=None):
    deprecated_use_manuka()


@task
def find_duplicate(field=['email', 'displayname', 'user_id'], details=False):
    deprecated_use_manuka()


@task
def link_account(existing_email, new_email):
    deprecated_use_manuka()


@task
def link_duplicate(email, dry_run=True):
    deprecated_use_manuka()
