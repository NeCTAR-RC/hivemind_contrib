"""

Run Verbose:

   slab-test upgrade:verbose=True

Filter out packages:

   slab-test upgrade:verbose=True,exclude="apt;libpolkit-gobject-1-0"


"""
from itertools import chain
from fabric.api import (env, parallel, runs_once, execute,
                        prompt, settings, show, puts, task)
from hivemind import apt, operations, puppet

from hivemind_contrib import swift


env.use_ssh_config = True
env.output_prefix = False


@runs_once
@task
def upgrade(exclude="", verbose=False, upgrade_method=apt.upgrade,
            pre_method=None, post_method=None, unattended=False):
    # one hour command timeout, one minute connect)
    with settings(command_timeout=3600, timeout=60):
        exclude = exclude.split(";")
        execute(apt.update)
        packages = execute(apt.verify)
        apt.filter_packages(packages, exclude)

        # check if there are packages available for upgrade
        count_packages = len(list(set(chain(*[p.keys()
                             for p in packages.values()]))))
        if count_packages is 0:
            print "No packages to upgrade"
            return
        if verbose:
            apt.print_changes_perhost(packages)
        else:
            apt.print_changes(packages)
        if not unattended:
            with settings(abort_on_prompts=False):
                do_it = prompt("Do you want to continue?", default="y")
                if do_it not in ("y", "Y"):
                    return
        if pre_method is not None:
            execute(pre_method)
        execute(upgrade_method, packages=packages)
        if post_method is not None:
            execute(post_method)


@runs_once
@task
def puppet_agent(sync=False):
    """Force execution of the puppet agent on a host.  Optionally sync the
    puppet slaves first.

    """
    if sync:
        if env.roledefs.get("puppet-slaves", None):
            execute(puppet_sync, role="puppet-slaves")
        else:
            puts("No puppet slaves to sync.")
    with show('output'):
        execute(puppet.run_agent)


@runs_once
@task
def print_hosts(for_role=None):
    for role, roledef in env.roledefs.items():
        if for_role is not None and for_role != role:
            continue
        print role
        for host in roledef:
            print '  -', host
        print


@parallel(pool_size=5)
def puppet_sync():
    operations.run("/usr/local/sbin/sync-puppet.sh")


@runs_once
@task
def swift_upgrade(exclude="", verbose=False):
    upgrade(exclude=exclude, verbose=verbose,
            upgrade_method=swift.upgrade)
