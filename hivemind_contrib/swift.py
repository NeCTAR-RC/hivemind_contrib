import os

from fabric.api import task
import swiftclient.client as swift_client

from hivemind.decorators import configurable


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
