import os

from fabric.api import env
from fabric.api import parallel
from fabric.api import puts
from fabric.api import task
from fabric.colors import blue
from fabric.colors import red
from fabric.operations import reboot
import swiftclient.client as swift_client

from hivemind import apt
from hivemind.decorators import configurable
from hivemind.operations import run
from hivemind import puppet
from hivemind import util


@configurable('nectar.openstack.client')
def client(url=None, username=None, password=None, tenant=None):
    url = os.environ.get('OS_AUTH_URL', url)
    username = os.environ.get('OS_USERNAME', username)
    password = os.environ.get('OS_PASSWORD', password)
    tenant = os.environ.get('OS_TENANT_NAME', tenant)
    assert url and username and password and tenant
    return swift_client.Connection(authurl=url,
                                   user=username,
                                   key=password,
                                   tenant_name=tenant,
                                   auth_version=2)


def list_service():

    cmd_output = run("swift-init all status", warn_only=True, quiet=True)
    running_services = []
    disabled_services = []
    get_services = [line for line in cmd_output.split("\n")]
    services_run = [rs for rs in get_services if "No" not in rs]
    for s in services_run:
        running_services.append(s.split()[0])

    services_no = [ds for ds in get_services if "No" in ds]
    for s in services_no:
        disabled_services.append(s.split()[1])

    return running_services, disabled_services


@task
@parallel(pool_size=6)
def stop_services(services='all'):
    if services is 'all':
        run("swift-init all stop",
            warn_only=True, quiet=True)
    elif services is 'background':
        # stop non-server process on storage node
        run("swift-init account-replicator stop")
        run("swift-init account-reaper stop")
        run("swift-init account-auditor stop")
        run("swift-init object-replicator stop")
        run("swift-init object-auditor stop")
        run("swift-init object-updater stop")
        run("swift-init container-replicator stop")
        run("swift-init container-updater stop")
        run("swift-init container-auditor stop")
    else:
        puts("No such services %s" % services)


@task
@parallel(pool_size=6)
def start_services():
    cmd_output = run("swift-init all start",
                     warn_only=True, quiet=True)
    return cmd_output


def print_results(services):
    def p(s):
        return '\n '.join(x for x in s)
    for k, v in services.iteritems():
        if len(v[0])is 0:
            puts("[%s]\n %s\n %s" % (k, blue("=> running"), "None"))
        else:
            puts("[%s]\n %s\n %s" % (k, blue("=> running"), p(set(v[0]))))
        puts("[%s]\n %s\n %s" % (k, red("=> disabled"), p(set(v[1]))))


@task
@parallel(pool_size=8)
def pre_upgrade(nagios=None):
    services = {}
    outage = "Package Upgrade (%s@%s)." % (util.local_user(),
                                           util.local_host())

    if nagios is not None:
        nagios.ensure_host_maintenance(outage)
    # stop the puppet service, in order to run puppet manually using agent
    puppet.stop_service()
    backup_ring()
    if 'swift-node' in identify_role_service():
        stop_services(services='background')
    else:
        stop_services(services='all')

    services[env.host_string] = list_service()
    print_results(services)


def upgrade(packages=[]):
    wait = 600
    if isinstance(packages, dict):
        packages = packages[env.host_string]
    if not packages:
        return
    puppet.run_agent()
    apt.run_upgrade(packages)
    puts('Rebooting machine (going to wait %s seconds)' % wait)
    reboot(wait=wait)


@task
@parallel(pool_size=8)
def post_upgrade(nagios=None):
    outage = "Package Upgrade (%s@%s)." % (util.local_user(),
                                           util.local_host())
    services = {}
    start_services()
    services[env.host_string] = list_service()
    print_results(services)

    if nagios is not None:
        nagios.ensure_host_maintenance(outage)


def identify_role_service():
    # function to get what roledefs a host belongs to. e.g sp01 -> swift-proxy
    if len(env.roles) is 0:
        return [k for k, v in env.roledefs.items()
                if util.current_host() in v]
    else:
        return env.roles


def backup_ring():
    services = identify_role_service()

    run("mkdir -p /etc/swift/backup_upgrade")
    run("cp /etc/swift/***.ring.gz /etc/swift/backup_upgrade/")

    if 'swift-proxy' in services:
        run("cp /etc/swift/***.builder /etc/swift/backup_upgrade/",
            warn_only=True, quiet=True)


def size_to_bytes(num):
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB']
    if num[-2:].isalpha():
        num, unit = (num[:-2], num[-2:])
    elif num[-1:].isalpha():
        num, unit = (num[:-1], num[-1])
    else:
        raise ValueError("No units found in number '%s'" % num)
    try:
        power = units.index(unit)
    except Exception:
        raise ValueError("Unit %s is not one of %s" % (unit, units))
    return int(num) * pow(1042, power)


@task
def set_quota(tenant_id, quota):
    """Set the swift quota for a tenant.

    :param str quota: A number in bytes or None for unlimited.
    """
    if quota.lower() == "none":
        quota = ''
    else:
        quota = size_to_bytes(quota)
    sc = client()
    url, token = sc.get_auth()
    base_url = url.split('_')[0] + '_'
    tenant_url = base_url + tenant_id

    swift_client.post_account(url=tenant_url,
                              token=token,
                              headers={'X-Account-Meta-Quota-Bytes': quota})
